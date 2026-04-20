# Architecture Decision Log

Журнал архитектурных решений тимлида. Каждая запись: дата, контекст, решение, обоснование, последствия. Заполняется при каждом нетривиальном выборе — выбор библиотеки, изменение контракта между модулями, смена подхода к задаче.

---

## 2026-04-19 — Fix #1: UISettings persistence (localStorage)

**Что:** Новый хук `ui/src/hooks/useUISettings.ts` (load/save с per-field type-guards) + App.tsx подхватывает `loadUISettings()` в initial state и `saveUISettings(...)` в useEffect по `[state.uiSettings]`.

**Почему:** До фикса theme/font/density/accent/backdrop жили только в `useState` — любой refresh затирал их в TWEAK_DEFAULTS, что делает экран Preferences плацебо.

**Как проверил:** `cd ui && npm run build` — собрано без TS-ошибок (307 KB js). Store валидируется при загрузке (вручную проверил bad-json и unknown-enum не ломают — падает в дефолты).

**Scope:** только 5 визуальных полей. 11 «поведенческих» toggle-ов (анимации/auto-restart/TDD/…) оставлены без персиста — отдельный тикет.

---

## 2026-04-19 — Fix A: spawner env (AGENT_TEAMS + .mcp.json)

**Что:** `core/spawner.py::spawn()` теперь добавляет `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` в env и `--mcp-config <project_path>/.mcp.json` в CLI, если файл существует.

**Почему:** audit-all.md #5 — sub-агенты, спауненные через `spawner.spawn()`, раньше не имели ни agent-teams, ни MCP-моста. Без этого `claudeorch-comms` у них отсутствовал → WS-связь невозможна. Opus (в нулевом окне) единственный имел TEAMS=1 из start.sh.

**Как проверил:** 
1. `pytest tests/integration/test_spawn_flow.py` — 4 passed.
2. Реальный spawn: `python3 -c "orch.spawn_role('backend-dev')"` → успех. `tmux capture-pane backend-dev` показал командную строку `AGENT_NAME=backend-dev CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude ... --mcp-config /mnt/d/orchkerstr/.mcp.json`. 
3. `ps auxf` — MCP server child: `python3 /mnt/d/orchkerstr/communication/mcp_server.py` запущен под PID backend-dev'а.

**Известное ограничение:** `mcp_server.py::_ensure_connected` — lazy, WS-коннект поднимается только при первом tool-call из claude. Пока backend-dev idle, он не появляется в `GET /agents`. Это не регрессия Fix A — это дизайн MCP-моста (документировано в комментарии функции).

---

## 2026-04-19 — Fix B: не форвардить `message` в pane когда `to=opus`

**Что:** В `communication/server.py::_dispatch` для `type=="message"` добавлен guard `to != SNAPSHOT_SINK_AGENT` перед `_forward_to_pane`. Route-direct через WS остался без изменений.

**Почему:** `_resolve_pane_target(to)` для `to="opus"` не находит запись в `backend.list_targets()` (opus — не worker, он запускается из start.sh, а не через AgentSpawner) и уходит в `self._lead_target`, который и есть пейн opus'а. В итоге сообщение «ui → opus» попадало в пейн дважды: раз через MCP inbox (`get_messages`), раз через `tmux send-keys` с префиксом `[from=ui]`. Пользователь видел задвоение в TUI.

**Почему guard explicit, а не «только если opus WS-зарегистрирован»:** MCP-мост подключается лениво (см. Fix A). Между рестартом MCP и первым tool-call opus WS-не-зарегистрирован, но продолжает читать inbox через MCP — pane-форвард в этом окне тоже был бы дублем, а не единственным каналом.

**Как проверил:** `pytest tests/unit/test_shutdown_endpoint.py tests/integration/test_spawn_flow.py` — 6 passed. Функциональная проверка — требует второго окна с opus'ом под UI; в этой сессии не делал, оставлено на оператора.

---

## 2026-04-19 — Fix C: AgentSpawner config hot-reload

**Что:** 
- `AgentSpawner._load_config(path)` — чистый статический ридер (возвращает `{}` на ошибку).
- `AgentSpawner.reload_config()` — публичный метод, перечитывает тот же `config_path` и обновляет `self.config`, но только если свежий парс непустой (сломанный YAML не стирает in-memory).
- `Orchestrator.spawn_role()` — когда `role_name not in known_roles()`, зовёт `reload_config()` и повторяет проверку. Только если после reload роль всё ещё неизвестна — отказ.

