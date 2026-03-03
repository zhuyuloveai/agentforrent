"""
租房 Agent 调测工具 —— 三种模式

⚠️  注意：PowerShell 命令行传入中文参数时存在编码问题，
    建议对含中文的查询使用 --api-probe-file 或 --preset 模式。

模式1：单用例精细运行（--id）
  python -m test.debug_runner --id SC7 M7 SC13
  对比 baseline 参数 vs agent 实际 tool call 参数，逐轮展示差异

模式2a：API 直接探针（--api-probe，参数无中文时可用）
  python -m test.debug_runner --api-probe "min_price=6000 max_price=10000 bedrooms=2"
  python -m test.debug_runner --api-probe "commute_to_xierqi_max=30 rental_type=zhengzu"

模式2b：API 探针 JSON 文件（--api-probe-file，推荐用于含中文参数）
  python -m test.debug_runner --api-probe-file probes/sc7.json
  JSON 格式：{"district": "海淀,朝阳", "decoration": "精装", "bedrooms": "2", "rental_type": "整租"}

模式2c：内置预设探针（--preset，快速验证失分用例的数据情况）
  python -m test.debug_runner --preset list          # 列出所有预设
  python -m test.debug_runner --preset sc7           # 验证SC7跨区域查询
  python -m test.debug_runner --preset m4            # 验证M4精装+电梯+两居室
  python -m test.debug_runner --preset all_failed    # 批量验证所有失分查询

模式3：地标探针（--probe-landmark，建议写入 JSON 文件传入）
  python -m test.debug_runner --probe-landmark baidu --landmark-category company
  注：地标名称若含中文同样建议使用 --api-probe-file 读取

运行具体失分用例（精细对比）：
  python -m test.debug_runner --id SC7 M7 M10 MC5
"""

import argparse
import asyncio
import json
import os
import sys
from typing import List, Optional, Dict, Any

import httpx

# ── 路径修正，确保从任意目录运行均可导入 ──
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import RENT_API_BASE, USER_ID
from src.agent.core import run
from src.agent.session import session_manager
from src.agent.tracer import RunTracer
from test.cases import ALL_CASES, TestCase, NearbyBaseline, LandmarkNameBaseline

_HEADERS = {"X-User-ID": USER_ID}
_COUNTER = 0


# ══════════════════════════════════════════════════════════════
# 底层 API 调用
# ══════════════════════════════════════════════════════════════

async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as c:
        r = await c.get(f"{RENT_API_BASE}{path}", params=params, headers=_HEADERS)
        r.raise_for_status()
        return r.json()


