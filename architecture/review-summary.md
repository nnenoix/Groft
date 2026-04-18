# Code Review: Summary

Дата: 2026-04-18
Источники: `review-core.md`, `review-ui.md`, `review-integration.md`

## Корневой диагноз

**Инфраструктура собрана, но не провязана.** Все три ревьюера независимо пришли к одному выводу: отдельные модули (checkpoint / guard / watchdog / error / recovery / server / client / git / memory, плюс UI со стором и хуками) реализованы аккуратно — но `core/main.py` делает только `__init__ + initialize`, без привязки callback-ов и без конфигурации tmux-таргетов. В итоге WS-контракт симметричен на уровне типов сообщений, но ни одно end-to-end-взаимодействие не доезжает до получателя.

Вторая корневая проблема: **модель watchdog'а (tmux capture-pane) не совпадает с моделью Agent Teams** — backend-dev / frontend-dev / tester / reviewer в реальности спаунятся Opus'ом внутри его же Claude Code сессии, а не в отдельных tmux-окнах. `start.sh` создаёт только одно окно `claudeorch:0` для Opus. Ожидание tmux-адресуемых агентов — архитектурное несоответствие.

---

## P0 — блокируют первый реальный тест

Эти три блока нужно закрыть одним коммитом в `core/main.py` + `server.py` + `agentStore.tsx`.

### P0.1 — UI→Opus чат не доходит физически

Сейчас: `main.py:23` → `CommunicationServer()` без `lead_tmux_target` → `_forward_to_tmux` всегда silent-skip.
`main.py:26` регистрирует клиента как `"orchestrator"`, но весь код (UI, SNAPSHOT_SINK_AGENT, `to:"opus"` в ChatInput) рассчитан на `"opus"`.

Починка:
1. Переименовать `agent_name="orchestrator"` → `agent_name="opus"` в `main.py:26`.
2. Читать `config.yml`, прокидывать `lead_tmux_target="claudeorch:0"` в `CommunicationServer(...)` и `agent_tmux_targets=...` в `RecoveryManager(...)`.
3. Решить стратегически: либо UI шлёт сообщения напрямую в tmux через `_forward_to_tmux` (текущий механизм), либо вместо Opus-в-tmux делать Opus WS-клиентом. Сейчас реализован первый путь — его и активировать.

Источники: core #C1, #C2, #C6; integration #C1, #C3, #C5; ui (неявно — contract).

### P0.2 — UI навсегда показывает мок-данные

Сейчас: `store/agentStore.tsx:68-128` содержит `INITIAL_AGENTS` (4 idle) + `INITIAL_TASKS` (AUTH-1/UI-2/HEALTH-1/INIT-1). Нет actions `SET_AGENT_ROSTER` / `SET_TASKS`, нет серверного фрейма для задач, нет sync с REST `/agents`.

Починка:
1. Убрать `INITIAL_TASKS`, начать с пустых `{backlog:[], current:[], done:[]}`.
2. Добавить `SET_AGENT_ROSTER` action + poll `GET localhost:8766/agents` в `useOrchestrator` (или push от сервера).
3. Серверный фрейм `{type:"tasks", backlog, current, done}` + `UPSERT_TASKS` action. Источник данных на стороне Python — пока заглушка, читать `tasks/backlog.md` / `current.md` / `done.md`.
4. Либо расширить status-форвард в `server.py:243-245` полями `currentAction`/`currentTask`, либо убрать их чтение в `useOrchestrator.ts:60-71` (сейчас всегда `undefined`).

Источники: ui #C1, #C2; ui important #1 (status-контракт).

### P0.3 — Потеря сообщений при offline

`ChatInput.tsx:10-15` очищает textarea ДО проверки что `sendMessage` вернул true; `useWebSocket.ts:157-170` молча дропает при `readyState !== OPEN`. В offline пользователь теряет ввод без фидбэка.

Починка: `onSubmit: (text) => boolean`, `setText("")` только при `true`; плюс красная подсветка или toast при `false`.

Источник: ui #C3.

---

## P1 — надёжность и recovery-цепочка

### P1.1 — Callbacks не подписаны

`main.py` не вызывает ни одного `set_*_callback`:
- `error_handler`: `set_checkpoint_callback`, `set_restart_callback`, `set_bad_code_callback`, `set_compaction_callback` — все мёртвые.
- `process_guard`: `set_checkpoint_callback`, `set_agent_stop_callback` — Ctrl-C не сохраняет состояние.
- `agent_watchdog`: `set_wake_up_callback`, `set_restart_callback`, `set_notification_callback` — stuck-агенты никто не лечит.

Починка: в `main.py` после `initialize()` всех компонентов — блок провязки. Цепочка: watchdog-stuck → `error_handler.handle(AGENT_STUCK)` → `agent_watchdog.send_wake_up` / `restart`.

Источники: core #C4, #C5; integration #I2, #I3.

### P1.2 — `restore_session` никогда не вызывается

`recovery_manager.initialize()` умеет детектить незавершённую сессию, но `main.py:50-54` только печатает сообщение. Agents после рестарта остаются незарегистрированными в watchdog.