**Почему:** `AgentSpawner.config` кешировался в `__init__` и жил до рестарта процесса. Пользователь добавлял новую роль в `config.yml` — `/spawn new-role` падало «unknown role», хотя файл уже содержал запись. Это ломало продуктовый сценарий «добавил роль → сразу спаунится».

**Как проверил:** `pytest tests/unit/test_spawner_reload.py tests/unit/test_shutdown_endpoint.py tests/integration/test_spawn_flow.py` — 9 passed. Покрыты три кейса:
1. reload подхватывает свежедобавленную роль.
2. reload на malformed YAML не стирает известные роли.
3. `Orchestrator.spawn_role("scout")` возвращает False до правки `config.yml`, True после (без явного reload_config — автоматически через spawn_role).

**Почему guard на пустой reload:** если юзер временно поломал YAML в редакторе, не хотим терять известный роли и делать всю оркестрацию неспаунимой до исправления. Сохранение старой копии — defense-in-depth.

---

## 2026-04-19 — Phase 3 skipped: Telegram backend не существует

**Что:** Phase 3 из плана ("Telegram wizard test с токеном из `.claudeorch/secrets.env`") откладывается в объединённый Phase 6 (messenger wizards).

**Почему:** Аудит описывал Telegram-wizard как «рабочий до Step 3» с багом в структурированном ответе. Проверка показала большее — backend-а **не существует вообще**:
- `grep -rn "telegram" --include="*.py"` → 0 результатов. 
- Слэш-команды `/telegram:configure`, `/telegram:access` нигде не обрабатываются.
- `run_tmux_command` (в `ui/src-tauri/src/messenger.rs`) шлёт эти команды в Opus-пейн, где claude воспринимает их как неизвестный слэш.
- `save_messenger_config` только пишет `.claudeorch/messenger-telegram.json`, но никто этот JSON не читает.

Таким образом, «протестировать визард» невозможно — под ним пустота.

**Что сделаю в Phase 6:** написать реальный Python-бэкенд (aiogram или python-telegram-bot long-polling), зарегистрировать `/telegram:configure` и `/telegram:access` как MCP tools у опуса, ввести `/messenger/status/{name}` REST, убрать `setUsername(null)` заглушку.

**Токен** в `.claudeorch/secrets.env` (`TELEGRAM_BOT_TOKEN=...`) — валидный `8778460710:...`, используется в Phase 6 для интеграционного теста.

---

## 2026-04-20 — AgentSpawner vs Task tool: разделение ролей, не конкуренция

**Что:** Во время Phase 2 gap-marathon'а оркестратор (opus) выбрал Claude Code Task tool с `isolation:worktree` для параллельного спауна backend-dev/frontend-dev **вместо** собственного `AgentSpawner.spawn_role()`. Решение было тихое, без записи в decision-log.

**Сигнал:** если наш собственный продукт предпочитает встроенный инструмент конкурента — это провал продуктового позиционирования для текущего use case.

**Честный анализ где кто выигрывает:**

| Критерий | Task tool | AgentSpawner |
|---|---|---|
| Setup overhead | 0 | tmux + WS + MCP + DuckDB |
| Worktree isolation | из коробки | надо руками |
| Windows без WSL | ✔ | ✗ (tmux) |
| One-shot parallel burst | ✔ | ✗ (тяжёлая инфра) |
| Long-lived (hours/days) | ✗ (умирает) | ✔ |
| Persistent identity / memory | ✗ | ✔ |
| External triggers (Telegram/UI → запущенный агент) | ✗ | ✔ |
| Cross-agent messaging | ✗ (изолированы) | ✔ (MCP `send_message`) |
| Human-in-the-loop (наблюдать + вмешаться) | ✗ (invisible) | ✔ (tmux pane) |
| Watchdog / recovery | ✗ | ✔ |

**Вывод для продукта:**
Groft — **не оркестратор параллельных задач**. На этом поле Task tool объективно лучше. Groft — **команда долгоживущих AI-товарищей с identity, memory, наблюдаемой работой и внешними каналами коммуникации**. Parallel burst-fix'ы делаются Task tool'ом **внутри** живых AgentSpawner-агентов.

