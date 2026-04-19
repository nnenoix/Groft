# Backend Developer Memory

```markdown
# Backend Developer Memory

Персональная память backend-dev агента (Sonnet 4.6).

## Архитектурные конвенции

- `from __future__ import annotations`, PEP 604 unions, type hints везде.
- Без `print`/`logging` в best-effort операциях — ошибки глушатся silent.
- `asyncio.create_subprocess_exec` с list-args — никогда shell=True.
- Файловые операции в `run_in_executor` — event loop не блокируется.

## Ключевые решения

### core/process/windows_backend.py (PROCESS-BACKEND-2, PR2)
- `WindowsBackend` — Popen-based `ProcessBackend`. Target = `"pid:{pid}"`. State: `_procs: dict[name, (Popen, log_path, log_fh)]` + `_targets`. log_dir injectable (tests).
- Import-safety: `CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)` — модуль импортируется на Linux (0 = no-op creationflag даже на Windows).
- spawn: `open(log, "wb", buffering=0)`, `Popen(stdin=PIPE, stdout=log, stderr=STDOUT, creationflags=NEW_CONSOLE|NEW_PROCESS_GROUP)`. Весь sync-код в `asyncio.to_thread` (spawn/send_text/capture_output/kill).
- send_text CRLF: normalise `\r\n` → `\n`, затем expand `\n` → `\r\n`. Final `\r\n` только если `press_enter=True and not text.endswith("\n")`. Python НЕ auto-translate на Windows для bytes-pipe.
- kill double-tap: `terminate()` → `wait(timeout=5)` → на timeout `kill()`. Затем `taskkill /T /F /PID` (try/except — non-fatal, покрывает node.exe grandchildren).
- capture_output: seek to end-64KB, decode errors="replace", `replace("\r\n","\n")` → split `\n` → last N. Возврат `""` если файла нет/пусто. O(1) по FS.
- list_targets purge: каждый call итерирует `_procs`, `proc.poll()` → если not None, pop + close log_fh.
- `shutdown()` — kill all alive. Добавлен в Protocol (`core/process/backend.py`). No-op в TmuxBackend (tmux-окна по дизайну переживают orch) и InMemoryBackend (tests append `("shutdown",)`).
- `core/main.py` teardown: `await backend.shutdown()` между `spawner.despawn_all()` и `recovery_manager.shutdown()`.
- pywinpty НЕ в requirements — known limitation: bare pipe stdin ≠ TTY, future PR с `process.windows.use_pty` config flag.
- Factory: `select_backend({})` на Windows → WindowsBackend, `"windows"` явно → WindowsBackend (раньше NotImplementedError).
- Smoke tests (`tests/integration/test_windows_backend.py`): `pytestmark = skipif(sys.platform != "win32")`, 3 теста (`spawn_and_kill`, `capture_output`, `factory_on_windows`). Timeout /t 2 — быстрый cleanup.
- `start.ps1` / `stop.ps1` — PS 5.1 совместимы. `-Environment` нет в 5.1, так что env выставляется через `$env:VAR = ...` до Start-Process (child наследует). `stop.ps1` — `$ErrorActionPreference = "Continue"`, `Stop-Process -Force` с try/catch per-PID.

### core/process/* (PROCESS-BACKEND-1, PR1)
- `ProcessBackend` Protocol (`core/process/backend.py`) — abstraction `spawn/send_text/kill/capture_output/is_alive/list_targets`. `Target = str` opaque. Callers получают Target от `spawn()` или из `backend.list_targets()`.
- `TmuxBackend` (`core/process/tmux_backend.py`) — единственный продакшн backend. Содержит весь tmux-код: `_run_tmux`, `_tmux_send`, `capture-pane`. `send_text` хранит инвариант безопасности: split на `\n`, каждая непустая строка → `["-l", "--", line]`, между ними bare `Enter`, в конце финальный `Enter` (если `press_enter=True`). НЕ объединять в один send-keys — это injection-guard, на нём держится UI allowlist regex.
- `select_backend(config)` (`core/process/__init__.py`) читает `config["process"]["backend"]`. `auto` → POSIX → TmuxBackend, Windows → NotImplementedError. `tmux` → TmuxBackend. `windows` → NotImplementedError. Прочее → ValueError.
- `InMemoryBackend` (`tests/support/in_memory_backend.py`) — записывает каждый вызов в `self.calls: list[tuple]`. Target = `f"mem:{name}"`. `outputs[target]=...` — тестовый preset capture_output.
- `AgentSpawner.__init__(..., backend=None)` — backend optional (default TmuxBackend). `cmd: list[str]` + `env: dict[str,str]` теперь живут отдельно (раньше склеивались в shell-строку самим spawner-ом). `get_tmux_targets()` оставлен как DeprecationWarning alias на `get_targets()`.
- `CommunicationServer.__init__(..., backend=None, lead_target=None)` — старые `lead_tmux_target`/`agent_tmux_targets` удалены. Forward к pane: `_resolve_pane_target(to)` смотрит сначала в `backend.list_targets().get(to)`, потом в `lead_target`. Сам tmux-код выпилен — есть только `backend.send_text(target, content)`.
- `AgentWatchdog.__init__(..., backend=None)` — `_capture(target)` делегирует `backend.capture_output(target, 50)`. Поле `AgentState.tmux_target` переименовано в `target`. `register_agent(name, target)` — параметр тоже переименован.
- `RecoveryManager(..., agent_targets=...)` — kwarg переименован c `agent_tmux_targets`.
- `core/main.py::_load_runtime_config` возвращает `(full_config, lead_target, agent_targets)`. Backend создаётся один раз через `select_backend(raw_config)` и инжектится в spawner/server/watchdog. config.yml: добавлена секция `process: { backend: auto }`. Секция `tmux:` остаётся (там адреса target-ов — пока tmux-форматные).
- Checkpoint миграция (`core/session/checkpoint.py::from_row`): если в `agent_states[name]` нет `target` но есть `tmux_target` — копируем. На запись только `target`. Это сохраняет загружаемость старых `.claudeorch/checkpoints.db`.
- Тест `test_spawn_flow.py` переписан: fixture `backend` → `InMemoryBackend()` инжектится во все три модуля. Assert на `backend.list_targets()["backend-dev"] == "mem:backend-dev"` и на `backend.calls` (фильтр по op="spawn").

### communication/server.py
- Триггер UI-forward на `sender == "ui"` из WebSocket registration, не из `msg["from"]` — защита от подмены.
- tmux forward: `send-keys -l` (literal, предотвращает инъекции) + отдельный `Enter` без `-l`. Многострочный контент → `content.split("\n")`, каждая строка отдельно. (PROCESS-BACKEND-1: эта логика переехала в `TmuxBackend.send_text`.)
- `_forward_to_ui(payload)` — best-effort, `ConnectionClosed` → silent + `_unregister`.
- `UI_SINK_AGENT = "ui"`, `SNAPSHOT_SINK_AGENT = "opus"` — константы в начале файла.
- snapshot frame: поле `terminal` с fallback на `content` для совместимости.
- status frame: порядок — `_status[sender]=status` → duckdb-лог → UI-форвард.
- В snapshot duckdb `msg_to` = "opus" отражает первичный маршрут, UI-форвард не влияет.

### communication/mcp_server.py (P5.1)
- `inbox: list[dict]` заменён на aiosqlite (`mcp_inbox.db`, WAL mode).
- `_get_db()` — ленивое открытие, создаёт каталог + схему (`messages` + индекс `idx_messages_to_unread`).
- `get_messages`: `BEGIN IMMEDIATE`, SELECT unread, batch UPDATE `consumed_at`, commit. Пустой → `"Нет новых сообщений"` (сохранён контракт).
- `send_message`/`broadcast_message` в БД не пишут — inbox только для incoming.
- Teardown не нужен: WAL mode корректно закрывается при ungraceful exit.

### memory/manager.py (P2.2 + P4.1)
- `append_decision(title, context, decision, rationale)` — формат: `## <ISO UTC> — <title>` + три H3 подсекции. `path.open("a")`, mkdir parents.
- ISO-timestamp: `isoformat(timespec="seconds")` → `2026-04-19T12:34:56+00:00`.
- `_compress_path(path, log_agent_name, archive_prefix, default_title)` — общая логика для per-agent и shared compression.
- `compress_shared()` — try/except с `log.exception`, возвращает False при ошибке.

