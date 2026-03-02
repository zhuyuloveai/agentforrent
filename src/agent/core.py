"""Agent 核心逻辑：Function Calling 主流程"""
import json
import re
import time
import logging

from src.agent.prompts import SYSTEM_PROMPT, TOOLS
from src.agent.session import session_manager
from src.tools.model_client import ModelClient
from src.tools import rent_api, landmark_api

logger = logging.getLogger(__name__)

TOOL_HANDLERS = {
    "search_houses": rent_api.search_houses,
    "get_house_detail": rent_api.get_house_detail,
    "get_house_listings": rent_api.get_house_listings,
    "get_houses_nearby": rent_api.get_houses_nearby,
    "get_nearby_landmarks": rent_api.get_nearby_landmarks,
    "search_landmarks": landmark_api.search_landmarks,
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


async def _execute_tool(name: str, arguments: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
    try:
        result = await handler(**arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _extract_houses_from_tool_results(messages: list) -> list[str]:
    """从工具返回结果中提取房源 ID 列表"""
    houses = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        try:
            data = json.loads(msg["content"])
            items = data.get("data", {})
            if isinstance(items, dict):
                items = items.get("items", [])
            if isinstance(items, list):
                for item in items:
                    hid = item.get("house_id") or item.get("id")
                    if hid and hid not in houses:
                        houses.append(hid)
        except Exception:
            pass
    return houses


async def run(session_id: str, message: str, model_ip: str = None) -> str:
    """
    Agent 主入口。
    普通对话返回文本，房源查询返回 JSON 字符串：{"message": "...", "houses": [...]}
    """
    start = time.time()

    # 简单问候，模板回复，0 次模型调用
    if _is_simple_chat(message):
        return "您好！我是租房助手，请告诉我您的租房需求，例如区域、预算、户型等，我来帮您找房。"

    client = ModelClient(model_ip=model_ip, session_id=session_id)

    session_manager.add_message(session_id, "user", message)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + session_manager.get_messages(session_id)

    # ── 第一次模型调用：意图识别 + 工具选择 ──
    response = await client.chat_completion(messages=messages, tools=TOOLS, temperature=1.0)
    choice = response["choices"][0]["message"]
    tool_calls = choice.get("tool_calls") or []

    if not tool_calls:
        reply = choice.get("content", "")
        session_manager.add_message(session_id, "assistant", reply)
        return reply

    # ── 执行工具调用 ──
    messages.append(choice)
    session_manager.get_messages(session_id).append(choice)

    for tc in tool_calls:
        name = tc["function"]["name"]
        try:
            arguments = json.loads(tc["function"]["arguments"])
        except Exception:
            arguments = {}

        logger.info(f"[{session_id}] tool call: {name}({arguments})")
        result = await _execute_tool(name, arguments)

        tool_msg = {"role": "tool", "tool_call_id": tc["id"], "content": result}
        messages.append(tool_msg)
        session_manager.get_messages(session_id).append(tool_msg)

    # ── 第二次模型调用：生成最终回复 ──
    messages2 = [{"role": "system", "content": SYSTEM_PROMPT}] + session_manager.get_messages(session_id)
    response2 = await client.chat_completion(messages=messages2, temperature=1.0)
    final_content = response2["choices"][0]["message"].get("content", "")

    session_manager.add_message(session_id, "assistant", final_content)

    # 从输出中提取 JSON（支持模型输出混合文本的情况）
    parsed = _extract_json_from_text(final_content)
    if parsed and "houses" in parsed:
        houses = parsed["houses"][:5]
        session_manager.update_candidates(session_id, houses)
        return json.dumps(
            {"message": parsed.get("message", "为您找到以下符合条件的房源："), "houses": houses},
            ensure_ascii=False,
        )

    # 兜底：从工具结果里提取房源 ID，模型输出作为 message
    all_houses = _extract_houses_from_tool_results(session_manager.get_messages(session_id))
    if all_houses:
        top5 = all_houses[:5]
        session_manager.update_candidates(session_id, top5)
        # 去掉 final_content 里可能混入的 JSON 片段，只保留自然语言部分
        summary = re.sub(r'\{.*?"houses".*?\}', '', final_content, flags=re.DOTALL).strip()
        msg = summary[:200] if summary else "为您找到以下符合条件的房源："
        return json.dumps({"message": msg, "houses": top5}, ensure_ascii=False)

    logger.info(f"[{session_id}] done in {int((time.time() - start) * 1000)}ms")
    return final_content
