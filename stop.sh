#!/bin/bash

echo "🛑 Остановка ClaudeOrch..."

# Остановить UI (npm + дочерние vite/cargo/tauri)
if [ -f .claudeorch/ui.pid ]; then
    UI_PID=$(cat .claudeorch/ui.pid)
    kill $UI_PID 2>/dev/null
    pkill -f "/mnt/d/orchkerstr/ui/node_modules" 2>/dev/null
    pkill -f "cargo run --no-default-features.*orchkerstr" 2>/dev/null
    pkill -f "target/debug/ui" 2>/dev/null
    echo "✓ UI остановлен"
    rm .claudeorch/ui.pid
fi

# Остановить оркестратор (вместе с встроенным WebSocket сервером)
if [ -f .claudeorch/orch.pid ]; then
    ORCH_PID=$(cat .claudeorch/orch.pid)
    kill $ORCH_PID 2>/dev/null && echo "✓ Оркестратор остановлен"
    rm .claudeorch/orch.pid
fi

# Остановить tmux сессию Claude Code
tmux kill-session -t claudeorch 2>/dev/null && echo "✓ Claude Code остановлен"

echo "✅ ClaudeOrch остановлен"
