#!/usr/bin/env python3
"""
抓取真实房源数据脚本（完整版）

从比赛环境 API 抓取全量房源、三平台挂牌记录和地标数据，保存为本地 JSON 文件。

用法：
  # 基础抓取（房源 + 地标 + 统计）
  python scripts/fetch_real_data.py

  # 同时抓取每套房源的三平台挂牌详情（较慢，约需多几分钟）
  python scripts/fetch_real_data.py --fetch-listings

  # 指定参数
  python scripts/fetch_real_data.py --api-base http://7.225.29.223:8080 --user-id z00881489
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

# 默认配置（优先读取环境变量）
DEFAULT_API_BASE = os.getenv("RENT_API_BASE", "http://7.225.29.223:8080")
DEFAULT_USER_ID = os.getenv("USER_ID", "z00881489")
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data")

DISTRICTS = ["海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"]
PLATFORMS = ["安居客", "链家", "58同城"]

# 并发抓取 listings 的线程数
LISTINGS_WORKERS = 10


def make_client(user_id: str) -> httpx.Client:
    return httpx.Client(headers={"X-User-ID": user_id}, timeout=30)


def fetch_json(client: httpx.Client, url: str, params: dict = None, label: str = "") -> dict:
    try:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [警告] {label} 返回非0: {data.get('message')}")
        return data
    except httpx.RequestError as e:
        print(f"  [错误] {label} 请求失败: {e}")
        return {}
    except httpx.HTTPStatusError as e:
        print(f"  [错误] {label} HTTP {e.response.status_code}")
        return {}


# ─────────────────────────────────────────────
# 接口 1: GET /api/landmarks  +  接口 2: GET /api/landmarks/stats
# ─────────────────────────────────────────────
def fetch_all_landmarks(api_base: str) -> tuple[list[dict], dict]:
    """
    抓取全部地标（不需要 X-User-ID）。
    接口 1: GET /api/landmarks  （按类别分别拉取，兜底全量）
    接口 2: GET /api/landmarks/stats （地标统计）
    """
    print("\n=== [接口1] 抓取地标列表 ===")
    url = f"{api_base}/api/landmarks"
    all_landmarks: dict[str, dict] = {}

    with httpx.Client(timeout=30) as lm_client:
        # 按类别分别拉，防止接口有数量限制
        for category in ["subway", "company", "landmark"]:
            r = fetch_json(lm_client, url, params={"category": category}, label=f"地标({category})")
            items = r.get("data", {}).get("items", r.get("data", []))
            if isinstance(items, list):
                for lm in items:
                    lid = lm.get("id") or lm.get("landmark_id")
                    if lid:
                        all_landmarks[lid] = lm
                print(f"  {category}: {len(items)} 条")

        # 不带参数兜底
        r = fetch_json(lm_client, url, params={}, label="地标(全部兜底)")
        items = r.get("data", {}).get("items", r.get("data", []))
        if isinstance(items, list):
            added = 0
            for lm in items:
                lid = lm.get("id") or lm.get("landmark_id")
                if lid and lid not in all_landmarks:
                    all_landmarks[lid] = lm
                    added += 1
            print(f"  全部(兜底): {len(items)} 条 (新增 {added} 条)")

        print(f"  汇总去重: {len(all_landmarks)} 个地标")

        # 接口2: 地标统计
        print("\n=== [接口2] 地标统计 ===")
        stats_r = fetch_json(lm_client, f"{api_base}/api/landmarks/stats", label="地标统计")
        lm_stats = stats_r.get("data", {})
        print(f"  地标总数: {lm_stats.get('total', 'N/A')}")
        print(f"  按类别: {lm_stats.get('by_category', lm_stats.get('by_type', {}))}")

    return list(all_landmarks.values()), lm_stats


# ─────────────────────────────────────────────
# 接口 3: GET /api/houses/by_platform  （三平台全量）
# ─────────────────────────────────────────────
def fetch_all_houses_by_platform(client: httpx.Client, api_base: str) -> dict[str, dict]:
    """
    接口3: GET /api/houses/by_platform
    分别用 安居客/链家/58同城 各抓一次全量，再按行政区补漏，合并去重。
    返回 {house_id: house_dict}，house_dict 中附加 _platforms 字段记录出现的平台。
    """
    print("\n=== [接口3] 抓取全量房源（三平台）===")
    url = f"{api_base}/api/houses/by_platform"
    all_houses: dict[str, dict] = {}

    # 按平台拉全量
    for platform in PLATFORMS:
        r = fetch_json(client, url, params={"listing_platform": platform, "page_size": 10000, "page": 1},
                       label=f"房源({platform})")
        items = r.get("data", {}).get("items", [])
        total = r.get("data", {}).get("total", len(items))
        added = 0
        for h in items:
            hid = h["house_id"]
            if hid not in all_houses:
                h.setdefault("_platforms", [])
                h["_platforms"].append(platform)
                all_houses[hid] = h
                added += 1
            else:
                all_houses[hid].setdefault("_platforms", [])
                if platform not in all_houses[hid]["_platforms"]:
                    all_houses[hid]["_platforms"].append(platform)
        print(f"  {platform}: 共 {total} 条，返回 {len(items)} 条，新增 {added} 条")

    # 按行政区补漏（不指定平台 = 默认安居客）
    print("  按行政区补漏...")
    for district in DISTRICTS:
        for platform in PLATFORMS:
            r = fetch_json(client, url,
                           params={"district": district, "listing_platform": platform,
                                   "page_size": 10000, "page": 1},
                           label=f"补漏({district}/{platform})")
            items = r.get("data", {}).get("items", [])
            for h in items:
                hid = h["house_id"]
                if hid not in all_houses:
                    h.setdefault("_platforms", [platform])
                    all_houses[hid] = h
                else:
                    all_houses[hid].setdefault("_platforms", [])
                    if platform not in all_houses[hid]["_platforms"]:
                        all_houses[hid]["_platforms"].append(platform)

    print(f"  汇总去重: {len(all_houses)} 套房源")
    return all_houses


# ─────────────────────────────────────────────
# 接口 4: GET /api/houses/listings/{house_id}
# ─────────────────────────────────────────────
def fetch_one_listing(args: tuple) -> tuple[str, dict]:
    """单套房源的三平台挂牌记录（线程池调用）"""
    api_base, user_id, house_id = args
    url = f"{api_base}/api/houses/listings/{house_id}"
    try:
        with httpx.Client(headers={"X-User-ID": user_id}, timeout=20) as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
            return house_id, data.get("data", {})
    except Exception as e:
        return house_id, {"error": str(e)}


def fetch_all_listings(api_base: str, user_id: str, house_ids: list[str]) -> dict[str, dict]:
    """
    接口4: GET /api/houses/listings/{house_id}
    并发抓取所有房源的三平台挂牌记录。
    """
    print(f"\n=== [接口4] 抓取三平台挂牌记录（共 {len(house_ids)} 套，并发{LISTINGS_WORKERS}）===")
    results: dict[str, dict] = {}
    args_list = [(api_base, user_id, hid) for hid in house_ids]
    done = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=LISTINGS_WORKERS) as executor:
        futures = {executor.submit(fetch_one_listing, args): args[2] for args in args_list}
        for future in as_completed(futures):
            house_id, data = future.result()
            results[house_id] = data
            if "error" in data:
                errors += 1
            done += 1
            if done % 100 == 0 or done == len(house_ids):
                print(f"  进度: {done}/{len(house_ids)}，错误: {errors}")

    print(f"  完成: {len(results)} 条，错误: {errors} 条")
    return results


# ─────────────────────────────────────────────
# 接口 5: GET /api/houses/stats
# ─────────────────────────────────────────────
def fetch_house_stats(client: httpx.Client, api_base: str) -> dict:
    """接口5: GET /api/houses/stats - 房源统计信息"""
    print("\n=== [接口5] 房源统计 ===")
    r = fetch_json(client, f"{api_base}/api/houses/stats", label="房源统计")
    data = r.get("data", {})
    print(f"  总房源数: {data.get('total', 'N/A')}")
    print(f"  按状态:   {data.get('by_status', {})}")
    print(f"  按行政区: {data.get('by_district', {})}")
    return data


# ─────────────────────────────────────────────
# 本地分析
# ─────────────────────────────────────────────
def analyze_houses(houses: list[dict]) -> dict:
    if not houses:
        return {}

    districts: dict[str, int] = {}
    rental_types: dict[str, int] = {}
    decorations: dict[str, int] = {}
    price_ranges = {"500以下": 0, "500-2000": 0, "2000-5000": 0, "5000-10000": 0, "10000以上": 0}
    with_elevator = 0
    near_subway = 0
    platform_count: dict[str, int] = {}

    for h in houses:
        districts[h.get("district", "未知")] = districts.get(h.get("district", "未知"), 0) + 1
        rental_types[h.get("rental_type", "未知")] = rental_types.get(h.get("rental_type", "未知"), 0) + 1
        decorations[h.get("decoration", "未知")] = decorations.get(h.get("decoration", "未知"), 0) + 1

        price = h.get("price", 0) or 0
        if price < 500:
            price_ranges["500以下"] += 1
        elif price < 2000:
            price_ranges["500-2000"] += 1
        elif price < 5000:
            price_ranges["2000-5000"] += 1
        elif price < 10000:
            price_ranges["5000-10000"] += 1
        else:
            price_ranges["10000以上"] += 1

        if h.get("elevator"):
            with_elevator += 1

        subway_dist = h.get("subway_distance") or h.get("subway_dist") or 9999
        if subway_dist <= 800:
            near_subway += 1

        for p in h.get("_platforms", []):
            platform_count[p] = platform_count.get(p, 0) + 1

    return {
        "total": len(houses),
        "by_district": districts,
        "by_rental_type": rental_types,
        "by_decoration": decorations,
        "by_price_range": price_ranges,
        "with_elevator": with_elevator,
        "near_subway_800m": near_subway,
        "by_platform": platform_count,
    }


def save_json(data, filepath: str, label: str = ""):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"  已保存 {label}: {filepath} ({size_kb:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(description="抓取比赛环境真实房源数据（完整版）")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE,
                        help=f"API 地址 (默认: {DEFAULT_API_BASE})")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID,
                        help=f"用户工号 (默认: {DEFAULT_USER_ID})")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="输出目录 (默认: data/)")
    parser.add_argument("--fetch-listings", action="store_true",
                        help="同时抓取每套房源的三平台挂牌记录（接口4，较慢）")
    parser.add_argument("--skip-landmarks", action="store_true",
                        help="跳过地标数据抓取")
    parser.add_argument("--skip-stats", action="store_true",
                        help="跳过房源统计抓取")
    args = parser.parse_args()

    api_base = args.api_base.rstrip("/")
    output_dir = args.output
    user_id = args.user_id

    print("=" * 50)
    print(f"API 地址: {api_base}")
    print(f"用户工号: {user_id}")
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"抓取listings: {'是' if args.fetch_listings else '否（加 --fetch-listings 开启）'}")
    print("=" * 50)

    start_time = time.time()
    client = make_client(user_id)

    # ── 接口1+2: 地标 ──
    landmarks_list, lm_stats = [], {}
    if not args.skip_landmarks:
        landmarks_list, lm_stats = fetch_all_landmarks(api_base)

    # ── 接口3: 三平台全量房源 ──
    houses_dict = fetch_all_houses_by_platform(client, api_base)
    houses_list = list(houses_dict.values())

    # ── 接口4: 三平台挂牌记录（可选） ──
    listings_dict: dict[str, dict] = {}
    if args.fetch_listings:
        listings_dict = fetch_all_listings(api_base, user_id, list(houses_dict.keys()))

    # ── 接口5: 房源统计 ──
    house_stats = {}
    if not args.skip_stats:
        house_stats = fetch_house_stats(client, api_base)

    client.close()

    # 本地分析
    analysis = analyze_houses(houses_list)

    elapsed = time.time() - start_time
    print(f"\n=== 抓取完成，耗时 {elapsed:.1f}s ===")

    # ── 保存数据 ──
    print("\n=== 保存数据 ===")
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    save_json(houses_list,           f"{output_dir}/houses_all.json",       "全量房源（三平台合并）")
    save_json(landmarks_list,        f"{output_dir}/landmarks_all.json",    "全量地标")
    save_json(lm_stats,              f"{output_dir}/landmarks_stats.json",  "地标统计")
    save_json(house_stats,           f"{output_dir}/houses_stats.json",     "房源统计")
    save_json(analysis,              f"{output_dir}/houses_analysis.json",  "本地分析摘要")

    if listings_dict:
        save_json(listings_dict,     f"{output_dir}/houses_listings.json",  "三平台挂牌记录")

    # 带时间戳备份
    save_json(houses_list,           f"{output_dir}/backup/houses_{timestamp}.json", "房源备份")

    # ── 摘要 ──
    print("\n=== 数据摘要 ===")
    print(f"  房源总数:        {analysis.get('total', 0)}")
    print(f"  平台分布:        {analysis.get('by_platform', {})}")
    print(f"  行政区分布:      {analysis.get('by_district', {})}")
    print(f"  租房类型:        {analysis.get('by_rental_type', {})}")
    print(f"  价格分布:        {analysis.get('by_price_range', {})}")
    print(f"  有电梯:          {analysis.get('with_elevator', 0)} 套")
    print(f"  近地铁(≤800m):  {analysis.get('near_subway_800m', 0)} 套")
    print(f"  地标总数:        {len(landmarks_list)}")
    if listings_dict:
        print(f"  挂牌记录(套):   {len(listings_dict)}")


if __name__ == "__main__":
    main()
