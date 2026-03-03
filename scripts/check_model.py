"""临时脚本：测试 API key 和模型可用性"""
import httpx
import json
import os

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# 1. 查询可用模型
print("=== 查询可用模型 ===")
try:
    r = httpx.get(f"{BASE_URL}/models", headers=HEADERS, timeout=15.0)
    print(f"Status: {r.status_code}")
    data = r.json()
    models = [m["id"] for m in data.get("data", [])]
    print("Models:", json.dumps(models[:20], indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")

# 2. 用 Qwen3.5-27B 发一条最简单的请求
print("\n=== 测试 Qwen3.5-27B 调用 ===")
try:
    r = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={
            "model": "Qwen3.5-27B",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10,
        },
        timeout=30.0,
    )
    print(f"Status: {r.status_code}")
    print("Body:", r.text[:500])
except Exception as e:
    print(f"Error: {e}")
