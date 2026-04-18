#!/bin/bash
set -e

echo "🚀 Запуск ClaudeOrch..."

# 1. Создать .claudeorch если нет
mkdir -p .claudeorch

# 2. Запустить Python оркестратор в фоне
echo "▶ Запуск оркестратора..."
python3 core/main.py &
ORCH_PID=$!
echo $ORCH_PID > .claudeorch/orch.pid
sleep 2

# 3. Запустить WebSocket сервер в фоне
echo "▶ Запуск WebSocket сервера..."
python3 -c "
import asyncio
from communication.server import CommunicationServer
async def main():
    s = CommunicationServer()
    await s.start()
    print('WebSocket server running on :8765')
    await asyncio.Future()
asyncio.run(main())
" &
WS_PID=$!
echo $WS_PID > .claudeorch/ws.pid
sleep 2

# 4. Проверить что сервисы запустились
if kill -0 $ORCH_PID 2>/dev/null; then
    echo "✓ Оркестратор запущен (PID: $ORCH_PID)"
else
    echo "✗ Оркестратор не запустился"
    exit 1
fi

if kill -0 $WS_PID 2>/dev/null; then
    echo "✓ WebSocket сервер запущен (PID: $WS_PID)"
else
    echo "✗ WebSocket сервер не запустился"
    exit 1
fi

# 5. Запустить Claude Code с Channels в tmux
echo "▶ Запуск Claude Code..."
tmux new-session -d -s claudeorch \
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude \
    --model claude-opus-4-7 \
    --dangerously-skip-permissions \
    --channels plugin:telegram@claude-plugins-official"
echo "✓ Claude Code запущен в tmux сессии 'claudeorch'"

# 6. Запустить UI
echo "▶ Запуск UI..."
cd ui && npm run tauri dev &
UI_PID=$!
cd ..
echo $UI_PID > .claudeorch/ui.pid

echo ""
echo "✅ ClaudeOrch запущен!"
echo "   Claude Code: tmux attach -t claudeorch"
echo "   WebSocket: ws://localhost:8765"
echo "   REST API: http://localhost:8766/agents"
echo "   Остановить: ./stop.sh"
