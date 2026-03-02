"""FastAPI 入口：POST /api/v1/chat"""
import time
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.agent import core
from src.tools.rent_api import init_houses
from src.config import AGENT_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="租房 AI Agent")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model_ip: str = None


@app.post("/api/v1/chat")
async def chat(req: ChatRequest):
    start = time.time()
    try:
        response = await core.run(
            session_id=req.session_id,
            message=req.message,
            model_ip=req.model_ip,
        )
        duration_ms = int((time.time() - start) * 1000)
        return {
            "session_id": req.session_id,
            "response": response,
            "status": "success",
            "tool_results": [],
            "timestamp": int(time.time()),
            "duration_ms": duration_ms,
        }
    except Exception as e:
        logger.exception(f"[{req.session_id}] error: {e}")
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


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=AGENT_PORT, reload=False)