### core/main.py (P3.1 + P4.1)
- `memory_compress_loop()` — sleep 600s, итерирует `known_roles()` + `compress_shared()`. Двойной try/except: одиночная ошибка не убивает loop.
- `/decide <json>` — slice `stripped[len(cmd):].strip()` (не split, чтобы не коллапсировать пробелы в payload).
- `/rescan-handoff` — шлёт `handoff_event` даже на empty diff (подтверждение команды). Loop фильтрует empty.

### core/handoff.py (P3.2 + P3.1)
- `scan_and_record_handoff` возвращает `list[str]` (relative paths) вместо bool.
- Module-level `_last_fingerprints: dict[Path, str]` — дедупа без чтения markdown. Per-project_root key.
- `_extract_components(html_files)` — lazy bs4 import, ImportError → warning + return []. `html.parser` (no lxml dep).
- Компоненты включаются в fingerprint — changed components триггерят re-emit.
- bs4: `classes = tag.get("class") or []` + `isinstance(classes, str)` defensive branch.

### communication/server.py (P2.2 decision frame)
- `type=decision` frame → validate 4 str fields → forward к opus через `_route_direct(SNAPSHOT_SINK_AGENT, ...)`.
- Сервер в файл НЕ пишет — только транспорт к Opus. Один write-site: `MemoryManager.append_decision`.

## Параллельная работа в одном worktree
При работе нескольких агентов в одном master без worktree — дожидаться чужих коммитов перед финальным Edit/commit. Иначе правки перезатираются. Решение: применять свои изменения на чистом HEAD и сразу коммитить.

## Зависимости
- `beautifulsoup4>=4.12` в `requirements.txt` (для `core/handoff.py`).
- `aiosqlite` уже в requirements (для `mcp_inbox.db`).

## Тесты
- `tests/integration/test_spawn_flow.py` — 4/4 PASS (smoke для коммуникационного слоя).
- `tests/test_mcp_inbox.py::test_get_messages_consumes_rows` — monkeypatch `_DB_PATH` на tmp_path.
- FastMCP `@server.tool()` возвращает оригинальную функцию без `.fn` wrapper.
```
