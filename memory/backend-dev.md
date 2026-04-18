# Backend Developer Memory

Персональная память backend-dev агента (Sonnet 4.6). Хранит контекст работы с API, БД, бизнес-логикой: схемы данных, принятые паттерны, известные баги и их обходы, используемые библиотеки и их версии, соглашения по структуре сервисов.

## Sessions

### 2026-04-18 — HEALTH-1 (feature/health)

Создан минимальный Express API в worktree `/mnt/d/orchkerstr-feature-health/`.

**Файлы:**
- `package.json` — name `orchkerstr-health`, version `0.1.0`, script `start: "node server.js"`, единственная зависимость `express: ^4.19.2`.
- `server.js` — Express app, `GET /health` -> `{status: "ok", timestamp: new Date().toISOString()}`, порт `process.env.PORT || 3000`.

**Решения / стиль:**
- Минимализм: без helmet/cors/morgan/логов/комментариев — только то, что в ТЗ.
- `timestamp` генерируется на каждый запрос через `new Date().toISOString()` (UTC, ISO-8601).
- `res.json(...)` (Express сам ставит `Content-Type: application/json`).

**Зависимости (npm install):**
- express `^4.19.2` (установлено 68 пакетов, 0 vulnerabilities).

**Проверка:**
- `npm install` — OK, 0 vulnerabilities.
- `curl http://localhost:3000/health` -> `{"status":"ok","timestamp":"2026-04-18T07:18:13.540Z"}`.

**Коммит:** не делал — тимлид закоммитит после ревью.

### 2026-04-18 — B-UI-1 (communication/server.py)

Добавил форвардинг сообщений от UI в tmux-сессию тимлида.

**Файл:** `/mnt/d/orchkerstr/communication/server.py` — только этот один изменён.

**Формат триггера:** входящее WS-сообщение `{"type":"message","from":"ui","to":"<agent>","content":"..."}`. Триггер на `sender == "ui"` (sender берётся из `register` frame, а не из поля `from` внутри message — это намеренно: защита от подмены). Обычный роутинг + duckdb-лог остаются без изменений, форвард идёт ДОПОЛНИТЕЛЬНО.

**Конфигурация target:**
- Новый параметр конструктора `lead_tmux_target: str | None = None` (дефолт-таргет).
- Новый параметр `agent_tmux_targets: dict[str, str] | None = None` (per-agent override; переиспользовал имя/тип из `RecoveryManager` для единообразия).
- Резолвер: `agent_tmux_targets.get(to) or lead_tmux_target`. Если оба None → silent skip.

**Эскейпинг (важное решение):**
- Использую `tmux send-keys -t <target> -l -- <line>` (флаг `-l` = literal, `--` = end-of-flags). С `-l` tmux НЕ интерпретирует `;`, `{`, `$`, key-names типа `Enter`/`C-c` — всё уходит как обычный текст. Это закрывает инъекционный риск от UI.
- Перевод строки в контенте: разбиваю `content.split("\n")`, каждая строка шлётся отдельным `send-keys -l`, между ними и в конце — отдельный `send-keys Enter` (без `-l`, чтобы tmux прожал именно Enter). Без такого разбиения `\n` внутри literal-строки не сработал бы как нажатие Enter.
- В конце всегда шлём Enter — чтобы Claude Code принял команду.

**Поведение при отсутствии tmux:**
- `FileNotFoundError` при `asyncio.create_subprocess_exec("tmux", ...)` → `return False` → форвард тихо пропускается, сервер продолжает работу.
- Несуществующая tmux-сессия → `tmux` выходит с ненулевым кодом, мы это игнорируем (silent).
- Любое исключение в `communicate()` тоже глушится. Принцип: форвард — best-effort, основная логика (роутинг + лог) никогда не должна падать из-за tmux.
- `print`/`logging` не использую (по ТЗ); не заводил `ErrorHandler` — это best-effort операция, не ошибка агента.

**Стиль:**
- `from __future__ import annotations`, PEP 604 unions, type hints.
- `asyncio.create_subprocess_exec` с list-args (никакого shell).
- Вспомогательные методы `_resolve_tmux_target`, `_forward_to_tmux`, `_tmux_send` — приватные.

**Smoke-тест (прошёл локально):**
1. `tmux new-session -d -s orch-test -x 200 -y 50 'bash -c "while true; do read line; echo GOT:\$line; done"'`.
2. Сервер стартанул с `lead_tmux_target="orch-test:0"` и `agent_tmux_targets={"opus": "orch-test:0"}`.
3. Клиент `ui` отправил `{"type":"message","to":"opus","content":"hello"}` и `{"type":"message","to":"opus","content":"line1\nline2"}`.
4. `tmux capture-pane -p` показал `GOT:hello`, `GOT:line1`, `GOT:line2` — обе однострочный и многострочный кейсы работают.
5. Дополнительно проверил: сервер без `lead_tmux_target` и сервер с несуществующей сессией — оба не падают, форвард тихо skipается.

**Нюансы:**
- Триггер на `sender == "ui"` читается из WebSocket registration, не из `msg["from"]`. Т.е. подделать `from: "ui"` с клиента нельзя, надо зарегистрироваться как `"ui"`.
- `content` может быть не-строкой (например, dict) — обёрнуто в `isinstance(content, str)`.
