"""运行追踪器：记录单次 Agent run() 的完整执行过程，用于调试分析。

每次 /api/v1/chat 调用都会生成一个 RunTracer，保存到 logs/traces/ 目录，
供事后分析定位问题出在哪个阶段：模型理解、工具调用、结果解析。
"""
import json
import math
import time
from typing import Optional


def _tokens_to_slices(total_tokens: int) -> int:
    """按比赛公式将单次模型调用的 token 数换算为时间片（向上取整）。
    公式：t = 1 + max(0, (n - 1000)) × 0.3
    """
    return math.ceil(1 + max(0, (total_tokens - 1000) * 0.3))


class RunTracer:
    def __init__(self, session_id: str, turn: int, message: str):
        self.session_id = session_id
        self.turn = turn
        self.message = message
        self._start = time.time()

        self.is_simple_chat = False
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.final_raw_content = ""
        self.parse_method = "none"       # json_direct / json_regex / fallback_tools / plain_text / none
        self.houses_returned: list[str] = []
        self.error: Optional[str] = None

    # ── 记录 API ──────────────────────────────────────────────

    def mark_simple_chat(self) -> None:
        self.is_simple_chat = True

    def begin_llm_call(self, round_num: int, messages_count: int, forced: bool = False) -> dict:
        """开始计时一次 LLM 调用，返回上下文 ctx，传给 end_llm_call。"""
        return {
            "round_num": round_num,
            "forced": forced,
            "messages_count": messages_count,
            "_t": time.time(),
        }

    def end_llm_call(self, ctx: dict, response: dict) -> None:
        """记录 LLM 调用结果和耗时。"""
        duration_ms = int((time.time() - ctx["_t"]) * 1000)
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = response.get("usage", {})
        tool_calls = msg.get("tool_calls") or []

        self.llm_calls.append({
            "round_num": ctx["round_num"],
            "forced": ctx["forced"],
            "messages_count": ctx["messages_count"],
            "duration_ms": duration_ms,
            "finish_reason": choice.get("finish_reason", "unknown"),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "tool_calls_requested": [tc["function"]["name"] for tc in tool_calls],
            # 只保留前500字符，避免文件过大
            "raw_content": (msg.get("content") or "")[:500],
        })

    def record_tool_call(
        self,
        round_num: int,
        name: str,
        arguments: dict,
        success: bool,
        duration_ms: int,
        result_str: str,
    ) -> None:
        self.tool_calls.append({
            "round_num": round_num,
            "name": name,
            "arguments": arguments,
            "success": success,
            "duration_ms": duration_ms,
            "result_summary": _summarize_tool_result(name, result_str),
        })

    def record_output(self, raw_content: str, parse_method: str, houses: list[str]) -> None:
        self.final_raw_content = raw_content[:1000]
        self.parse_method = parse_method
        self.houses_returned = houses

    def record_error(self, error: str) -> None:
        self.error = error

    # ── 序列化 / 持久化 ──────────────────────────────────────

    def save(self, trace_dir: str = "logs/traces") -> None:
        """将 trace 写入 {trace_dir}/{session_id}_t{turn}.json"""
        import pathlib
        p = pathlib.Path(trace_dir)
        p.mkdir(parents=True, exist_ok=True)
        fname = p / f"{self.session_id}_t{self.turn}.json"
        with fname.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        total_ms = int((time.time() - self._start) * 1000)
        total_tokens = sum(c.get("total_tokens", 0) for c in self.llm_calls)
        total_slices = sum(_tokens_to_slices(c.get("total_tokens", 0)) for c in self.llm_calls)
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "message": self.message,
            "total_duration_ms": total_ms,
            "is_simple_chat": self.is_simple_chat,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "final_raw_content": self.final_raw_content,
            "parse_method": self.parse_method,
            "houses_returned": self.houses_returned,
            "error": self.error,
            "summary": {
                "llm_call_count": len(self.llm_calls),
                "tool_call_count": len(self.tool_calls),
                "total_tokens": total_tokens,
                "time_slices": total_slices,
                "houses_count": len(self.houses_returned),
                "diagnosis": _diagnose(self),
            },
        }


# ── 内部辅助函数 ─────────────────────────────────────────────

def _summarize_tool_result(name: str, result_str: str) -> str:
    """从工具返回结果中提取关键信息摘要，用于 trace 展示。"""
    try:
        data = json.loads(result_str)
        if "error" in data:
            return f"ERROR: {data['error']}"
        d = data.get("data", data)
        if isinstance(d, dict):
            items = d.get("items", [])
            if isinstance(items, list):
                ids = [it.get("house_id", it.get("id", "?")) for it in items[:5]]
                total = d.get("total", len(items))
                return f"total={total}, sample={ids}"
            hid = d.get("house_id") or d.get("id")
            if hid:
                return f"house_id={hid} status={d.get('status', '')}"
        return str(d)[:120]
    except Exception:
        return result_str[:120]


def _diagnose(t: RunTracer) -> list[str]:
    """自动诊断常见问题，返回问题列表。"""
    issues: list[str] = []

    if t.is_simple_chat:
        return ["OK: simple_chat 模板回复，无LLM调用"]

    if not t.llm_calls:
        issues.append("ERROR: 无LLM调用记录，Agent未正常运行")
        return issues

    if t.error:
        issues.append(f"ERROR: 运行时异常 → {t.error}")

    # 结果解析
    if t.parse_method == "none":
        issues.append("CRIT: 模型输出无JSON结构，houses为空，该用例0分")
    elif t.parse_method == "fallback_tools":
        issues.append("WARN: 模型未输出JSON，回退工具结果提取houses，可能遗漏或不准确")
    elif t.parse_method == "plain_text":
        issues.append("INFO: 纯文本回复（Chat类或无房源查询）")

    # 工具调用失败
    for ft in [tc for tc in t.tool_calls if not tc["success"]]:
        issues.append(f"ERROR: 工具调用失败 {ft['name']} args={ft['arguments']}")

    # 强制回复（超出工具轮数）
    if any(c.get("forced") for c in t.llm_calls):
        issues.append("WARN: 超出最大工具调用轮数，触发强制回复，可能漏返房源")

    # token消耗
    for c in t.llm_calls:
        tok = c.get("total_tokens", 0)
        if tok > 5000:
            issues.append(f"WARN: round{c['round_num']} total_tokens={tok}，消耗偏高")

    # 有工具但无houses
    if t.tool_calls and not t.houses_returned:
        issues.append("WARN: 有工具调用但最终houses为空，检查模型输出格式")

    # finish_reason 异常
    for c in t.llm_calls:
        if c.get("finish_reason") == "length":
            issues.append(f"WARN: round{c['round_num']} finish_reason=length，输出被截断")

    if not issues:
        issues.append("OK: 无明显问题")
    return issues
