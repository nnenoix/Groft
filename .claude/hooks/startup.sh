#!/bin/bash
# Автоматически при старте каждой Claude Code сессии.
# Проверяем что WebSocket сервер ClaudeOrch доступен.
if curl -sSf http://localhost:8766/agents > /dev/null 2>&1; then
    echo "✓ ClaudeOrch WebSocket сервер доступен"
else
    echo "⚠ ClaudeOrch WebSocket сервер недоступен"
fi
