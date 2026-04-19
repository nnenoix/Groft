# Backend Developer Memory

Вот сжатый текст памяти backend-dev:

---

# Backend Developer Memory

## Архитектурные конвенции

- `from __future__ import annotations`, PEP 604 unions, type hints везде.
- Без `print`/`logging` в best-effort операциях — ошибки глушатся silent.
- `asyncio.create_subprocess_exec` с list-args — никогда `shell=True`.
- Файловые операции в `run_in_executor` — event loop не блокируется.

## core/paths.py

- `install_root()` (MEIPASS под frozen, repo root в dev) и `user_data_root()` (`CLAUDEORCH_USER_DATA` env → `install_root()` fallback). Оба `@functools.cache`.
- `*_dir()` авто-mkdir: `claudeorch_dir`, `logs_dir`, `panes_dir`, `architecture_dir`, `memory_dir`, `memory_archive_dir`, `tasks_dir`, `agents_dir`, `handoff_dir`. `handoff_dir` читает `CLAUDEORCH_HANDOFF_DIR`.
- `config_path`/`default_config_path` без mkdir. НЕТ module-level констант путей.
- Все конструкторы call-sites сохраняют explicit override для тестов.
- Тест `tests/unit/test_paths.py`: autouse-фикстура `_reset_path_cache` чистит `@cache` до/после каждого теста.

## ProcessBackend абстракция

- `ProcessBackend` Protocol (`core/process/backend.py`): `spawn/send_text/kill/capture_output/is_alive/list_targets`. `Target = str` opaque.
- `TmuxBackend` — prod backend. `send_text`: split на `\n`, каждая строка → `["-l", "--", line]`, между ними bare `Enter` — injection-guard.
- `WindowsBackend` — Popen-based. spawn: `Popen(stdin=PIPE, stdout=log, stderr=STDOUT, creationflags=NEW_CONSOLE|NEW_PROCESS_GROUP)`. send_text CRLF: normalise `\r\n→\n`, expand `\n→\r\n`. kill double-tap: `terminate()→wait(5)→kill()` + `taskkill /T /F /PID`. capture_output: seek end-64KB, decode errors="replace". `CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)` — import-safe на Linux.
- `select_backend(config)` читает `config["process"]["backend"]`. `auto` → POSIX→TmuxBackend, Windows→WindowsBackend.
- `InMemoryBackend` (`tests/support/in_memory_backend.py`) — записывает calls в `self.calls: list[tuple]`.
- `shutdown()` в Protocol; TmuxBackend no-op (окна переживают orch); `core/main.py` вызывает `await backend.shutdown()` при teardown.
- Checkpoint миграция: `tmux_target` → `target` при чтении старых `.claudeorch/checkpoints.db`.

## communication/server.py

- UI-forward триггер на `sender == "ui"` из WS registration, не из `msg["from"]`.
- `UI_SINK_AGENT = "ui"`, `SNAPSHOT_SINK_AGENT = "opus"` — константы.
- `type=decision` frame → 4 str fields validate → forward к opus. Сервер в файл не пишет, только транспорт.
- `set_shutdown_callback(fn)` — setter для graceful shutdown из Tauri. `POST /shutdown` → 200 сразу + `create_task(cb())`.
- `_forward_to_ui` best-effort, `ConnectionClosed` → silent + `_unregister`.

## communication/mcp_server.py

- `inbox` = aiosqlite (`mcp_inbox.db`, WAL mode). `_get_db()` ленивое открытие + схема.
- `get_messages`: `BEGIN IMMEDIATE`, SELECT unread, batch UPDATE `consumed_at`. Пустой → `"Нет новых сообщений"`.

## memory/manager.py

- `append_decision(title, context, decision, rationale)`: `## <ISO UTC> — <title>` + три H3 подсекции.
- `_compress_path` — общая логика для per-agent и shared compression.
- `compress_shared()` — try/except с `log.exception`, возвращает False при ошибке.

## core/main.py

- `memory_compress_loop()` — sleep 600s, итерирует `known_roles()` + `compress_shared()`.
- `/decide <json>` — `stripped[len(cmd):].strip()` (не split).
- `/rescan-handoff` — шлёт `handoff_event` даже на empty diff.
- `set_shutdown_callback(process_guard.request_shutdown)` после `await comm_server.start()`.

## core/handoff.py

- `scan_and_record_handoff` возвращает `list[str]` (relative paths).
- Module-level `_last_fingerprints: dict[Path, str]` — дедупа без чтения markdown.
- `_extract_components`: lazy bs4 import, `html.parser`. `classes = tag.get("class") or []` defensive.

## Tauri sidecar (PR C)

- `ProcessGuard.request_shutdown()` — тонкая обёртка над `_shutdown()`.
- Rust: `OrchestratorChild(Mutex<Option<Child>>)`, `on_window_event(CloseRequested)` → `reqwest::blocking POST /shutdown` (timeout 2s) → `child.kill()+wait()` → `app.exit(0)`. First-run seed: config.yml + `.claude/agents/` из resource_dir.

## Packaging (PR B) и Release (PR D)

- `packaging/orchestrator.spec`: `PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))` — пути от корня, не от `packaging/`.
- `--smoke` в `core/main.py`: early-exit сразу после `configure_logging`, до `_load_runtime_config`.
- `tauri.conf.json::bundle.windows.wix.upgradeCode = "3be766d6-a9e9-4d6d-a623-6139519fdaa2"` — статичный навсегда.
- `.github/workflows/release.yml`: триггер `push: tags: ["v*"]` + `workflow_dispatch`. `permissions: contents: write`. Все `uses:` пиннутые (`@v4`/`@v5`/`@v2`).
- Baseline тестов: 13 passed, 4 skipped.

## core/usage_tracker.py

- `UsageTracker(projects_dir: Path | None)` — sync `compute()` reads `**/*.jsonl` under projects_dir.
- Aggregates into `rolling_5h` (now - 5h) and `weekly` (now - 7d) windows.
- Returns `{"rolling_5h": {..., "reset_at": str}, "weekly": {..., "reset_at": str}}`.
- `reset_at` = oldest message timestamp + window duration; fallback = `now.isoformat()` when window empty.
- Skips unreadable files (log.warning), skips malformed JSON lines, skips missing keys. No raises.
- projects_dir non-existent → zeros returned immediately.

## communication/server.py — usage tracking additions

- `_usage_task: asyncio.Task[None] | None` in `__init__`.
- `/usage` GET endpoint: runs `UsageTracker().compute()` in executor, returns dict.
- `_usage_broadcast_loop`: asyncio.sleep(60) loop, calls `_forward_to_ui({"type": "usage", "windows": ...})`.
- Task created in `start()` after `_started = True`; cancelled+awaited in `stop()` before WS shutdown.

## Зависимости

- `beautifulsoup4>=4.12` в `requirements.txt`.
- `aiosqlite` уже в requirements.
- `pyinstaller>=6.0` в `requirements-dev.txt`.
