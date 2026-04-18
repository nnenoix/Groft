# Code Review: Integration

Дата: 2026-04-18
Ревьюер: integration-reviewer

## Критично (блокирует работу)

1. **`CommunicationServer.lead_tmux_target` и `agent_tmux_targets` нигде не прокидываются.**
   `core/main.py:23` инстанцирует `CommunicationServer()` без аргументов, поэтому `_lead_tmux_target is None` и `_agent_tmux_targets = {}`. В итоге ветка `if sender == "ui": await self._forward_to_tmux(to, content)` (server.py:218, :281) всегда silent-skipается — **чат из UI к Opus физически не доходит**. При этом `ChatInput` → `App.handleChatSubmit` → `sendMessage({to:"opus"})` (App.tsx:112-119) — это основной путь команд пользователя.

2. **Tmux target watchdog'а никогда не регистрируется.**
   `AgentWatchdog.register_agent(name, tmux_target)` вызывается только из `RecoveryManager.restore_session()` (recovery_manager.py:97), а `restore_session` из `main.py` не вызывается ни разу. `main.py:48` зовёт только `recovery_manager.initialize()`, `agent_watchdog.start()` — запуская пустой monitor loop. Watchdog стартует, но `_agents = {}` навсегда. Результат: ни snapshot'ов, ни wake-up/restart callbacks.

3. **Несоответствие имени tmux-сессии.**
   `start.sh:26` создаёт сессию `claudeorch` с одним окном — Opus сидит в `claudeorch:0`. Watchdog ожидает `tmux_target` вида `session:window.pane`, но нигде не задано соответствие `backend-dev → claudeorch:?` и т.п. Даже если бы `restore_session()` вызывался — `_agent_tmux_targets` в RecoveryManager тоже пустой (main.py инстанцирует `RecoveryManager(...)` без `agent_tmux_targets=`). Агенты backend-dev / frontend-dev / tester / reviewer вообще не имеют собственных tmux-окон в `start.sh`.

4. **UI → server: `status` не форвардится от Opus/агентов к UI.**
   Server форвардит `status` только когда клиент-отправитель шлёт его (server.py:242-245) — и получатель всегда `UI_SINK_AGENT="ui"`. Но агенты-исполнители в текущей схеме Python не существуют как WS-клиенты (Python подключает только `orchestrator` из `main.py:26`); Opus запускается как Claude Code в tmux, а не как WS-клиент. Поэтому `status`-сообщения никто не шлёт → панель агентов в UI остаётся на моковых "idle" навсегда.

## Важно (нужно исправить)

1. **`SessionManager` из `memory/session_manager.py` — сирота.** Никем не импортируется кроме `memory/__init__.py`. Context-tracking / `/compact` keystroke не интегрированы ни с `ErrorHandler.CONTEXT_OVERFLOW`, ни с `main.py`. Комментарий в `CLAUDE.md` упоминает session_manager как компонент системы.

2. **`ErrorHandler` инстанцирован, но ни один callback не подписан.**
   `main.py:32` вызывает `ErrorHandler()` + `initialize()`, но ни `set_checkpoint_callback`, ни `set_restart_callback`, ни `set_bad_code_callback`, ни `set_compaction_callback` не установлены. При любой ошибке handler логирует событие, но восстановительные действия не срабатывают.

3. **Watchdog callbacks не установлены.** `set_wake_up_callback` / `set_restart_callback` / `set_notification_callback` никогда не вызываются в `main.py`. Даже если бы агенты были зарегистрированы — зависания никак не обрабатывались бы.

4. **UI шлёт `{type:"message", from:"ui", to:"opus"}`, а Opus не WS-клиент.**
   Server route_direct в server.py:250 отправит payload в `_registry["opus"]` — но Opus в tmux не подключается к ws://localhost:8765 самостоятельно (в нашем коде нет ни одной строчки, которая это делает — только `main.py` как `orchestrator`). Поэтому `_route_direct` тихо ничего не сделает (target is None). Рабочий путь должен быть именно `_forward_to_tmux` — см. критический пункт 1.

5. **Имя агента-оркестратора расходится.** `main.py:26` регистрирует `agent_name="orchestrator"`, но server.py:19 использует `SNAPSHOT_SINK_AGENT = "opus"`, UI шлёт `to:"opus"` (App.tsx:116). Никто не слушает под именем `opus`. snapshot forwarding в server._dispatch тоже уйдёт в пустоту.

6. **Stop.sh не останавливает REST (8766) отдельно.** REST запускается внутри оркестратора — ок, но при зомби-процессе uvicorn порт 8766 может остаться. Нет проверки / `pkill -f uvicorn`.

## Замечания (можно улучшить)

1. `stop.sh` не имеет `set -e`, `kill` не ждёт завершения, `rm` делается до проверки что процесс реально умер.

