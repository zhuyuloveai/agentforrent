"""Agent 核心逻辑：Function Calling 主流程"""
import json
import re
import time
import logging
from typing import Optional

from src.agent.prompts import SYSTEM_PROMPT, TOOLS
from src.agent.session import session_manager
from src.agent.tracer import RunTracer
from src.tools.model_client import ModelClient
from src.tools import rent_api, landmark_api

logger = logging.getLogger(__name__)

TOOL_HANDLERS = {
    "search_houses": rent_api.search_houses,
    "get_house_detail": rent_api.get_house_detail,
    "get_house_listings": rent_api.get_house_listings,
    "get_houses_by_community": rent_api.get_houses_by_community,
    "get_houses_nearby": rent_api.get_houses_nearby,
    "get_nearby_landmarks": rent_api.get_nearby_landmarks,
    "search_landmarks": landmark_api.search_landmarks,
    "get_landmark_by_name": landmark_api.get_landmark_by_name,
    "rent_house": rent_api.rent_house,
    "terminate_rental": rent_api.terminate_rental,
    "offline_house": rent_api.offline_house,
}

_GREET_PATTERNS = {"你好", "hello", "hi", "您好", "嗨", "在吗"}


def _is_simple_chat(message: str) -> bool:
    msg = message.strip().lower()
    return len(msg) <= 8 and any(p in msg for p in _GREET_PATTERNS)


def _extract_json_from_text(text: str) -> dict | None:
    """从模型输出中提取包含 houses 字段的 JSON，支持混合文本"""
    # 先尝试直接解析
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # 正则找最后一个包含 houses 的 JSON 块
    matches = re.findall(r'\{[^{}]*"houses"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[-1])
        except Exception:
            pass
    return None


async def _execute_tool(name: str, arguments: dict) -> tuple[str, bool]:
    """执行工具调用，返回 (结果JSON字符串, 是否成功)"""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False), False
    try:
        result = await handler(**arguments)
        return json.dumps(result, ensure_ascii=False), True
    except Exception as e:
        logger.warning(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False), False


def _extract_houses_from_collected(tool_results: list) -> list[str]:
    """从本轮工具调用结果中提取房源 ID，避免混入多轮对话的历史数据"""
    houses = []
    for tr in tool_results:
        try:
            data = json.loads(tr["output"])
            inner = data.get("data", {})
            if isinstance(inner, dict):
                # 单套房源详情（get_house_detail / rent_house / offline_house 等）
                hid = inner.get("house_id")
                if hid and hid not in houses:
                    houses.append(hid)
                # 列表型响应
                items = inner.get("items", [])
                if isinstance(items, list):
                    for item in items:
                        hid = item.get("house_id") or item.get("id")
                        if hid and hid not in houses:
                            houses.append(hid)
            elif isinstance(inner, list):
                for item in inner:
                    hid = item.get("house_id") or item.get("id")
                    if hid and hid not in houses:
                        houses.append(hid)
        except Exception:
            pass
    return houses


MAX_TOOL_ROUNDS = 3


def _sanitize_messages(messages: list) -> list:
    """清洗历史消息，避免空 content 导致模型服务器 500。
    - assistant 消息：content 为 None 时改为空字符串；content 纯空白且无 tool_calls 时跳过
    - tool/user 消息：content 为 None 时改为空字符串
    """
    result = []
    for msg in messages:
        msg = dict(msg)  # 浅拷贝，不改原始 session 数据
        role = msg.get("role")
        content = msg.get("content")

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if content is None:
                msg["content"] = ""
            if not str(content or "").strip() and not tool_calls:
                # 纯空白且没有工具调用的 assistant 消息，跳过
                continue
        else:
            if content is None:
                msg["content"] = ""

        result.append(msg)
    return result


