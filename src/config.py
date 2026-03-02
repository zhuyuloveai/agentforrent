import os

# 用户工号
USER_ID = os.getenv("USER_ID", "z00881489")

# 租房仿真 API
RENT_API_BASE = os.getenv("RENT_API_BASE", "http://localhost:8080")

# Agent 服务端口
AGENT_PORT = int(os.getenv("AGENT_PORT", "8191"))

# Kimi 调试用配置（正式评测时 model_ip 由判题器下发）
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

# 模型调用端口（评测环境）
MODEL_PORT = 8888

# 是否调试模式（使用 Kimi 而非评测模型）
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