2. `start.sh`: `sleep 3` как способ дождаться оркестратора — хрупко. Лучше polling `curl http://localhost:8766/agents`.

3. Нет retry-политики для WS-подключения в `main.py` — если `CommunicationClient.connect()` упал, оркестратор свалится до `install()` signal handlers.

4. `architecture/interfaces.md`, `architecture/graph.md`, `architecture/decisions.md`, `architecture/design-handoff.md`, `architecture/current-test.md` — читаются только людьми / Opus через tmux, в Python-коде никто их не открывает. Это ок по дизайну (они — рабочие артефакты тимлида), но стоит это явно зафиксировать, чтобы не искать пропавших читателей.

5. `memory/manager.py` читает `architecture/current-task.md` в `get_context`, а `architecture/current-test.md` / `interfaces.md` / `graph.md` / `decisions.md` — нет. Либо добавить их в context, либо пояснить зачем отделено.

6. `UI_SINK_AGENT = "ui"` захардкожен. Если UI задаст другое `agentName` в `useWebSocket` — разорвёт forwarding. Стоит экспортировать как константу и использовать с обеих сторон.

7. `useOrchestrator` принимает `message` от server'а, но server никогда не роутит message обратно UI (UI в `_route_direct` попадает, только если `to:"ui"`; `broadcast` отсекает отправителя). Комментарий в useOrchestrator.ts уже отмечает этот caveat.

8. `TeamCreate` / Agent Teams spawn-логика в Python отсутствует. Согласно CLAUDE.md Opus сам спаунит агентов через Agent Teams — значит Python-оркестратор к этому не имеет отношения, и роль `core/main.py` сводится к надёжности-слою. Это корректно, но нигде не написано явно и создаёт ощущение «сиротства» модулей.

## Хорошо сделано

- Чёткий WS-контракт: 5 типов (`register`, `message`, `broadcast`, `snapshot`, `status`) с симметрией между `client.py` и `server.py`.
- Первый frame = `register` enforced с обеих сторон (server close 1008, UI шлёт в onopen).
- DuckDB-логирование во всех модулях с единым паттерном (`.claudeorch/*.duckdb`), под одним lock.
- `CommunicationServer` идемпотентен (`_started` guard), `AgentWatchdog.start` тоже.
- Teardown в `main.py` с per-step `try/except` — одна ошибка не валит остальные.
- UI-сторона типобезопасно валидирует `status` (`VALID_STATUSES`) и аккуратно нормализует `snapshot` (`terminal` / `lines` / `content`).
- Reconnect-логика в `useWebSocket` корректная: `shouldRunRef`, `connectRef`, `scheduleReconnect`, clean unmount.

---

## Матрица WebSocket-контракта

| Направление | Тип | Server понимает | UI обрабатывает | Opus/WS-клиент | Разрыв |
|---|---|---|---|---|---|
| → server | register | ✓ | ✓ (ws.onopen) | ✓ (client.connect) | — |
| → server | message | ✓ | ✓ (ChatInput) | ✓ (client.send) | см. крит. №1 и №5 |
| → server | broadcast | ✓ | ✗ UI не шлёт | ✓ (client.broadcast) | UI не использует |
| → server | snapshot | ✓ | ✗ UI не шлёт | ✓ (client.snapshot) | — |
| → server | status | ✓ | ✗ UI не шлёт | ✓ (client.status) | — |
| server → | message | — | ✓ (APPEND_LOG) | ✓ (listen yield) | — |
| server → | broadcast | — | ✓ (APPEND_LOG) | ✓ (listen yield) | — |
| server → | snapshot | — | ✓ (APPEND_TERMINAL) | → `opus` (но `opus` не подключён) | крит. №5 |
| server → | status (fwd to UI) | — | ✓ (UPSERT_AGENT_STATUS) | — | агенты status не шлют (см. крит. №4) |

**Разрывов: 4 критичных, 1 незадействованный, 1 mis-named (orchestrator vs opus).**

---

## Модули и их инстанцирование в main.py

| Модуль | Инстанцирован | Запущен | Callbacks подписаны |
|---|---|---|---|
| CommunicationServer | ✓ | ✓ start() | — (без tmux targets) |
| CommunicationClient (as "orchestrator") | ✓ | ✓ connect() | listen() не вызывается |
| CheckpointManager | ✓ | ✓ initialize() | — |
| ProcessGuard | ✓ | ✓ install() | register_agent никогда |
| AgentWatchdog | ✓ | ✓ start() | **ни один** callback |
| ErrorHandler | ✓ | ✓ initialize() | **ни один** callback |
| GitManager | ✓ | ✓ initialize() | — |
| MemoryManager | ✓ | ✓ initialize() | — |
| RecoveryManager | ✓ | ✓ initialize() | `restore_session` не вызывается |
| SessionManager | ✗ | — | **сирота** |