Починка: при `result.has_unfinished` → `await recovery_manager.restore_session(...)` либо `start_fresh()`. Также передавать `agent_tmux_targets` в `RecoveryManager(...)` из config.

Источники: core #C1, #C3; integration #C2.

### P1.3 — SessionManager — сирота

Модуль реализован (`memory/session_manager.py`), но нигде не инстанцируется. `CONTEXT_OVERFLOW` в error_handler указывает в пустоту.

Починка: создавать SessionManager по одному на агента (или по tmux-target), подключить к `error_handler.set_compaction_callback`.

Источники: core #C6; integration #I1.

---

## P2 — архитектурное несоответствие

### P2.1 — Watchdog (tmux) vs Agent Teams (in-process)

Реальность: Opus запущен в `claudeorch:0`, он спаунит исполнителей через Agent Teams — **они не в отдельных tmux-окнах**. Watchdog через `tmux capture-pane -t <agent>:<window>` не сможет мониторить backend-dev / frontend-dev как tmux-таргеты.

Варианты:
- **Опция A (минимум):** мониторить только Opus в `claudeorch:0`. Остальных "агентов" считать под-процессами, наблюдаемыми через WS (agents сами шлют status/snapshot как WS-клиенты из своих сессий).
- **Опция B (макс):** для каждого исполнителя стартовать отдельное tmux-окно, гнать туда `claude` на соответствующей модели — тяжело и ломает модель Agent Teams.

Рекомендация: Опция A. Watchdog смотрит на Opus, status-агентов получаем через WS от тех, у кого есть свой клиент (пока — только оркестратор).

### P2.2 — Roster UI: кто шлёт статусы

Сейчас только `orchestrator` (main.py) подключён как WS-клиент под именем "opus" (после фикса P0.1). Он — sink snapshot'ов, но сам status не эмитит. Panель агентов в UI остаётся статичной.

Решение: на время Python-оркестратор публикует синтетические status-сообщения от имени Opus+Agent Teams исполнителей, парся state из Claude Code output. Долгосрочно — Agent Teams добавить WS-клиент как плагин.

---

## P3 — полировка

Необязательно для первого теста:

- Порог retry у `CLAUDE_CODE_CRASH` (core замечание).
- BaseException catch в watchdog monitor-loop → Exception (core important).
- React StrictMode double-mount лишний register (ui important).
- `LogFeed` автоскролл игнорирует scroll-вверх пользователя (ui замечание).
- `ConnectionStatus` счётчик reconnect (ui замечание).
- Hardcoded `to:"opus"` в ChatInput — мешает будущему чату с другими агентами (ui important).
- `start.sh` polling вместо `sleep 3` (integration замечание).
- `stop.sh` без `set -e`, без `pkill -f uvicorn` (integration замечание, important).
- Логирование через `print` — заменить на logger (core замечание).
- `GitManager.get_rollback_history` и `CheckpointManager.has_unfinished_session` — dead code (core important).

---

## Последовательность работ

1. **Коммит #1 (P0, один день):**
   - `main.py`: rename "orchestrator" → "opus", прокинуть tmux_targets из config.yml, подписать все callback-и, вызывать restore_session.
   - `agentStore.tsx`: убрать INITIAL_TASKS, добавить SET_AGENT_ROSTER / UPSERT_TASKS.
   - `server.py`: при подключении нового клиента бродкастить обновлённый roster на UI.
   - `ChatInput.tsx`: boolean-return от onSubmit, очистка после подтверждения.
   - Убрать `currentAction`/`currentTask` из status-контракта или расширить сервер.

2. **Коммит #2 (P1, отдельно):**
   - Watchdog → ErrorHandler → restart цепочка.
   - SessionManager подключить к compaction.

3. **Коммит #3 (P2, архитектурный):**
   - Решить по watchdog-модели (опция A).
   - Модель roster — кто шлёт статусы исполнителей.

4. **Коммит #4 (P3):** polish по списку.

---

## Что сделано хорошо (не трогаем)

Подтверждено всеми тремя ревьюерами:
- WS-контракт симметричен между server.py / client.py / useWebSocket; register-first enforced.
- Reconnect-логика в `useWebSocket` — ref-замыкание, shouldRunRef, clean unmount, без утечек.
- Типобезопасность UI: discriminated union + exhaustive switch + type guards, нет `any`/`@ts-ignore`.
- Append-only DuckDB-журналы + asyncio.Lock-дисциплина в каждом модуле.
- Graceful teardown: per-step try/except в `main.py`, idempotent start/install.
- `ProcessGuard` — SIGINT/SIGTERM/SIGHUP + re-entry guard на двойной Ctrl-C.
- `AgentWatchdog` — чистая state-machine `active → possibly_stuck → restarting`.
- `GitManager` — worktree/merge/rollback с логированием причины, устойчив к конфликтам merge.
- Tauri `minWidth: 900 / minHeight: 650`, tsconfig strict, UI-5 UX на Inter + Claude-палитре.
