import os
from dotenv import load_dotenv

load_dotenv()

# 用户工号
USER_ID = os.getenv("USER_ID", "z00881489")

# 租房仿真 API
RENT_API_BASE = os.getenv("RENT_API_BASE", "http://localhost:8080")

# Agent 服务端口
AGENT_PORT = int(os.getenv("AGENT_PORT", "8191"))

# 本地调试用模型配置（贴近比赛环境的 Qwen 系列模型）
# 正式评测时 model_ip 由判题器下发，本段配置不生效
DEBUG_BASE_URL = os.getenv("DEBUG_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
DEBUG_API_KEY = os.getenv("DEBUG_API_KEY", "sk-c215a6597a284c9ca699f57aa6c0646e")
DEBUG_MODEL = os.getenv("DEBUG_MODEL", "qwen3.5-27b")

# 是否关闭 Qwen thinking 模式（节省 token，推荐 true）
DISABLE_THINKING = os.getenv("DISABLE_THINKING", "true").lower() == "true"

# 模型调用端口（评测环境）
MODEL_PORT = 8888

# 模型调用接口版本（v1=计入评测统计，需Session-ID；v2=不计统计，调测用）
MODEL_API_VERSION = os.getenv("MODEL_API_VERSION", "v1")

# 评测模型调用超时时间（秒）
MODEL_TIMEOUT = float(os.getenv("MODEL_TIMEOUT", "120"))

# 评测模型最大输出 token 数（限制输出长度，避免超时；0=不限制）
MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "1024"))

# 评测模型调用温度
MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.3"))

# 是否调试模式（true=本地 Qwen，false=使用评测模型）
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