async def _post(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as c:
        r = await c.post(f"{RENT_API_BASE}{path}", params=params, headers=_HEADERS)
        r.raise_for_status()
        return r.json()


def _parse_houses(data: dict) -> List[str]:
    inner = data.get("data", {})
    if isinstance(inner, dict):
        items = inner.get("items", [])
    elif isinstance(inner, list):
        items = inner
    else:
        items = []
    return [h["house_id"] for h in items if isinstance(h, dict) and "house_id" in h]


async def _query_houses(params: dict) -> List[str]:
    data = await _get("/api/houses/by_platform", {**params, "page_size": 100})
    return _parse_houses(data)


async def _reset():
    await _post("/api/houses/init")


# ══════════════════════════════════════════════════════════════
# 模式2：API 探针
# ══════════════════════════════════════════════════════════════

def _parse_probe_params(raw: str) -> dict:
    """解析 'key=value key2=value2' 格式为 dict，自动转换数值类型"""
    result = {}
    for token in raw.strip().split():
        if "=" not in token:
            print(f"  [!] 忽略无效参数: {token!r}（需要 key=value 格式）")
            continue
        k, _, v = token.partition("=")
        # 尝试转为数值
        if v.lstrip("-").isdigit():
            result[k] = int(v)
        else:
            try:
                result[k] = float(v)
            except ValueError:
                result[k] = v
    return result


async def probe_api(raw_params: str) -> None:
    """直接探针查询 /api/houses/by_platform"""
    params = _parse_probe_params(raw_params)
    if not params:
        print("  [!] 未解析到任何参数，退出")
        return

    print("\n" + "=" * 62)
    print("  API 探针 → /api/houses/by_platform")
    print("-" * 62)
    print("  传入参数：")
    for k, v in params.items():
        print(f"    {k} = {v!r}")
    print("-" * 62)

    await _reset()
    try:
        data = await _get("/api/houses/by_platform", {**params, "page_size": 100})
    except Exception as e:
        print(f"  [ERROR] API调用失败: {e}")
        print("=" * 62)
        return

    inner = data.get("data", {})
    if isinstance(inner, dict):
        total = inner.get("total", 0)
        items = inner.get("items", [])
    else:
        total = 0
        items = []

    ids = [h.get("house_id", "?") for h in items]

    print(f"  返回总数: {total} 套")
    if ids:
        print(f"  house_id 列表：")
        for i, hid in enumerate(ids):
            h = items[i] if i < len(items) else {}
            district = h.get("district", "?")
            price = h.get("price", "?")
            bedrooms = h.get("bedrooms", "?")
            decoration = h.get("decoration", "?")
            elevator = h.get("elevator", "?")
            print(f"    {hid}  {district}  {bedrooms}居  {decoration}  电梯={elevator}  {price}元/月")
    else:
        print("  (无结果)")
    print("=" * 62)


# ══════════════════════════════════════════════════════════════
# 内置预设探针（规避 PowerShell 中文编码问题）
# ══════════════════════════════════════════════════════════════

_PRESETS: dict[str, list[dict]] = {
    # ── 根因A：特定区域无数据 ──
    "s6":  [{"district": "通州", "rental_type": "整租", "bedrooms": "2"}],
    "s10": [{"district": "丰台", "rental_type": "整租", "bedrooms": "2"}],
    "s13": [{"district": "丰台", "rental_type": "合租", "bedrooms": "1"}],
    "s15": [{"district": "西城", "rental_type": "整租", "bedrooms": "2"}],
    "sc14":[{"district": "东城", "decoration": "精装", "rental_type": "整租", "min_price": 6000, "max_price": 12000}],
    "sc15":[{"district": "顺义", "rental_type": "整租", "bedrooms": "2", "max_price": 6000}],
    "m9":  [{"district": "西城", "bedrooms": "2", "rental_type": "整租", "decoration": "精装"}],
    # ── 根因B：逗号分隔district ──
    "sc7": [
        {"district": "海淀,朝阳", "rental_type": "整租", "bedrooms": "2", "decoration": "精装"},  # 逗号分隔
        {"district": "海淀", "rental_type": "整租", "bedrooms": "2", "decoration": "精装"},       # 单区域对比
        {"district": "朝阳", "rental_type": "整租", "bedrooms": "2", "decoration": "精装"},       # 单区域对比
    ],
    # ── 根因C：subway_line+decoration叠加 ──
    "sc9": [
        {"subway_line": "13号线", "decoration": "精装", "rental_type": "整租", "bedrooms": "2", "max_price": 8000},
        {"subway_line": "13号线", "rental_type": "整租", "bedrooms": "2"},  # 去掉精装，对比
        {"subway_line": "13号线", "decoration": "精装"},                    # 只保留装修
    ],
    # ── 根因E：M7 agent丢失district约束 ──
    "m7":  [
        {"district": "昌平", "subway_line": "13号线", "rental_type": "整租", "bedrooms": "1"},  # baseline期望
        {"subway_line": "13号线", "bedrooms": "1", "rental_type": "整租"},                      # agent实际查询
        {"district": "昌平", "rental_type": "整租", "bedrooms": "1"},                          # 只昌平+一居室
    ],
    # ── 根因F：价格区间叠加无数据 ──
    "m10": [
        {"commute_to_xierqi_max": 30, "rental_type": "整租", "bedrooms": "2", "min_price": 6000, "max_price": 10000},
        {"commute_to_xierqi_max": 30, "rental_type": "整租", "bedrooms": "2"},  # 去掉价格限制
    ],
    "m5":  [
        {"orientation": "朝南", "rental_type": "整租", "bedrooms": "2", "min_price": 6000, "max_price": 10000},
        {"orientation": "朝南", "rental_type": "整租", "bedrooms": "2"},  # 去掉价格限制
    ],
    # ── 根因G：精装+电梯+两居室无交集 ──
    "m4":  [
        {"district": "海淀", "decoration": "精装", "rental_type": "整租", "bedrooms": "2", "elevator": "true"},
        {"district": "海淀", "decoration": "精装", "rental_type": "整租", "bedrooms": "2"},  # 去掉电梯
        {"district": "海淀", "decoration": "精装", "rental_type": "整租"},                  # 去掉户型
    ],
    # ── MC5：朝阳精装整租两居室 ──
    "mc5": [
        {"district": "朝阳", "decoration": "精装", "rental_type": "整租", "bedrooms": "2"},
        {"district": "朝阳", "rental_type": "整租", "bedrooms": "2"},  # 去掉精装
    ],
}
_PRESETS["all_failed"] = (
    _PRESETS["s6"] + _PRESETS["s10"] + _PRESETS["s13"] + _PRESETS["s15"] +
    _PRESETS["sc7"][:1] + _PRESETS["sc9"][:1] + _PRESETS["sc14"] + _PRESETS["sc15"] +
    _PRESETS["m4"][:1] + _PRESETS["m5"][:1] + _PRESETS["m7"][:1] + _PRESETS["m9"] +
    _PRESETS["m10"][:1] + _PRESETS["mc5"][:1]
)


async def _probe_one(params: dict, label: str = "") -> None:
    """执行单次 API 探针查询并输出结果"""
    display_params = {k: v for k, v in params.items()}
    await _reset()
    try:
        data = await _get("/api/houses/by_platform", {**params, "page_size": 100})
    except Exception as e:
        print(f"  [ERR] {label or '查询'} -> {e}")
        return

    inner = data.get("data", {})
    total = inner.get("total", 0) if isinstance(inner, dict) else 0
    items = inner.get("items", []) if isinstance(inner, dict) else []
    ids = [h.get("house_id", "?") for h in items]

    icon = "[OK]" if total > 0 else "[NG]"
    param_str = " ".join(f"{k}={v}" for k, v in display_params.items())
    print(f"  {icon} [{total:3d}] {param_str}")
    if total > 0 and total <= 10:
        for h in items:
            price = h.get("price", "?")
            district = h.get("district", "?")
            bedrooms = h.get("bedrooms", "?")
            decoration = h.get("decoration", "?")
            elevator = h.get("elevator", "?")
            print(f"          {h['house_id']}  {district}  {bedrooms}居  {decoration}  电梯={elevator}  {price}元/月")


async def probe_preset(preset_name: str) -> None:
    """运行内置预设探针"""
    if preset_name == "list":
        print("\n可用预设：")
        for name, queries in _PRESETS.items():
            if name == "all_failed":
                continue
            print(f"  {name:<12} ({len(queries)} 个查询)")
        print(f"  {'all_failed':<12} (批量验证所有失分用例)")
        return

    queries = _PRESETS.get(preset_name.lower())
    if queries is None:
        print(f"  [!] 未知预设 '{preset_name}'，使用 --preset list 查看可用预设")
        return

    print(f"\n{'=' * 62}")
    print(f"  预设探针：{preset_name.upper()}")
    print("-" * 62)
    for q in queries:
        await _probe_one(q)
    print("=" * 62)


async def probe_api_file(json_path: str) -> None:
    """从 JSON 文件读取查询参数并执行探针"""
    import os
    if not os.path.isabs(json_path):
        json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), json_path)
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            params = json.load(f)
    except Exception as e:
        print(f"  [!] 读取文件失败: {e}")
        return

    print(f"\n{'=' * 62}")
    print(f"  API 探针（文件）→ {json_path}")
    print("-" * 62)
    if isinstance(params, list):
        for p in params:
            await _probe_one(p)
    else:
        await _probe_one(params)
    print("=" * 62)