**Конкретные следствия, которые запись в CLAUDE.md уже отражает:**
1. One-shot parallel file-burst → Task tool (опционально — внутри живого AgentSpawner-агента как делегация)
2. Long-lived teammate с накапливаемой памятью и внешним каналом → AgentSpawner
3. UI выделяет уникальные фичи: `chat-with-backend-dev-via-Telegram`, `watch-agent-live-in-tmux`, `persistent-memory-view`
4. Не вкладываться в burst-parallelism на AgentSpawner'е — это проигранная битва
5. Phase 2 gap-marathon валидно сделан через Task tool; decision зафиксирован постфактум здесь

**Action items (вне текущих фаз):**
- Phase 8 (decision log) — must-have, чтобы такие решения не оставались тихими
- Repositioning в README/docs: «AI teammates you chat with», а не «yet another subagent spawner»
- Аудит `memory/*.md` — использует ли опус реально persistent memory или обнуляет при каждой задаче

---

## 2026-04-20 — Phase 10: Hot-boot Telegram bridge + Watchdog skip_liveness (gap #4)

**Что:**
- `/messenger/telegram/configure` теперь hot-buut'ит bridge через `build_and_start_bridge` (извлечённая функция в `core/messengers/telegram.py`) + `CommunicationServer.replace_telegram_bridge(new)` корректно стопит старый и ставит новый. Endpoint всегда 200, поле `bridge` = `"running"|"failed"`.
- `AgentState.skip_liveness: bool` + `AgentWatchdog.register_agent(..., skip_liveness=True)` — снапшоты идут в UI, но wake/restart/notify колбеки не триггерятся. `core/main.py` явно регистрирует opus с флагом.

**Почему:**
- Hot-boot: без него UX сломан — пользователь вводит токен → нужен рестарт orch чтобы bridge ожил. Это противоречит обещанию «configure-then-pair» flow.
- Watchdog-гап #4: opus — лидер, он бездействует между задачами; watchdog слал ему `"wake up, are you there?"` каждые 180s в pane, что ломало UX тимлида.

