#!/bin/bash

echo "🛑 Остановка ClaudeOrch..."

# Остановить UI
if [ -f .claudeorch/ui.pid ]; then
    UI_PID=$(cat .claudeorch/ui.pid)
    kill $UI_PID 2>/dev/null && echo "✓ UI остановлен"
    rm .claudeorch/ui.pid
fi

# Остановить WebSocket сервер
if [ -f .claudeorch/ws.pid ]; then
    WS_PID=$(cat .claudeorch/ws.pid)
    kill $WS_PID 2>/dev/null && echo "✓ WebSocket сервер остановлен"
    rm .claudeorch/ws.pid
fi

# Остановить оркестратор
if [ -f .claudeorch/orch.pid ]; then
    ORCH_PID=$(cat .claudeorch/orch.pid)
    kill $ORCH_PID 2>/dev/null && echo "✓ Оркестратор остановлен"
    rm .claudeorch/orch.pid
fi

# Остановить tmux сессию Claude Code
tmux kill-session -t claudeorch 2>/dev/null && echo "✓ Claude Code остановлен"

echo "✅ ClaudeOrch остановлен"
