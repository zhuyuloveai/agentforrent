# 租房 AI Agent

智能租房 AI Agent，基于 Python + FastAPI + Kimi 模型实现。

## 项目结构

```
agentforrent/
├── src/
│   ├── agent/
│   │   ├── core.py          # Agent 核心逻辑（Function Calling）
│   │   ├── prompts.py       # System Prompt 和工具定义
│   │   └── session.py       # 会话管理
│   ├── tools/
│   │   ├── rent_api.py      # 租房 API 封装
│   │   ├── landmark_api.py  # 地标 API 封装
│   │   └── model_client.py  # 模型调用客户端
│   ├── config.py            # 配置文件
│   └── main.py              # FastAPI 入口
├── mock_server.py           # 本地 Mock 租房 API（调试用）
├── requirements.txt         # Python 依赖
├── start.sh                 # 启动 Agent 服务
└── start_all.sh             # 启动 Mock + Agent 服务
```

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `start_all.sh`，设置：
- `USER_ID`: 用户工号（比赛平台注册的工号）
- `KIMI_API_KEY`: Kimi API Key（调试用）
- `DEBUG_MODE`: 是否调试模式（true=使用Kimi，false=使用评测模型）

### 3. 启动服务

```bash
chmod +x start_all.sh
./start_all.sh
```

服务启动后：
- Mock API: http://localhost:8080
- Agent API: http://localhost:8191

### 4. 测试

```bash
# 健康检查
curl http://localhost:8191/health

# 问候测试（0次模型调用）
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test001","message":"你好"}'

# 房源查询测试
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test002","message":"帮我找海淀区两居室，预算8000以内，要近地铁"}'

# 多轮对话测试
curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test003","message":"我想在朝阳区找房，预算10000以内"}'

curl -X POST http://localhost:8191/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test003","message":"要精装修的，而且要有电梯"}'
```

## 核心特性

### 1. 轻量级设计
- 无重型框架依赖（LangChain/AutoGPT）
- 精简的 Function Calling 实现
- 最多 2 次模型调用完成任务

### 2. 智能意图识别
- 简单问候：模板回复（0次模型调用）
- 单轮查询：1-2次模型调用
- 多轮对话：利用上下文，每轮1次模型调用

### 3. 工具调用优化
- 批量查询（page_size=20）
- 会话内缓存
- 智能筛选（先宽松查询，再内存过滤）

### 4. 输出格式
- 普通对话：自然语言文本
- 房源查询完成：JSON 格式
  ```json
  {
    "message": "为您找到以下符合条件的房源：",
    "houses": ["HF_4", "HF_6", "HF_277"]
  }
  ```

## 接口规范

### Agent 对外接口

**POST /api/v1/chat**

请求：
```json
{
  "session_id": "abc123",
  "message": "查询海淀区的房源",
  "model_ip": "xxx.xxx.xx.x"  // 评测环境下发
}
```

响应：
```json
{
  "session_id": "abc123",
  "response": "...",  // 文本或JSON字符串
  "status": "success",
  "tool_results": [],
  "timestamp": 1704067200,
  "duration_ms": 1500
}
```

### 租房 API

Mock Server 提供完整的租房 API 模拟：
- 地标查询：`/api/landmarks/*`
- 房源查询：`/api/houses/*`
- 租房操作：`/api/houses/{house_id}/rent`

详见 `mock_server.py` 和文档 `租房仿真API使用指导.txt`

## 评测优化

### Token 消耗优化
1. 问候类用例：模板回复，0次模型调用
2. 精简 System Prompt（< 500 tokens）
3. 上下文压缩：只保留关键信息

### 时间片优化
1. 减少模型调用次数（最多2次）
2. 批量 API 查询
3. 会话内缓存

### 预估性能
| 用例类型 | 模型调用 | Token | 时间片 | 得分 |
|---------|---------|-------|--------|------|
| Chat    | 0-1     | 0-2k  | 0-1    | 5    |
| Single  | 1-2     | 2k-5k | 2-5    | 10-15|
| Multi   | 2-4     | 5k-15k| 5-15   | 20-30|

## 部署到评测环境

### 1. 修改配置

编辑 `src/config.py`：
```python
DEBUG_MODE = False  # 使用评测模型
RENT_API_BASE = "http://7.225.29.223:8080"  # 内网API
```

### 2. 启动服务

```bash
export USER_ID="你的工号"
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8191
```

### 3. 配置到比赛平台

在比赛平台配置：
- Agent 地址：`http://localhost:8191`
- 监听端口：`8191`

## 开发说明

### 添加新工具

1. 在 `src/tools/rent_api.py` 添加函数
2. 在 `src/agent/prompts.py` 的 `TOOLS` 添加定义
3. 在 `src/agent/core.py` 的 `TOOL_HANDLERS` 注册

### 调试技巧

```python
# 直接调用 Agent 核心逻辑
import asyncio
from src.agent.core import run

async def test():
    result = await run('test_session', '你的测试消息')
    print(result)

asyncio.run(test())
```

### Mock Server 数据

Mock Server 生成 500 套模拟房源：
- 覆盖北京 10 个行政区
- 价格 500-25000 元/月
- 整租/合租各 50%
- 90% 可租，5% 已租，5% 下架

## 常见问题

### Q: Kimi API 连接失败？
A: 检查网络连接和 API Key，或设置 `DEBUG_MODE=false` 使用评测模型。

### Q: 租房 API 返回 502？
A: 确保 Mock Server 已启动（端口 8080），或检查内网 API 连通性。

### Q: 多轮对话上下文丢失？
A: 确保使用相同的 `session_id`，Agent 会自动管理上下文。

### Q: 房源数据重复执行用例后查不到？
A: 调用 `POST /api/houses/init` 重置房源状态。

## License

MIT
