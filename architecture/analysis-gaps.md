# Feature gaps (analysis-gaps)

Scope: repo root `/mnt/d/orchkerstr`. Compared claims in `CLAUDE.md` and templates in
`architecture/{decisions,interfaces,graph,current-test,design-handoff}.md` against
actual code in `core/`, `communication/`, `memory/`, `git_manager/`, `ui/`.

Legend: ✅ wired / ⚠️ partial / ❌ missing / 📖 undocumented.

## ❌ Missing (claimed but not wired)

- [x] **TDD cycle — consumption of `architecture/current-test.md`** — CLAUDE.md clarified: файл ведёт Opus вручную, авто-чтения нет (TODO отмечено). —
  claim: "Перед выдачей задачи исполнителю: сам напиши тест… Tester запускает тест" (CLAUDE.md).
  Evidence: no match for `current-test` or `current_test` across `.py`/`.ts`.
  `memory/manager.py` exposes only `current_task_path()` (manager.py:67), никакого чтения/записи теста.
  Fix: либо реализовать «опус пишет тест → tester запускает», либо убрать пункт из CLAUDE.md.

- [x] **Auto-append к `architecture/decisions.md`** — CLAUDE.md переформулирован: decisions.md ведёт Opus вручную. —
  claim: "После каждого решения записывай в architecture/decisions.md", "Фиксируй каждое решение в decisions.md".
  Evidence: no match for `decisions.md` or `architecture/decisions` в коде.
  Файл остался шаблоном (decisions.md:1-3).
  Fix: добавить helper в `memory/manager.py` или hook, который аппендит запись; либо сменить формулировку CLAUDE.md на «делает это вручную».

- [x] **Claude Design handoff detector** — `core/handoff.py::scan_and_record_handoff` детектит `ork-handoff/`, аппендит инвентарь в `architecture/design-handoff.md`, дедуплицируется по fingerprint. Вызывается из `core/main.py` при старте. —
  claim: "Оркестратор обнаруживает входящий дизайн пакет" + целая секция "Интеграция с Claude Design".
  Evidence: no match for `ork-handoff` или `design-handoff` в `.py`. В `ork-handoff/ork/` лежат реальные HTML/скриншоты,
  но парсера нет. `architecture/design-handoff.md` — только шаблон.
  Fix: либо реализовать watcher (FS-poll → `memory/manager.py` запись → спаун агентов), либо вынести секцию в backlog и пометить как TODO.

- [ ] **Shared memory TTL cleanup** — SKIP: size-based compression (10KB threshold) признан достаточным; TTL не нужен. —
  task mentions it.
  Evidence: no match for `ttl`/`TTL` в `.py`. В `memory/manager.py` есть только size-based сжатие агентской памяти (threshold 10KB, manager.py:34). Shared.md сжимается не вызывается никогда (нет триггера).
  Fix: либо решить, что TTL не нужен (размер-порог достаточен), либо добавить периодическую задачу.

- [x] **Atomic/interfaces workflow — запись в `architecture/interfaces.md`** — CLAUDE.md переформулирован: файл ведёт Opus вручную. —
  claim: "Перед спауном исполнителей запиши в architecture/interfaces.md…".
  Evidence: no match for `interfaces.md` в коде. Файл — шаблон (interfaces.md:1-10).
  Fix: документировать как ручной процесс Opus или реализовать helper.

- [x] **Dependency graph — запись в `architecture/graph.md`** — CLAUDE.md переформулирован: graph.md ведёт Opus вручную; Python-слой его не пишет. —
  claim: "Построй граф зависимостей → architecture/graph.md".
  Evidence: no match for `graph.md` в коде; `Checkpoint.dependency_graph` хранится только в sqlite, не в .md.
  Fix: тоже документировать как ручной процесс или реализовать dump.

- [x] **AgentSpawner — фактический вызов `.spawn()`** — добавлен `core/orchestrator.py::Orchestrator.spawn_role(role_name)`; валидирует role по config.yml, инициирует spawn, register/unregister callbacks уже провязаны. Инстанцируется в `core/main.py`. —
  claim: "Спауни нужных агентов через AgentSpawner (каждый в своём tmux окне)".
  Evidence: `AgentSpawner` инстанцируется (`core/main.py:82`), но `.spawn()` нигде не вызывается
  (no match for `spawner.spawn(` / `await spawner.spawn`). Callbacks register/unregister тоже висят вхолостую.
  Fix: wire a trigger (UI-кнопка / WS-message / Opus tool) на `spawner.spawn(name)`, иначе tmux-окна создаются только вручную.

## ⚠️ Partial

