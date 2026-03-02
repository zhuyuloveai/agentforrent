"""FastAPI 入口：POST /api/v1/chat"""
import json
import time
import logging
import datetime
import pathlib
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agent import core
from src.agent.tracer import RunTracer
from src.tools.rent_api import init_houses
from src.config import AGENT_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="租房 AI Agent")

# ── 日志目录 ──────────────────────────────────────────────
_LOG_DIR = pathlib.Path("logs")
_TRACE_DIR = _LOG_DIR / "traces"
_LOG_DIR.mkdir(exist_ok=True)
_TRACE_DIR.mkdir(exist_ok=True)
_QUESTION_LOG = _LOG_DIR / "questions.jsonl"

# 每个 session_id 已出现的轮次计数
_session_turn: dict[str, int] = {}


def _current_turn(session_id: str) -> int:
    """返回该 session 当前是第几轮（从1开始），同时递增计数。"""
    _session_turn[session_id] = _session_turn.get(session_id, 0) + 1
    return _session_turn[session_id]


def _record_question(session_id: str, turn: int, message: str, model_ip: str | None) -> None:
    """将本次请求的题目信息追加写入 logs/questions.jsonl"""
    entry = {
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": session_id,
        "turn": turn,
        "is_new_session": turn == 1,
        "message": message,
        "model_ip": model_ip,
    }
    try:
        with _QUESTION_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"题目记录写入失败: {e}")


def _save_trace(tracer: RunTracer) -> None:
    """将 trace 写入 logs/traces/{session_id}_t{turn}.json"""
    fname = _TRACE_DIR / f"{tracer.session_id}_t{tracer.turn}.json"
    try:
        with fname.open("w", encoding="utf-8") as f:
            json.dump(tracer.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"trace 写入失败: {e}")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model_ip: str = None


@app.post("/api/v1/chat")
async def chat(req: ChatRequest):
    turn = _current_turn(req.session_id)
    _record_question(req.session_id, turn, req.message, req.model_ip)
    tracer = RunTracer(session_id=req.session_id, turn=turn, message=req.message)
    start = time.time()
    try:
        result = await core.run(
            session_id=req.session_id,
            message=req.message,
            model_ip=req.model_ip,
            tracer=tracer,
        )
        duration_ms = int((time.time() - start) * 1000)
        _save_trace(tracer)
        return {
            "session_id": req.session_id,
            "response": result["response"],
            "status": "success",
            "tool_results": result["tool_results"],
            "timestamp": int(time.time()),
            "duration_ms": duration_ms,
        }
    except Exception as e:
        logger.exception(f"[{req.session_id}] error: {e}")
        tracer.record_error(str(e))
        _save_trace(tracer)
        duration_ms = int((time.time() - start) * 1000)
        return JSONResponse(
            status_code=500,
            content={
                "session_id": req.session_id,
                "response": "抱歉，处理您的请求时出现了问题，请稍后重试。",
                "status": "error",
                "tool_results": [],
                "timestamp": int(time.time()),
                "duration_ms": duration_ms,
            },
        )


@app.post("/api/v1/init")
async def init(request: Request):
    """手动触发房源数据重置（调试用）"""
    body = await request.json()
    session_id = body.get("session_id", "")
    result = await init_houses()
    return {"session_id": session_id, "result": result}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/traces")
async def list_traces(last: int = 20):
    """列出最近的 trace 文件摘要（按修改时间倒序）"""
    files = sorted(_TRACE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for f in files[:last]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            summary = data.get("summary", {})
            result.append({
                "file": f.name,
                "session_id": data.get("session_id"),
                "turn": data.get("turn"),
                "message": data.get("message"),
                "total_duration_ms": data.get("total_duration_ms"),
                "llm_call_count": summary.get("llm_call_count"),
                "tool_call_count": summary.get("tool_call_count"),
                "total_tokens": summary.get("total_tokens"),
                "houses_count": summary.get("houses_count"),
                "diagnosis": summary.get("diagnosis"),
            })
        except Exception:
            result.append({"file": f.name, "error": "parse error"})
    return {"count": len(result), "traces": result}


@app.get("/api/v1/traces/{session_id}")
async def get_trace(session_id: str):
    """获取指定 session 的所有轮次完整 trace"""
    files = sorted(_TRACE_DIR.glob(f"{session_id}_t*.json"))
    if not files:
        return JSONResponse(status_code=404, content={"error": f"no traces for session {session_id}"})
    turns = []
    for f in files:
        try:
            turns.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            turns.append({"file": f.name, "error": "parse error"})
    return {"session_id": session_id, "turn_count": len(turns), "turns": turns}


@app.get("/api/v1/questions")
async def list_questions(session_id: str = None, last: int = 50):
    """查看记录的题目。session_id 过滤，last 控制返回最近条数（默认50）"""
    if not _QUESTION_LOG.exists():
        return {"total": 0, "records": []}
    records = []
    with _QUESTION_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if session_id is None or entry.get("session_id") == session_id:
                    records.append(entry)
            except Exception:
                pass
    records = records[-last:]
    # 统计 session 分组
    sessions: dict[str, list] = {}
    for r in records:
        sid = r["session_id"]
        sessions.setdefault(sid, []).append(r["message"])
    return {
        "total": len(records),
        "session_count": len(sessions),
        "sessions": [
            {"session_id": sid, "turns": len(msgs), "messages": msgs}
            for sid, msgs in sessions.items()
        ],
    }


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=AGENT_PORT, reload=False)
