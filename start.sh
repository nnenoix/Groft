#!/bin/bash
set -e

echo "🚀 Запуск ClaudeOrch..."

# 1. Создать .claudeorch если нет
mkdir -p .claudeorch

# 2. Запустить Python оркестратор (хостит WebSocket сервер на :8765)
echo "▶ Запуск оркестратора..."
python3 core/main.py &
ORCH_PID=$!
echo $ORCH_PID > .claudeorch/orch.pid
sleep 3

# 3. Проверить что оркестратор жив
if kill -0 $ORCH_PID 2>/dev/null; then
    echo "✓ Оркестратор запущен (PID: $ORCH_PID)"
else
    echo "✗ Оркестратор не запустился"
    exit 1
fi

# 4. Запустить Claude Code с Channels в tmux
echo "▶ Запуск Claude Code..."
tmux new-session -d -s claudeorch \
    "AGENT_NAME=opus CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude \
    --model claude-opus-4-7 \
    --dangerously-skip-permissions \
    --channels plugin:telegram@claude-plugins-official"
echo "✓ Claude Code запущен в tmux сессии 'claudeorch'"
echo "▶ Агенты будут спаунены Opus по запросу через AgentSpawner"
echo "   Мониторинг: tmux list-windows -t claudeorch"

# 5. Запустить UI
echo "▶ Запуск UI..."
( cd ui && npm run tauri dev ) &
UI_PID=$!
echo $UI_PID > .claudeorch/ui.pid

echo ""
echo "✅ ClaudeOrch запущен!"
echo "   Claude Code: tmux attach -t claudeorch"
echo "   WebSocket: ws://localhost:8765"
echo "   REST API: http://localhost:8766/agents"
echo "   Остановить: ./stop.sh"
