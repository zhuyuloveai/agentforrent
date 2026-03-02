"""
基准集预查询工具

在 mock server 初始化后，针对所有 Single/Multi 用例的 baseline，
直接调用 API 并报告基准集大小，用于：
  1. 验证测试条件的合理性（太大/太小都需要调整）
  2. 确认 mock server 是否支持对应的查询参数
  3. 指导是否需要修改 page_size 或放宽/收紧条件

基准集大小分级：
  [S]   1-5  套：小，理论满分；适合详情查询、精确多维筛选
  [M]   6-20 套：中，agent 返回全部即可满分
  [L]  21-50 套：大，需确保 agent 不截断结果（传大 page_size）
  [XL] 50+ 套：过大，建议收紧筛选条件
  [0]  空结果：条件过严或参数不被支持

用法：
  python -m test.baseline              # 检查全部用例
  python -m test.baseline --id S1 SC4  # 只检查指定用例
"""
import argparse
import asyncio
from typing import List

import httpx

from src.config import RENT_API_BASE, USER_ID
from test.cases import (
    ALL_CASES, TestCase,
    NearbyBaseline, LandmarkNameBaseline,
    SCORE_SUMMARY,
)

_HEADERS = {"X-User-ID": USER_ID}


def _size_grade(n: int) -> str:
    if n == 0:
        return f"[0]  {n:<4} 空结果，条件过严或参数不支持"
    elif n <= 5:
        return f"[S]  {n:<4} 小，精确匹配，易满分"
    elif n <= 20:
        return f"[M]  {n:<4} 中，agent需返回全部"
    elif n <= 50:
        return f"[L]  {n:<4} 大，注意不截断（page_size需够大）"
    else:
        return f"[XL] {n:<4} 过大，建议收紧条件"


