"""模型调用客户端"""
import asyncio
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from src.config import (
    DEBUG_MODE,
    DEBUG_BASE_URL,
    DEBUG_API_KEY,
    DEBUG_MODEL,
    DISABLE_THINKING,
    MODEL_PORT,
    MODEL_API_VERSION,
    MODEL_TIMEOUT,
    MODEL_MAX_TOKENS,
    MODEL_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class ModelClient:
    def __init__(self, model_ip: str = None, session_id: str = None):
        self.model_ip = model_ip
        self.session_id = session_id
        self.debug_mode = DEBUG_MODE

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> dict:
        """调用模型进行对话补全，支持自动重试"""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                if self.debug_mode:
                    return await self._call_debug_model(messages, tools, temperature)
                else:
                    return await self._call_judge_model(messages, tools, temperature)
            except httpx.HTTPStatusError as e:
                # 5xx 服务端错误（如 504 Gateway Timeout）才重试，4xx 不重试
                if e.response.status_code >= 500:
                    last_exc = e
                    if attempt < max_retries:
                        wait = attempt * 5
                        logger.warning(f"Model call HTTP {e.response.status_code} (attempt {attempt}/{max_retries}), retrying in {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Model call failed after {max_retries} attempts: {e}")
                else:
                    raise
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.RemoteProtocolError,
                httpx.ProxyError,
            ) as e:
                last_exc = e
                if attempt < max_retries:
                    wait = attempt * 3
                    logger.warning(f"Model call failed (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Model call failed after {max_retries} attempts: {e}")
        raise last_exc

    async def _call_debug_model(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
    ) -> dict:
        """调用本地调试模型（DashScope OpenAI 兼容接口，默认 Qwen3.5-27B）"""
        headers = {
            "Authorization": f"Bearer {DEBUG_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DEBUG_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        # 关闭 Qwen thinking 模式，避免 <think> tokens 消耗配额
        if DISABLE_THINKING:
            payload["enable_thinking"] = False

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            r = await client.post(
                f"{DEBUG_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            return r.json()

    async def _call_judge_model(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
    ) -> dict:
        """调用判题器提供的模型（评测用）"""
        if not self.model_ip:
            raise ValueError("model_ip is required in evaluation mode")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-placeholder",
        }
        if self.session_id:
            headers["Session-ID"] = self.session_id

        payload = {
            "model": "",  # 评测环境模型名由判题器决定
            "messages": messages,
            "temperature": MODEL_TEMPERATURE,
            "stream": False,
            "tools": tools if tools else [],
        }
        if MODEL_MAX_TOKENS > 0:
            payload["max_tokens"] = MODEL_MAX_TOKENS

        url = f"http://{self.model_ip}:{MODEL_PORT}/{MODEL_API_VERSION}/chat/completions"
        async with httpx.AsyncClient(timeout=MODEL_TIMEOUT) as client:
            try:
                t0 = asyncio.get_event_loop().time()
                r = await client.post(url, json=payload, headers=headers)
                elapsed = asyncio.get_event_loop().time() - t0
                r.raise_for_status()
                logger.info(f"Judge model OK in {elapsed:.1f}s (session={self.session_id})")
                return r.json()
            except Exception as e:
                truncated_msgs = [
                    {
                        "role": m.get("role"),
                        "content": (str(m.get("content", ""))[:80] + "…") if len(str(m.get("content", ""))) > 80 else m.get("content"),
                    }
                    for m in payload.get("messages", [])
                ]
                log_payload = {**payload, "messages": truncated_msgs}
                logger.error(
                    f"Judge model request failed: {e}\n"
                    f"  URL: POST {url}\n"
                    f"  Payload: {json.dumps(log_payload, ensure_ascii=False, indent=2)}"
                )
                raise
