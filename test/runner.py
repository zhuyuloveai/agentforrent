"""
测试执行器 —— 模拟判题器评分逻辑

评分规则：
  - Chat：有响应即满分（5分）
  - Single/Multi 纯查询：命中率 = |agent返回 ∩ 基准集| / |基准集| × 满分
  - Multi 含写操作：
      查询部分（50%）：最后一个纯查询轮（写操作之前）的 houses 命中率 × 满分×0.5
      写操作部分（50%）：各写操作对应轮次的 API状态(50%) + houses字段(50%) × 满分×0.5
  - required_tools：指定工具未被成功调用，按缺失比例扣减得分

用法：
  python -m test.runner                  # 运行全部用例
  python -m test.runner --type Chat      # 只跑 Chat 类
  python -m test.runner --id S1 SC2 M1  # 指定用例 ID
  python -m test.runner --no-verbose     # 仅显示汇总
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Optional

import httpx

from src.agent.core import run
from src.agent.session import session_manager
from src.agent.tracer import RunTracer
from src.config import RENT_API_BASE, USER_ID
from test.cases import (
    TestCase, WriteOp, NearbyBaseline, LandmarkNameBaseline,
    ALL_CASES, CHAT_CASES,
    SINGLE_SIMPLE_CASES, SINGLE_COMPLEX_CASES,
    MULTI_MEDIUM_CASES, MULTI_COMPLEX_CASES,
    SCORE_SUMMARY,
)

_HEADERS = {"X-User-ID": USER_ID}
_COUNTER = 0  # 保证每次运行 session_id 唯一


class _Tee:
    """同时写入 stdout 和日志文件"""
    def __init__(self, log_path: str):
        self._file = open(log_path, "w", encoding="utf-8")
        self._stdout = sys.stdout

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        self._file.close()

    # 透传 isatty，避免部分库检测失败
    def isatty(self):
        return self._stdout.isatty()


def _setup_log() -> tuple[str, "_Tee"]:
    """在 logs/ 目录下创建带时间戳的日志文件，返回 (路径, Tee 对象)"""
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"test_results_{ts}.log")
    tee = _Tee(log_path)
    sys.stdout = tee
    return log_path, tee


# ──────────────────────────────────────────────────────────
# 工具函数：直接操作租房 API
# ──────────────────────────────────────────────────────────

async def _api_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        r = await client.get(f"{RENT_API_BASE}{path}", params=params, headers=_HEADERS)
        r.raise_for_status()
        return r.json()


async def _api_post(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        r = await client.post(f"{RENT_API_BASE}{path}", params=params, headers=_HEADERS)
        r.raise_for_status()
        return r.json()


async def _reset_houses() -> None:
    """重置房源数据到初始状态（模拟判题器每道题前的重置操作）"""
    await _api_post("/api/houses/init")


def _parse_houses_from_api(data: dict) -> List[str]:
    """解析 /api/houses/by_platform 返回的 house_id 列表"""
    inner = data.get("data", {})
    if isinstance(inner, dict):
        items = inner.get("items", [])
    elif isinstance(inner, list):
        items = inner
    else:
        items = []
    return [h["house_id"] for h in items if isinstance(h, dict) and "house_id" in h]


async def _get_baseline(case: TestCase) -> List[str]:
    """
    预查询基准集（模拟判题器的查询逻辑）。
    - baseline_house_id：固定单套，如详情或写操作场景
    - baseline_nearby：调用 /api/houses/nearby（已知 landmark_id）
    - baseline_landmark：动态查找 landmark_id，再调用 /api/houses/nearby
    - baseline_community：调用 /api/houses/by_community
    - baseline_queries：多次调用 /api/houses/by_platform 取并集（跨区 OR 查询）
    - baseline_query：直接调用 /api/houses/by_platform
    - 全为 None（Chat 类）：返回空列表
    """
    if case.baseline_house_id:
        return [case.baseline_house_id]

    if case.baseline_nearby:
        nb: NearbyBaseline = case.baseline_nearby
        data = await _api_get("/api/houses/nearby", {
            "landmark_id": nb.landmark_id,
            "max_distance": nb.max_distance,
            "page_size": 100,
        })
        return _parse_houses_from_api(data)

    if case.baseline_landmark:
        lb: LandmarkNameBaseline = case.baseline_landmark
        # 先搜索地标，取第一个结果的 landmark_id
        params = {"q": lb.name}
        if lb.category:
            params["category"] = lb.category
        lm_data = await _api_get("/api/landmarks/search", params)
        lm_items = lm_data.get("data", {})
        if isinstance(lm_items, dict):
            lm_items = lm_items.get("items", [])
        elif not isinstance(lm_items, list):
            lm_items = []
        if not lm_items:
            print(f"  [!] 地标 '{lb.name}' 未找到，baseline_landmark 返回空集")
            return []
        landmark_id = lm_items[0].get("landmark_id") or lm_items[0].get("id", "")
        if not landmark_id:
            print(f"  [!] 地标 '{lb.name}' 无 landmark_id 字段，返回空集")
            return []
        data = await _api_get("/api/houses/nearby", {
            "landmark_id": landmark_id,
            "max_distance": lb.max_distance,
            "page_size": 100,
        })
        return _parse_houses_from_api(data)

    if case.baseline_community:
        data = await _api_get("/api/houses/by_community", {
            "community": case.baseline_community,
            "page_size": 100,
        })
        return _parse_houses_from_api(data)

    if case.baseline_queries:
        # 多次查询取并集（用于跨区 OR 场景，如 SC7）
        all_ids: list = []
        seen: set = set()
        for q in case.baseline_queries:
            data = await _api_get("/api/houses/by_platform", q)
            for hid in _parse_houses_from_api(data):
                if hid not in seen:
                    seen.add(hid)
                    all_ids.append(hid)
        return all_ids

    if case.baseline_query is None:
        return []
    data = await _api_get("/api/houses/by_platform", case.baseline_query)
    return _parse_houses_from_api(data)


def _calc_hit_rate_score(agent_houses: List[str], baseline: List[str], full_score: float) -> float:
    """命中率得分"""
    if not baseline:
        return 0.0
    hits = len(set(agent_houses) & set(baseline))
    return round(hits / len(baseline) * full_score, 2)


def _extract_dynamic_house(all_tool_results: List[dict], action: str) -> Optional[str]:
    """
    从 agent 的工具调用结果中提取写操作使用的 house_id。
    按 action (rent/terminate/offline) 匹配工具名，取第一次成功调用的 house_id。
    """
    action_tool_map = {
        "rent": "rent_house",
        "terminate": "terminate_rental",
        "offline": "offline_house",
    }
    target_tool = action_tool_map.get(action)
    for tr in all_tool_results:
        if tr.get("name") == target_tool and tr.get("success"):
            try:
                out = json.loads(tr["output"])
                # API 返回 {"data": {"house_id": "...", ...}}
                hid = (
                    out.get("data", {}).get("house_id")
                    or out.get("house_id")
                )
                if hid:
                    return hid
            except Exception:
                pass
    return None


async def _verify_write_op(
    op: WriteOp,
    agent_houses: List[str],
    all_tool_results: List[dict],
) -> tuple[bool, bool, str]:
    """
    验证写操作结果。
    返回 (api_state_ok, houses_field_ok, resolved_house_id)
    """
    house_id = op.house_id
    if house_id == "dynamic":
        house_id = _extract_dynamic_house(all_tool_results, op.action)

    if not house_id:
        return False, False, "unknown"

    # 1. houses 字段验证
    houses_ok = house_id in agent_houses

    # 2. API 状态验证
    try:
        detail = await _api_get(f"/api/houses/{house_id}")
        status = detail.get("data", {}).get("status", "")
        api_ok = status == op.expected_status
    except Exception:
        api_ok = False

    return api_ok, houses_ok, house_id


# ──────────────────────────────────────────────────────────
# 核心：运行单个用例
# ──────────────────────────────────────────────────────────

async def run_case(case: TestCase, verbose: bool = True) -> dict:
    """运行单个测试用例，返回结果字典"""
    global _COUNTER
    _COUNTER += 1
    session_id = f"test_{case.id}_{_COUNTER}"

    # 清理可能残留的 session 状态
    session_manager.clear(session_id)

    if verbose:
        print(f"\n{'='*62}")
        tag = f"[{case.id}] {case.name}"
        print(f"  {tag:<30}  {case.case_type}  {case.full_score}分")
        print(f"{'-'*62}")

    # 重置房源数据（session 创建时 core.run() 还会再 reset 一次，均幂等）
    await _reset_houses()

    # 预查基准集
    baseline = await _get_baseline(case)
    if verbose and baseline:
        preview = str(baseline[:5]) + ("..." if len(baseline) > 5 else "")
        print(f"  基准集: {len(baseline)} 套  {preview}")

    # ── 执行多轮对话 ──
    agent_houses: List[str] = []
    per_turn_houses: List[List[str]] = []  # 每轮各自解析到的 houses，用于精确评分
    all_tool_results: List[dict] = []
    start_ts = time.time()

    for i, user_msg in enumerate(case.turns):
        turn = i + 1
        if verbose:
            print(f"  >> 轮{turn}: {user_msg}")

        tracer = RunTracer(session_id=session_id, turn=turn, message=user_msg)
        try:
            result = await run(session_id, user_msg, tracer=tracer)
        except Exception as turn_exc:
            if verbose:
                print(f"  << [ERROR] 轮{turn}异常: {turn_exc}")
            tracer.save()
            per_turn_houses.append([])  # 异常轮次记录空列表
            continue
        tracer.save()

        round_tools = result.get("tool_results", [])
        all_tool_results.extend(round_tools)

        resp_str = result["response"]
        tools_used = [t["name"] for t in round_tools]

        turn_houses: List[str] = []
        try:
            resp_data = json.loads(resp_str)
            turn_houses = resp_data.get("houses", [])
            agent_houses = turn_houses
            msg_preview = resp_data.get("message", "")[:50]
            if verbose:
                houses_preview = str(agent_houses[:5]) + ("..." if len(agent_houses) > 5 else "")
                diagnosis = tracer.to_dict()["summary"]["diagnosis"]
                diag_str = " | ".join(diagnosis)
                print(f"  << [{','.join(tools_used) or '无工具'}] {msg_preview}")
                print(f"     houses({len(agent_houses)}): {houses_preview}")
                print(f"     诊断: {diag_str}")
        except Exception:
            if verbose:
                diagnosis = tracer.to_dict()["summary"]["diagnosis"]
                print(f"  << [{','.join(tools_used) or '无工具'}] {resp_str[:80]}")
                print(f"     诊断: {' | '.join(diagnosis)}")
        per_turn_houses.append(turn_houses)

    elapsed = int((time.time() - start_ts) * 1000)

    # ── 计算得分 ──
    result_data = {
        "case_id": case.id,
        "case_name": case.name,
        "case_type": case.case_type,
        "full_score": case.full_score,
        "agent_houses": agent_houses,
        "baseline": baseline,
        "score": 0.0,
        "write_op_results": [],
        "elapsed_ms": elapsed,
    }

    # ── 空基准集警告（非 Chat 类，且定义了基准集来源但结果为空）──
    has_baseline_def = any([
        case.baseline_query is not None,
        case.baseline_queries is not None,
        case.baseline_nearby is not None,
        case.baseline_landmark is not None,
        case.baseline_community is not None,
        case.baseline_house_id is not None,
    ])
    if case.case_type != "Chat" and has_baseline_def and not baseline:
        if verbose:
            print(f"  [!] 警告：基准集为空（mock server 可能不支持该查询参数），查询部分将得0分")

    if case.case_type == "Chat":
        # Chat：任何非空响应即满分
        result_data["score"] = float(case.full_score)
        if verbose:
            print(f"  得分: {case.full_score}/{case.full_score}  (Chat类，有响应即满分)")

    elif not case.write_ops:
        # 纯查询：命中率得分
        score = _calc_hit_rate_score(agent_houses, baseline, case.full_score)
        result_data["score"] = score
        if verbose and baseline:
            hits = len(set(agent_houses) & set(baseline))
            pct = hits / len(baseline) * 100 if baseline else 0
            print(f"  命中: {hits}/{len(baseline)} ({pct:.0f}%)  得分: {score}/{case.full_score}")

    else:
        # 含写操作：查询 50%（最后一个纯查询轮）+ 写操作 50%（各写操作对应轮次）
        write_op_count = len(case.write_ops)
        # 最后一个纯查询轮的索引（假设最后 write_op_count 轮为写操作轮）
        query_turn_idx = max(0, len(case.turns) - write_op_count - 1)
        query_houses = (
            per_turn_houses[query_turn_idx]
            if query_turn_idx < len(per_turn_houses)
            else agent_houses
        )
        write_op_start_idx = len(case.turns) - write_op_count

        query_score = (
            _calc_hit_rate_score(query_houses, baseline, case.full_score * 0.5)
            if baseline else case.full_score * 0.5
        )

        write_total = 0.0
        per_op_full = case.full_score * 0.5 / write_op_count
        for op_idx, op in enumerate(case.write_ops):
            # 每个写操作用其对应轮次的 houses 做 houses_ok 验证
            op_turn_idx = write_op_start_idx + op_idx
            op_turn_houses = (
                per_turn_houses[op_turn_idx]
                if op_turn_idx < len(per_turn_houses)
                else agent_houses
            )
            api_ok, houses_ok, resolved_id = await _verify_write_op(op, op_turn_houses, all_tool_results)
            op_score = round(per_op_full * (0.5 * api_ok + 0.5 * houses_ok), 2)
            write_total += op_score
            result_data["write_op_results"].append({
                "action": op.action,
                "house_id": resolved_id,
                "api_state_ok": api_ok,
                "houses_field_ok": houses_ok,
                "op_score": op_score,
            })
            if verbose:
                status_icon = "[OK]" if api_ok else "[NG]"
                houses_icon = "[OK]" if houses_ok else "[NG]"
                print(f"  写操作 {op.action}({resolved_id}): "
                      f"API状态{status_icon}  houses字段{houses_icon}  +{op_score:.1f}分")

        total = round(query_score + write_total, 2)
        result_data["score"] = total
        if verbose:
            if baseline:
                hits = len(set(query_houses) & set(baseline))
                print(f"  命中(轮{query_turn_idx + 1}): {hits}/{len(baseline)}  "
                      f"查询得分: {query_score:.1f}  写操作得分: {write_total:.1f}  "
                      f"总分: {total}/{case.full_score}")
            else:
                print(f"  写操作得分: {write_total:.1f}  总分: {total}/{case.full_score}")

    # ── required_tools 工具链路验证（非 Chat 类）──
    if case.required_tools and case.case_type != "Chat":
        called_tools = {tr["name"] for tr in all_tool_results if tr.get("success")}
        missing = [t for t in case.required_tools if t not in called_tools]
        if missing:
            tool_factor = (len(case.required_tools) - len(missing)) / len(case.required_tools)
            adjusted = round(result_data["score"] * tool_factor, 2)
            result_data["missing_tools"] = missing
            result_data["score"] = adjusted
            if verbose:
                print(f"  工具缺失: {missing}  系数: {tool_factor:.2f}  "
                      f"调整后得分: {adjusted}/{case.full_score}")

    if verbose:
        print(f"  耗时: {elapsed}ms")

    return result_data


# ──────────────────────────────────────────────────────────
# 批量运行 + 汇总
# ──────────────────────────────────────────────────────────

async def run_all(cases: List[TestCase] = None, verbose: bool = True) -> List[dict]:
    """运行全部（或指定）用例并打印汇总"""
    if cases is None:
        cases = ALL_CASES

    all_results = []
    type_stats: dict = {}

    for case in cases:
        try:
            res = await run_case(case, verbose=verbose)
        except Exception as exc:
            print(f"\n  [SKIP] {case.id} {case.name} 异常跳过: {exc}")
            res = {
                "case_id": case.id,
                "case_name": case.name,
                "case_type": case.case_type,
                "full_score": case.full_score,
                "score": 0.0,
                "skipped": True,
                "error": str(exc),
                "agent_houses": [],
                "baseline": [],
                "write_op_results": [],
                "elapsed_ms": 0,
            }
        all_results.append(res)

        t = res["case_type"]
        if t not in type_stats:
            type_stats[t] = {"score": 0.0, "full": 0, "count": 0}
        type_stats[t]["score"] += res["score"]
        type_stats[t]["full"] += res["full_score"]
        type_stats[t]["count"] += 1

    total_score = sum(r["score"] for r in all_results)
    total_full = sum(r["full_score"] for r in all_results)
    skipped = [r for r in all_results if r.get("skipped")]

    print(f"\n{'='*62}")
    print(f"  测试结果汇总")
    print(f"{'-'*62}")
    print(f"  {'类型':<10} {'题数':>5} {'得分':>10} {'满分':>8} {'命中率':>8}")
    print(f"{'-'*62}")
    for t in ["Chat", "Single", "Multi"]:
        if t in type_stats:
            s = type_stats[t]
            pct = s["score"] / s["full"] * 100 if s["full"] else 0
            print(f"  {t:<10} {s['count']:>5} {s['score']:>10.1f} {s['full']:>8} {pct:>7.1f}%")
    print(f"{'-'*62}")
    pct = total_score / total_full * 100 if total_full else 0
    print(f"  {'合计':<10} {len(all_results):>5} {total_score:>10.1f} {total_full:>8} {pct:>7.1f}%")
    if skipped:
        print(f"  跳过用例({len(skipped)}): {', '.join(r['case_id'] for r in skipped)}")
    print(f"{'='*62}\n")

    return all_results


# ──────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(description="租房 Agent 评分测试执行器")
    parser.add_argument(
        "--type", choices=["Chat", "Single", "Multi"],
        help="只运行指定类型的用例"
    )
    parser.add_argument(
        "--id", nargs="+", metavar="CASE_ID",
        help="指定运行的用例 ID，如 --id S1 SC2 M1"
    )
    parser.add_argument(
        "--no-verbose", action="store_true",
        help="不显示每轮详细过程，只打印汇总"
    )
    return parser.parse_args()


async def _main():
    args = _parse_args()
    verbose = not args.no_verbose

    log_path, tee = _setup_log()

    try:
        # 筛选用例
        cases = list(ALL_CASES)
        if args.type:
            cases = [c for c in cases if c.case_type == args.type]
        if args.id:
            id_set = set(args.id)
            cases = [c for c in cases if c.id in id_set]

        if not cases:
            print("没有匹配的用例，请检查 --type 或 --id 参数。")
            return

        print(f"\n准备运行 {len(cases)} 个用例，满分 {sum(c.full_score for c in cases)} 分")
        await run_all(cases, verbose=verbose)
        print(f"\n日志已保存至: {log_path}")
    finally:
        sys.stdout = tee._stdout
        tee.close()


if __name__ == "__main__":
    asyncio.run(_main())