async def check_baselines(cases: List[TestCase] = None) -> None:
    if cases is None:
        cases = ALL_CASES

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        # 重置数据
        r = await client.post(f"{RENT_API_BASE}/api/houses/init", headers=_HEADERS)
        print(f"数据重置: HTTP {r.status_code}\n")

        print(f"{'ID':<6} {'名称':<28} {'类型':<8} {'满分':>5}  {'基准集评估'}")
        print("─" * 75)

        for case in cases:
            tag = f"{case.id:<6} {case.name:<28} {case.case_type:<8} {case.full_score:>5}"

            # ── Chat 类：无基准集 ──
            if case.case_type == "Chat":
                print(f"{tag}  ──  Chat类无需基准集")
                continue

            # ── 固定 house_id ──
            if case.baseline_house_id:
                try:
                    r = await client.get(
                        f"{RENT_API_BASE}/api/houses/{case.baseline_house_id}",
                        headers=_HEADERS,
                    )
                    status = r.json().get("data", {}).get("status", "?")
                    print(f"{tag}  [S]  1    固定房源 {case.baseline_house_id} (status={status})")
                except Exception as e:
                    print(f"{tag}  [!]  ERR  {e}")
                continue

            # ── 已知 landmark_id 的 nearby ──
            if case.baseline_nearby:
                nb: NearbyBaseline = case.baseline_nearby
                try:
                    r = await client.get(
                        f"{RENT_API_BASE}/api/houses/nearby",
                        params={"landmark_id": nb.landmark_id,
                                "max_distance": nb.max_distance, "page_size": 100},
                        headers=_HEADERS,
                    )
                    data = r.json()
                    inner = data.get("data", {})
                    items = inner.get("items", []) if isinstance(inner, dict) else []
                    total = inner.get("total", len(items)) if isinstance(inner, dict) else len(items)
                    grade = _size_grade(total)
                    print(f"{tag}  {grade}  nearby({nb.landmark_id}, {int(nb.max_distance)}m)")
                    if len(items) < total:
                        print(f"       [!]  API 返回 {len(items)} 条，实际共 {total} 条")
                except Exception as e:
                    print(f"{tag}  [!]  ERR  {e}")
                continue

            # ── 动态查找 landmark 的 nearby ──
            if case.baseline_landmark:
                lb: LandmarkNameBaseline = case.baseline_landmark
                try:
                    params = {"q": lb.name}
                    if lb.category:
                        params["category"] = lb.category
                    r = await client.get(
                        f"{RENT_API_BASE}/api/landmarks/search",
                        params=params,
                        headers=_HEADERS,
                    )
                    lm_data = r.json()
                    lm_inner = lm_data.get("data", {})
                    lm_items = lm_inner.get("items", []) if isinstance(lm_inner, dict) else (
                        lm_inner if isinstance(lm_inner, list) else []
                    )
                    if not lm_items:
                        print(f"{tag}  [0]  0    地标 '{lb.name}' 未找到，需核实 mock server 数据")
                        continue
                    landmark_id = lm_items[0].get("landmark_id") or lm_items[0].get("id", "?")
                    lm_name = lm_items[0].get("name", lb.name)
                    # 查附近房源
                    r2 = await client.get(
                        f"{RENT_API_BASE}/api/houses/nearby",
                        params={"landmark_id": landmark_id,
                                "max_distance": lb.max_distance, "page_size": 100},
                        headers=_HEADERS,
                    )
                    data = r2.json()
                    inner = data.get("data", {})
                    items = inner.get("items", []) if isinstance(inner, dict) else []
                    total = inner.get("total", len(items)) if isinstance(inner, dict) else len(items)
                    grade = _size_grade(total)
                    print(f"{tag}  {grade}  landmark={landmark_id}({lm_name}), {int(lb.max_distance)}m")
                    if len(items) < total:
                        print(f"       [!]  API 返回 {len(items)} 条，实际共 {total} 条")
                except Exception as e:
                    print(f"{tag}  [!]  ERR  {e}")
                continue

            # ── 小区查询 ──
            if case.baseline_community:
                try:
                    r = await client.get(
                        f"{RENT_API_BASE}/api/houses/by_community",
                        params={"community": case.baseline_community, "page_size": 100},
                        headers=_HEADERS,
                    )
                    data = r.json()
                    inner = data.get("data", {})
                    if isinstance(inner, dict):
                        items = inner.get("items", [])
                        total = inner.get("total", len(items))
                    elif isinstance(inner, list):
                        items, total = inner, len(inner)
                    else:
                        items, total = [], 0
                    grade = _size_grade(total)
                    print(f"{tag}  {grade}  community='{case.baseline_community}'")
                    if len(items) < total:
                        print(f"       [!]  API 返回 {len(items)} 条，实际共 {total} 条")
                except Exception as e:
                    print(f"{tag}  [!]  ERR  {e}")
                continue

            # ── 无 baseline_query ──
            if not case.baseline_query:
                print(f"{tag}  ──  无 baseline（需特殊处理）")
                continue

            # ── 标准 by_platform 查询 ──
            try:
                r = await client.get(
                    f"{RENT_API_BASE}/api/houses/by_platform",
                    params=case.baseline_query,
                    headers=_HEADERS,
                )
                data = r.json()
                inner = data.get("data", {})
                if isinstance(inner, dict):
                    items = inner.get("items", [])
                    total = inner.get("total", len(items))
                elif isinstance(inner, list):
                    items, total = inner, len(inner)
                else:
                    items, total = [], 0

                grade = _size_grade(total)
                print(f"{tag}  {grade}")
                if len(items) < total:
                    print(f"       [!]  API 返回 {len(items)} 条，实际共 {total} 条，"
                          f"可增大 baseline_query['page_size']")

            except Exception as e:
                print(f"{tag}  [!]  ERR  {e}")

        # 汇总
        print("\n" + "─" * 75)
        print(f"  用例分布汇总:")
        for t, s in SCORE_SUMMARY.items():
            if t != "Total":
                print(f"    {t:<12} {s['count']:>3} 个用例  满分 {s['full']:>4} 分")
        ts = SCORE_SUMMARY["Total"]
        print(f"    {'合计':<12} {ts['count']:>3} 个用例  满分 {ts['full']:>4} 分")
        print("\n提示：")
        print("  - 基准集 >20 套时，确认 agent 传 page_size 参数足够大（建议 ≥100）")
        print("  - 基准集为 0 时，检查 mock server 是否支持对应查询参数")
        print("  - [LandmarkName] 类用例若提示地标未找到，需确认 mock server 的地标数据")


def _parse_args():
    parser = argparse.ArgumentParser(description="基准集预查询工具")
    parser.add_argument("--id", nargs="+", metavar="CASE_ID",
                        help="只检查指定用例 ID，如 --id S1 SC4 M3")
    return parser.parse_args()


async def _main():
    args = _parse_args()
    cases = list(ALL_CASES)
    if args.id:
        id_set = set(args.id)
        cases = [c for c in cases if c.id in id_set]
    if not cases:
        print("没有匹配的用例，请检查 --id 参数。")
        return
    await check_baselines(cases)


if __name__ == "__main__":
    asyncio.run(_main())
