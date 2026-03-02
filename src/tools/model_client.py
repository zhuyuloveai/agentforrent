"""模型调用客户端"""
import httpx
from typing import List, Dict, Any, Optional
from src.config import (
    DEBUG_MODE,
    KIMI_BASE_URL,
    KIMI_API_KEY,
    KIMI_MODEL,
    MODEL_PORT,
)


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
    ) -> dict:
        """调用模型进行对话补全"""
        if self.debug_mode:
            # 调试模式：使用 Kimi
            return await self._call_kimi(messages, tools, temperature)
        else:
            # 评测模式：使用判题器提供的模型
            return await self._call_judge_model(messages, tools, temperature)

    async def _call_kimi(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
    ) -> dict:
        """调用 Kimi 模型（调试用）"""
        headers = {
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": KIMI_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{KIMI_BASE_URL}/chat/completions",
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
            "model": "",  # 评测环境模型可以为空
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