**Реализация:**
- Один PR (#17), squash-merge в master → `745ddf5`.
- Ветка: `feature/phase10-quick-fixes`, два логических коммита (watchdog fix, telegram hot-boot) + тесты на каждый.
- Dogfood: реализацию делал AgentSpawner-agent `backend-dev` в живом tmux-окне. Я (opus) написал ТЗ в `architecture/current-task.md`, отправил через MCP `send_message(to="backend-dev")`, принял результат обратно через tmux-pane + git log. Task tool внутри backend-dev'а для локальной декомпозиции — допустимо per CLAUDE.md.

**Как проверил:** `pytest tests/ -q` → 150 passed, 5 skipped. `git log --oneline master..feature/phase10-quick-fixes` → 2 коммита. Acceptance grep'ы пройдены (см. PR #17).

**Security follow-up:** TELEGRAM_BOT_TOKEN засвечен во время разработки — после мерджа user должен отозвать через @BotFather и заново спарить бота (TODO в memory).

---

## 2026-04-20 — Phase 8: Decision log (DuckDB + MCP + REST + UI)

**Что:**
- `core/decision_log.py` — `DecisionLog` класс на DuckDB (`.claudeorch/decisions.duckdb`), schema: `id, ts, agent, category, chosen, alternatives JSON, reason, task_id`. Методы `initialize/append/list_recent/close`.
- MCP tool `log_decision(category, chosen, alternatives=None, reason="", task_id=None)` в `communication/mcp_server.py` — agent берётся из `AGENT_NAME` env.
- REST `GET /decisions?agent=&limit=` в `communication/server.py` — newest-first JSON.
- `scripts/backfill_decisions.py` — парсер markdown-журнала (7 записей успешно залиты).
- UI: `ui/src/views/DecisionsView.tsx` + nav-item «Decisions» в `CommandCenterLayout.tsx` (timeline, agent-filter, expand/collapse reason+alternatives, без новых npm-deps).
- `CLAUDE.md` раздел «Лог решений (Phase 8)» — правило вызывать `log_decision` перед каждым нетривиальным выбором; markdown остаётся для развёрнутого контекста.

**Почему:**
- `architecture/decisions.md` — только текст. Нельзя отфильтровать по агенту, категории, связанной задаче, построить таймлайн в UI или автоанализ.
- DuckDB уже стандарт в проекте (`messages.duckdb`, `memory_log.duckdb`, `git_history.duckdb`) — паттерн консистентен, нулевая когнитивная нагрузка.
- Параллельное ведение (markdown + DB) — markdown остаётся human-first, DB даёт structured query + UI.

**Реализация:**
- 4 PR'а: #18 (backend 8.1–8.4), #19 (UI 8.5). Phase 8.6 (CLAUDE.md rule) — отдельный маленький коммит `9930024` прямо в master (тривиальный текст).
- Dogfood: backend через AgentSpawner-агент `backend-dev` в tmux-окне (один цикл, самостоятельно разбил 8.1→8.4 на последовательные коммиты). UI через AgentSpawner-агент `frontend-dev` (один коммит `33dec86`, 217 insertions, чистый build).

**Как проверил:** `pytest tests/ -q` проходит. `scripts/backfill_decisions.py` — 7 записей в DuckDB. `cd ui && npm run build` — 0 TS-ошибок, 345 KB js. Визуальная проверка UI отложена до рестарта orch (эндпоинт живёт только после перезапуска процесса).

**Известное ограничение:** `/decisions` endpoint не отвечает до рестарта orch. Рестарт запланирован перед Phase 9 — активирует и Phase 8 (decisions), и Phase 10 (hot-boot telegram + skip_liveness) в живой системе.

---

## 2026-04-20 — Phase 9: Context retrieval (DuckDB FTS, not embeddings)

**Что:**
- `core/context_store.py` — DuckDB FTS (BM25) поверх `memory/{agent}.md` + `memory/shared.md`. Чанкинг по `---` → blank-line → hard-cap 1500 chars. Агенты фильтруются `WHERE agent = ? OR agent = '_shared'`. Fallback на `LIKE '%q%'` если FTS extension недоступен.
- MCP tools `get_relevant_context(query, k=5)` + `reindex_my_context()` в `communication/mcp_server.py`. Обе асинхронно обёрнуты через `asyncio.run_in_executor` — DuckDB sync API, event-loop не блокируется.
- `core/main.py` — lazy init + reindex всех известных ролей (opus + worker roles + `_shared`) при старте, close на teardown.
- 5 тестов в `tests/unit/test_context_store.py`, полный pytest: 174 passed (+24 vs pre-Phase 9).

**Почему DuckDB FTS, а не vector embeddings:**
- Нулевые новые зависимости (`sentence-transformers`/`torch`/`numpy` — heavy; OpenAI API — требует ключа + network).
- Консистентно с существующим DuckDB-heavy стэком (`messages.duckdb`, `decisions.duckdb`, `memory_log.duckdb`, `git_history.duckdb`).
- Memory files у агентов — markdown с общей технической терминологией. Лексическое пересечение высокое, BM25 хорошо ранжирует.
- Если BM25 окажется мало (агент ищет «как работает persistence» — не находит раздел «checkpoints»), мигрируем на embeddings отдельным тикетом.

**Что НЕ вошло в Phase 9 (по ревью scope):**
- MCP inbox DB-persistence — уже реализовано (`.claudeorch/mcp_inbox.db`, SQLite). Claim в original backlog был устаревший.
- Session save/load — уже есть в `checkpoints.db` (aiosqlite, `CheckpointManager`).
- UI «Memory search» вкладка — отдельный тикет для frontend-dev.

**Реализация:**
- Один PR (#20), squash-merge → `e6586b8`. 3 логических коммита внутри ветки (ContextStore + tools + orch wiring).
- Dogfood: backend-dev в живом tmux-окне, 5m 18s Task tool sub-task внутри, 38 tool uses.

**Известное ограничение:** auto-reindex срабатывает только на старте orch. Если агент обновил `memory/*.md` между рестартами — вызов `reindex_my_context()` нужен для свежести. Автоматический file-watch — отдельный тикет (KISS: пока не факт, что нужно — агенты редко пишут в свой memory в пределах одной сессии).

