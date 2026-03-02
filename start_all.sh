#!/bin/bash
# 启动脚本：同时启动 Mock Server 和 Agent Server

set -e

export USER_ID="z00881489"
export KIMI_API_KEY="sk-h89WVk9jykrKrvl04SdUzvlTqKvFcZ1VFxOPMIpKAU3DyGs2"
export DEBUG_MODE="true"
export RENT_API_BASE="http://localhost:8080"

cd "$(dirname "$0")"

echo "=== 检查依赖 ==="
if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，正在创建..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt -q
fi

echo ""
echo "=== 停止旧进程 ==="
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:8191 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

echo ""
echo "=== 启动 Mock 租房 API (端口 8080) ==="
.venv/bin/python3 -m uvicorn mock_server:app --host 0.0.0.0 --port 8080 > /tmp/mock_server.log 2>&1 &
MOCK_PID=$!
echo "Mock Server PID: $MOCK_PID"

sleep 2

echo ""
echo "=== 启动 Agent 服务 (端口 8191) ==="
.venv/bin/python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8191 > /tmp/agent_server.log 2>&1 &
AGENT_PID=$!
echo "Agent Server PID: $AGENT_PID"

sleep 2

echo ""
echo "=== 健康检查 ==="
if curl -s http://localhost:8080/api/landmarks/stats > /dev/null; then
    echo "✓ Mock Server 运行正常"
else
    echo "✗ Mock Server 启动失败，查看日志: tail -f /tmp/mock_server.log"
    exit 1
fi

if curl -s http://localhost:8191/health > /dev/null; then
    echo "✓ Agent Server 运行正常"
else
    echo "✗ Agent Server 启动失败，查看日志: tail -f /tmp/agent_server.log"
    exit 1
fi

echo ""
echo "=== 服务已启动 ==="
echo "Mock API:  http://localhost:8080"
echo "Agent API: http://localhost:8191"
echo ""
echo "日志文件："
echo "  Mock:  tail -f /tmp/mock_server.log"
echo "  Agent: tail -f /tmp/agent_server.log"
echo ""
echo "测试命令："
echo "  ./test_quick.sh"
echo ""
echo "停止服务："
echo "  kill $MOCK_PID $AGENT_PID"
echo "  或者: lsof -ti:8080,8191 | xargs kill -9"
echo ""
echo "按 Ctrl+C 停止..."

# 等待用户中断
trap "echo ''; echo '正在停止服务...'; kill $MOCK_PID $AGENT_PID 2>/dev/null; exit 0" INT TERM
wait