# ══════════════════════════════════════════════════════════════
# 模式3：地标探针
# ══════════════════════════════════════════════════════════════

async def probe_landmark(name: str, category: Optional[str], radius: float) -> None:
    """探针查询地标并验证附近房源"""
    print("\n" + "=" * 62)
    print(f"  地标探针 → /api/landmarks/search")
    print("-" * 62)
    search_params: dict = {"q": name}
    if category:
        search_params["category"] = category
    print(f"  搜索参数：q={name!r}" + (f", category={category!r}" if category else ""))
    print("-" * 62)

    await _reset()
    try:
        lm_data = await _get("/api/landmarks/search", search_params)
    except Exception as e:
        print(f"  [ERR] 地标搜索失败: {e}")
        print("=" * 62)
        return

    lm_inner = lm_data.get("data", {})
    if isinstance(lm_inner, dict):
        lm_items = lm_inner.get("items", [])
    elif isinstance(lm_inner, list):
        lm_items = lm_inner
    else:
        lm_items = []

    if not lm_items:
        print(f"  [NG] 未找到地标 '{name}'" + (f" (category={category})" if category else ""))
        print("=" * 62)
        return

    print(f"  找到 {len(lm_items)} 个地标：")
    for lm in lm_items:
        lm_id = lm.get("landmark_id") or lm.get("id", "?")
        lm_name = lm.get("name", "?")
        lm_cat = lm.get("category", "?")
        lm_lat = lm.get("latitude") or lm.get("lat", "?")
        lm_lon = lm.get("longitude") or lm.get("lon", "?")
        print(f"    {lm_id}  {lm_name}  [{lm_cat}]  ({lm_lat}, {lm_lon})")

    print()
    # 对每个找到的地标查附近房源
    for lm in lm_items[:3]:  # 最多查前3个
        lm_id = lm.get("landmark_id") or lm.get("id", "?")
        lm_name = lm.get("name", "?")
        if not lm_id or lm_id == "?":
            continue
        print(f"  nearby({lm_id}={lm_name!r}, radius={radius}m) →")
        try:
            nb_data = await _get("/api/houses/nearby", {
                "landmark_id": lm_id,
                "max_distance": radius,
                "page_size": 100,
            })
            nb_ids = _parse_houses(nb_data)
            nb_inner = nb_data.get("data", {})
            nb_total = nb_inner.get("total", len(nb_ids)) if isinstance(nb_inner, dict) else len(nb_ids)
            print(f"    共 {nb_total} 套房源")
            for hid in nb_ids[:5]:
                print(f"    • {hid}")
            if len(nb_ids) > 5:
                print(f"    ... 共 {len(nb_ids)} 套（只显示前5）")
        except Exception as e:
            print(f"    [ERROR] nearby查询失败: {e}")

    print("=" * 62)


