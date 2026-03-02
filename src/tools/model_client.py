"""模型调用客户端"""
import asyncio
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

        headers = {"Content-Type": "application/json"}
        if self.session_id:
            headers["Session-ID"] = self.session_id

        payload = {
            "model": "",  # 评测环境模型名由判题器决定
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        url = f"http://{self.model_ip}:{MODEL_PORT}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