async def run(
    session_id: str,
    message: str,
    model_ip: str = None,
    tracer: Optional[RunTracer] = None,
) -> dict:
    """
    Agent 主入口。返回 {"response": str, "tool_results": list, "tracer": RunTracer}
    - 普通对话：response 为自然语言文本
    - 房源查询：response 为 JSON 字符串 {"message": "...", "houses": [...]}

    采用 Agent 循环：每轮模型调用均开放工具，模型自主决定何时停止调用。
    最多循环 MAX_TOOL_ROUNDS 轮，超出后强制生成最终回复。
    tracer 由调用方（main.py）创建并传入，用于完整记录执行过程。
    """
    start = time.time()

    # 新 session 自动重置房源数据，确保每次用例从干净状态开始
    is_new_session = session_id not in session_manager._sessions
    if is_new_session:
        try:
            await rent_api.init_houses()
            logger.info(f"[{session_id}] new session, house data reset")
        except Exception:
            pass

    # 简单问候，模板回复，0 次模型调用
    if _is_simple_chat(message):
        if tracer:
            tracer.mark_simple_chat()
            tracer.record_output("", "plain_text", [])
        return {
            "response": "您好！我是租房助手，请告诉我您的租房需求，例如区域、预算、户型等，我来帮您找房。",
            "tool_results": [],
            "tracer": tracer,
        }

    client = ModelClient(model_ip=model_ip, session_id=session_id)
    session_manager.add_message(session_id, "user", message)

    collected_tool_results = []
    final_content = ""

    # ── Agent 循环：最多 MAX_TOOL_ROUNDS 轮工具调用 ──
    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        messages = _sanitize_messages(
            [{"role": "system", "content": SYSTEM_PROMPT}] + session_manager.get_messages(session_id)
        )

        llm_ctx = tracer.begin_llm_call(round_num, len(messages)) if tracer else None
        response = await client.chat_completion(messages=messages, tools=TOOLS)
        if tracer and llm_ctx:
            tracer.end_llm_call(llm_ctx, response)

        choice = response["choices"][0]
        msg = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")
        tool_calls = msg.get("tool_calls") or []

        # 模型不再调用工具，直接输出最终回复
        if not tool_calls or finish_reason == "stop":
            final_content = msg.get("content", "")
            session_manager.add_message(session_id, "assistant", final_content)
            logger.info(f"[{session_id}] agent done after {round_num} round(s)")
            break

        # 模型发起了工具调用，先把 assistant 消息存入 session
        session_manager.get_messages(session_id).append(msg)

        # 执行所有工具
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except Exception:
                arguments = {}

            logger.info(f"[{session_id}] round {round_num} tool: {name}({arguments})")
            t0 = time.time()
            result_str, success = await _execute_tool(name, arguments)
            tool_ms = int((time.time() - t0) * 1000)

            collected_tool_results.append({"name": name, "success": success, "output": result_str})
            if tracer:
                tracer.record_tool_call(round_num, name, arguments, success, tool_ms, result_str)

            tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result_str}
            session_manager.get_messages(session_id).append(tool_msg)

    else:
        # 超出最大轮数，强制调用一次（不传 tools）生成最终回复
        logger.warning(f"[{session_id}] max tool rounds ({MAX_TOOL_ROUNDS}) exhausted, forcing final response")
        messages = _sanitize_messages(
            [{"role": "system", "content": SYSTEM_PROMPT}] + session_manager.get_messages(session_id)
        )

        llm_ctx = tracer.begin_llm_call(MAX_TOOL_ROUNDS + 1, len(messages), forced=True) if tracer else None
        forced_resp = await client.chat_completion(messages=messages)
        if tracer and llm_ctx:
            tracer.end_llm_call(llm_ctx, forced_resp)

        final_content = forced_resp["choices"][0]["message"].get("content", "")
        session_manager.add_message(session_id, "assistant", final_content)

    # ── 解析最终输出 ──
    parsed = _extract_json_from_text(final_content)
    if parsed and "houses" in parsed:
        houses = parsed["houses"]
        session_manager.update_candidates(session_id, houses)
        # 区分直接解析成功还是正则提取
        parse_method = "json_direct"
        try:
            json.loads(final_content.strip())
        except Exception:
            parse_method = "json_regex"
        if tracer:
            tracer.record_output(final_content, parse_method, houses)
        resp_str = json.dumps(
            {"message": parsed.get("message", "为您找到以下符合条件的房源："), "houses": houses},
            ensure_ascii=False,
        )
        logger.info(f"[{session_id}] done in {int((time.time() - start) * 1000)}ms, houses={houses}")
        return {"response": resp_str, "tool_results": collected_tool_results, "tracer": tracer}

    # 兜底：从本轮工具结果里提取房源 ID（不扫历史，避免多轮污染）
    fallback_houses = _extract_houses_from_collected(collected_tool_results)
    if fallback_houses:
        session_manager.update_candidates(session_id, fallback_houses)
        if tracer:
            tracer.record_output(final_content, "fallback_tools", fallback_houses)
        summary = re.sub(r'\{.*?"houses".*?\}', '', final_content, flags=re.DOTALL).strip()
        msg_text = summary[:200] if summary else "为您找到以下符合条件的房源："
        resp_str = json.dumps({"message": msg_text, "houses": fallback_houses}, ensure_ascii=False)
        logger.info(f"[{session_id}] done in {int((time.time() - start) * 1000)}ms, fallback houses={fallback_houses}")
        return {"response": resp_str, "tool_results": collected_tool_results, "tracer": tracer}

    if tracer:
        tracer.record_output(final_content, "plain_text", [])
    logger.info(f"[{session_id}] done in {int((time.time() - start) * 1000)}ms")
    return {"response": final_content, "tool_results": collected_tool_results, "tracer": tracer}