# ══════════════════════════════════════════════════════════════
# 模式1：单用例精细运行
# ══════════════════════════════════════════════════════════════

async def _get_baseline_detail(case: TestCase) -> tuple[List[str], str, dict]:
    """
    获取基准集，同时返回查询方式和参数，便于展示。
    返回 (house_ids, query_type, query_params)
    """
    if case.baseline_house_id:
        return [case.baseline_house_id], "fixed_id", {"house_id": case.baseline_house_id}

    if case.baseline_nearby:
        nb: NearbyBaseline = case.baseline_nearby
        data = await _get("/api/houses/nearby", {
            "landmark_id": nb.landmark_id,
            "max_distance": nb.max_distance,
            "page_size": 100,
        })
        return _parse_houses(data), "nearby", {
            "landmark_id": nb.landmark_id,
            "max_distance": nb.max_distance,
        }

    if case.baseline_landmark:
        lb: LandmarkNameBaseline = case.baseline_landmark
        params: dict = {"q": lb.name}
        if lb.category:
            params["category"] = lb.category
        lm_data = await _get("/api/landmarks/search", params)
        lm_inner = lm_data.get("data", {})
        lm_items = (
            lm_inner.get("items", []) if isinstance(lm_inner, dict)
            else lm_inner if isinstance(lm_inner, list) else []
        )
        if not lm_items:
            return [], "landmark_search", {
                "landmark_search": params,
                "note": f"地标 '{lb.name}' 未找到",
            }
        lm_id = lm_items[0].get("landmark_id") or lm_items[0].get("id", "")
        data = await _get("/api/houses/nearby", {
            "landmark_id": lm_id,
            "max_distance": lb.max_distance,
            "page_size": 100,
        })
        return _parse_houses(data), "landmark_nearby", {
            "landmark_search": params,
            "resolved_id": lm_id,
            "max_distance": lb.max_distance,
        }

    if case.baseline_community:
        data = await _get("/api/houses/by_community", {
            "community": case.baseline_community,
            "page_size": 100,
        })
        return _parse_houses(data), "community", {"community": case.baseline_community}

    if case.baseline_query is not None:
        data = await _get("/api/houses/by_platform", case.baseline_query)
        return _parse_houses(data), "query", case.baseline_query

    return [], "none", {}