- [x] **Watchdog → Opus notifications** — `restart_claude_code` в main.py уже делает spawner.despawn+spawn+status_for; `notify_ui_stuck` шлёт typed `status` фрейм, UI = Opus-ретранслятор (это задокументировано в «Коммуникационный сервер»). —
  `AgentWatchdog` зовёт 3 callback'а (`agent_watchdog.py:145-159`), но в `core/main.py` они прописаны так:
  `notify_ui_stuck` шлёт "ui", а не "opus" (`main.py:147`); `restart_claude_code` — TODO-stub, просто печатает строку (`main.py:141-143`).
  Т.е. watchdog логически работает, но «сообщить Opus» и «перезапустить» до конца не доведены.
  Fix: либо отдельный канал в Opus-сторону, либо явно задокументировать, что UI = Opus-ретранслятор.

- [x] **`config.yml` models на spawn** — теперь живёт через `Orchestrator.spawn_role`; модель подставляется из config.yml при каждом вызове spawn. —
  `AgentSpawner.__init__` читает `config.yml` и подставляет модель в `claude --model ...` (spawner.py:14,27,37).
  Работает корректно, но применяется только если `.spawn()` реально вызван — см. выше (мёртво на практике).

- [x] **MCP bridge `claudeorch-comms`** — fire-and-forget поведение задокументировано в CLAUDE.md (секция «Коммуникационный сервер»). Reliable inbox — TODO в будущих задачах. —
  Сервер реализован (`communication/mcp_server.py`) и прописан в `.mcp.json`. Экспозит 4 tool'а
  (`send_message`, `broadcast_message`, `get_messages`, `get_connected_agents`).
  Partial: inbox теряется при рестарте процесса (`inbox: list[dict]` в памяти, mcp_server.py:22);
  `get_messages` очищает хвост без блокировки, возможны race при параллельных tool-call.
  Fix: либо задокументировать как fire-and-forget, либо переключить на очередь/WS-replay.

- [x] **`status` тип сообщений от агентов** — `main.py` уже вызывает `comm_client.status_for(...)` из `restart_claude_code`, `notify_ui_stuck`, `emit_watchdog_status` — путь живой, задокументирован в CLAUDE.md. —
  Сервер хранит статус (`server.py:254-259`) и форвардит UI, но нигде нет кода-клиента, шлющего `client.status(...)`.
  Fix: вызывать `status()` из spawner/agents или убрать путь.

## 📖 Undocumented (works but no doc)

- [x] **DuckDB логирование всего подряд** — задокументировано в CLAUDE.md (секция «Журналы и состояние»).
- [x] **Aiosqlite checkpoints** — задокументировано в CLAUDE.md (секция «Журналы и состояние»).
- [x] **SessionManager `/compact`** — задокументировано в CLAUDE.md (секция «Память и компактизация»).
- [x] **ErrorHandler стратегии** — задокументировано в CLAUDE.md (секция «Обработка ошибок»).
- [x] **`tasks` → UI broadcast** — задокументировано в CLAUDE.md (секция «Коммуникационный сервер» + «UI-поверхность»).
- [x] **UI → tmux forwarding** — задокументировано в CLAUDE.md (секция «Коммуникационный сервер»).
- [x] **Memory compression через `claude -p` CLI** — задокументировано в CLAUDE.md (секция «Память и компактизация»).
- [x] **Archive каталог** — задокументировано в CLAUDE.md (секция «Память и компактизация»).
- [x] **Roster broadcast на UI** — задокументировано в CLAUDE.md (секция «Коммуникационный сервер» — «Типы фреймов»).
- [x] **UI-пакет (Tauri + React)** — задокументировано в CLAUDE.md (секция «UI-поверхность»).
- [x] **`start.sh` / `stop.sh`** — задокументировано в CLAUDE.md (секция «UI-поверхность»).
- [x] **`server.js` + express `/health`** — задокументировано в CLAUDE.md (секция «Артефакты старых задач»); удаление оставлено как отдельная задача.

## ✅ Verified working (reference, no action)

- WebSocket server на `localhost:8765` — `communication/server.py:77-79`.
- REST `/agents` на `localhost:8766` — `communication/server.py:146-148`.
- Message routing (`message`/`broadcast`/`snapshot`/`status`/`tasks`) — `server.py:226-270`.
- Auto register/unregister + reconnect eviction — `server.py:190-218`.
- Agent watchdog (polling, possibly_stuck/stuck/restarting FSM) — `core/watchdog/agent_watchdog.py`.
- Spawner→watchdog auto-registration callbacks — `core/main.py:99-107`.
- Checkpoint append-only + recovery bootstrap — `core/session/checkpoint.py`, `core/recovery/recovery_manager.py`.
- ProcessGuard: SIGINT/SIGTERM/SIGHUP + confirm prompt — `core/guard/process_guard.py`.
- GitManager: worktree/commit/merge/rollback + DuckDB log — `git_manager/manager.py`.
- Config.yml чтение — `core/main.py:34-59`, `core/spawner.py:14-15`.
- MemoryManager: agent + shared memory, get_context, size-based compression — `memory/manager.py`.
- Task parser для `tasks/*.md` → UI payload — `communication/task_parser.py` + `server.py:382-392`.