async def _run_single_case_debug(case: TestCase) -> None:
    """精细运行单个用例，输出详细对比信息"""
    global _COUNTER
    _COUNTER += 1
    session_id = f"debug_{case.id}_{_COUNTER}"
    session_manager.clear(session_id)

    print("\n" + "=" * 62)
    print(f"  [{case.id}] {case.name}")
    print(f"  类型={case.case_type}  满分={case.full_score}分  轮数={len(case.turns)}")
    print("=" * 62)

    await _reset()

    # ── 展示基准集查询参数 ──
    print("\n▶ [BASELINE] 基准集查询")
    baseline, query_type, query_params = await _get_baseline_detail(case)
    print(f"  方式: {query_type}")
    if query_params:
        for k, v in query_params.items():
            print(f"    {k} = {v!r}")
    if baseline:
        print(f"  → 结果: {len(baseline)} 套: {baseline[:10]}" + ("..." if len(baseline) > 10 else ""))
    else:
        print(f"  → 结果: 0 套 ⚠️  (基准集为空，纯查询类将强制得0分)")

    # ── 逐轮运行 agent ──
    agent_houses: List[str] = []
    per_turn_houses: List[List[str]] = []

    for i, user_msg in enumerate(case.turns):
        turn = i + 1
        print(f"\n▶ [TURN {turn}] 用户: {user_msg!r}")

        tracer = RunTracer(session_id=session_id, turn=turn, message=user_msg)
        try:
            result = await run(session_id, user_msg, tracer=tracer)
        except Exception as e:
            print(f"  ← [ERROR] {e}")
            per_turn_houses.append([])
            tracer.save()
            continue
        tracer.save()

        # 展示 tool calls
        tool_results = result.get("tool_results", [])
        if tool_results:
            for tr in tool_results:
                tool_name = tr.get("name", "?")
                tr_args = tr.get("arguments", {})
                success = tr.get("success", False)
                duration = tr.get("duration_ms", 0)
                status_icon = "OK" if success else "NG"
                print(f"  <- [{status_icon}] {tool_name}({duration}ms)")
                print(f"       参数: {json.dumps(tr_args, ensure_ascii=False)}")
                # 尝试解析结果摘要
                if tr.get("output"):
                    try:
                        out = json.loads(tr["output"])
                        data_inner = out.get("data", {})
                        if isinstance(data_inner, dict):
                            total = data_inner.get("total", "?")
                            items = data_inner.get("items", [])
                            sample = [h.get("house_id", "?") for h in items[:3]]
                            print(f"       结果: total={total}, sample={sample}")
                        elif isinstance(data_inner, list):
                            print(f"       结果: {len(data_inner)} 条记录")
                    except Exception:
                        pass
        else:
            print("  <- [无工具调用]")

        # 解析 agent 响应
        resp_str = result.get("response", "")
        turn_houses: List[str] = []
        try:
            resp_data = json.loads(resp_str)
            turn_houses = resp_data.get("houses", [])
            msg = resp_data.get("message", "")[:80]
            print(f"  ← 消息: {msg!r}")
            print(f"  ← houses({len(turn_houses)}): {turn_houses[:5]}" + ("..." if len(turn_houses) > 5 else ""))
        except Exception:
            print(f"  ← 响应(纯文本): {resp_str[:100]!r}")

        per_turn_houses.append(turn_houses)
        if turn_houses:
            agent_houses = turn_houses

    # ── 最终对比 ──
    print(f"\n{'─' * 62}")
    print("▶ [DIFF] 最终结果对比")
    print(f"  Baseline  ({len(baseline):3d} 套): {sorted(baseline)[:10]}" + ("..." if len(baseline) > 10 else ""))
    print(f"  Agent返回 ({len(agent_houses):3d} 套): {sorted(agent_houses)[:10]}" + ("..." if len(agent_houses) > 10 else ""))

    if baseline:
        hit = set(agent_houses) & set(baseline)
        missed = set(baseline) - set(agent_houses)
        extra = set(agent_houses) - set(baseline)
        hit_rate = len(hit) / len(baseline) * 100

        print(f"\n  命中: {len(hit)}/{len(baseline)} ({hit_rate:.0f}%)")
        if missed:
            print(f"  漏检({len(missed)}): {sorted(missed)}")
        if extra:
            print(f"  多余({len(extra)}): {sorted(extra)}")
    else:
        print("\n  [!] 无基准集，无法计算命中率")

    # ── 多轮对比（多轮用例展示每轮 diff）──
    if len(case.turns) > 1 and baseline:
        print(f"\n  各轮命中详情:")
        for i, th in enumerate(per_turn_houses):
            hit_n = len(set(th) & set(baseline))
            print(f"    轮{i+1}: {len(th)}套返回，命中{hit_n}/{len(baseline)}")

    # ── 写操作提示 ──
    if case.write_ops:
        print(f"\n  写操作({len(case.write_ops)}个): " +
              ", ".join(f"{op.action}({op.house_id})" for op in case.write_ops))
        if not baseline:
            print("  [!] 无基准集时写操作前查询自动得满分50%，得分取决于写操作执行结果")

    print("=" * 62)


# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

def _parse_args():
    parser = argparse.ArgumentParser(
        description="租房 Agent 调测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行单个失分用例精细对比
  python -m test.debug_runner --id SC7 M7

  # 验证特定区域是否有数据
  python -m test.debug_runner --api-probe "district=通州 rental_type=整租 bedrooms=2"

  # 验证逗号分隔district是否支持
  python -m test.debug_runner --api-probe "district=海淀,朝阳 decoration=精装 bedrooms=2 rental_type=整租"

  # 验证 subway_line + decoration 叠加
  python -m test.debug_runner --api-probe "subway_line=13号线 decoration=精装 rental_type=整租 bedrooms=2 max_price=8000"

  # 验证地标及附近数据
  python -m test.debug_runner --probe-landmark "百度" --landmark-category company --landmark-radius 1000
  python -m test.debug_runner --probe-landmark "昌平" --landmark-radius 2000
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--id", nargs="+", metavar="CASE_ID",
        help="运行指定用例ID（可多个），如 --id SC7 M7 M10",
    )
    group.add_argument(
        "--api-probe", metavar="PARAMS",
        help="直接探针（无中文参数时用），如 --api-probe \"bedrooms=2 max_price=8000\"",
    )
    group.add_argument(
        "--api-probe-file", metavar="JSON_PATH",
        help="从 JSON 文件读取查询参数执行探针（推荐含中文时使用）",
    )
    group.add_argument(
        "--preset", metavar="PRESET_NAME",
        help="内置预设探针，使用 --preset list 查看所有可用预设",
    )
    group.add_argument(
        "--probe-landmark", metavar="NAME",
        help="地标探针，如 --probe-landmark baidu（英文）或用文件传入中文地标名",
    )

    parser.add_argument(
        "--landmark-category", default=None,
        choices=["subway", "company", "landmark", "school", "hospital", "mall"],
        help="地标探针的 category 过滤（可选）",
    )
    parser.add_argument(
        "--landmark-radius", type=float, default=1000,
        help="地标探针的搜索半径（米），默认1000",
    )

    return parser.parse_args()


async def _main():
    args = _parse_args()

    print(f"\n租房 Agent 调测工具 | API={RENT_API_BASE} | USER={USER_ID}")

    if args.api_probe:
        await probe_api(args.api_probe)

    elif args.api_probe_file:
        await probe_api_file(args.api_probe_file)

    elif args.preset:
        await probe_preset(args.preset)

    elif args.probe_landmark:
        await probe_landmark(
            name=args.probe_landmark,
            category=args.landmark_category,
            radius=args.landmark_radius,
        )

    elif args.id:
        # 查找用例
        id_set = set(args.id)
        cases = [c for c in ALL_CASES if c.id in id_set]
        not_found = id_set - {c.id for c in cases}
        if not_found:
            print(f"  [!] 未找到用例ID: {sorted(not_found)}")
            valid_ids = [c.id for c in ALL_CASES]
            print(f"  有效ID: {valid_ids}")
        for case in cases:
            await _run_single_case_debug(case)


if __name__ == "__main__":
    asyncio.run(_main())
