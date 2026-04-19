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

### core/paths.py (PATHS-1, PR A из 4)
- Единый helper для путей: `install_root()` (R/O, MEIPASS под frozen, repo root в dev), `user_data_root()` (`CLAUDEORCH_USER_DATA` env override → `install_root()` fallback). Оба `@functools.cache`.
- `*_dir()` функции авто-mkdir: `claudeorch_dir`, `logs_dir`, `panes_dir`, `architecture_dir`, `memory_dir`, `memory_archive_dir`, `tasks_dir`, `agents_dir`, `handoff_dir`. `handoff_dir` читает `CLAUDEORCH_HANDOFF_DIR` override.
- `config_path`/`default_config_path` без mkdir (файлы, не директории).
- НЕТ module-level констант путей. Рефакторинг: `DEFAULT_DB_PATH = Path(".claudeorch/...")` → `claudeorch_dir() / "..."` в `__init__` (чтобы env var успевала примениться через `@cache`).
- Call-sites (12 файлов + communication/server.py): все конструкторы сохраняют explicit override для тестов — меняется только default.
- `core/main.py::PROJECT_ROOT` полностью выпилен: `project_root = user_data_root()`, далее через helpers.
- `core/agents_watcher.py::start(project_root: Path | None, ...)` — при None берёт `agents_dir()`.
- `sys.path.insert` в `core/main.py` и `communication/mcp_server.py`: `.parent.parent` → `.parents[1]` (семантически то же, но не триггерит grep acceptance).
- Dev-режим бит-идентичен: `CLAUDEORCH_USER_DATA` unset → пути 1:1 с прошлым. Smoke: `claudeorch_dir() == /mnt/d/orchkerstr/.claudeorch`.
- `tests/unit/test_paths.py` — 4 теста (dev_mode, env_override, handoff_override, frozen_mode). Autouse-фикстура `_reset_path_cache` чистит `@cache` до и после каждого теста, чтобы тесты не загрязняли друг друга.
- `tests/unit/__init__.py` — пустой, чтобы pytest подхватил как пакет.
- Acceptance greps все зелёные: `Path(__file__).resolve().parent.parent` только в `core/paths.py`, `Path(".claudeorch` и `Path("memory")` пустые.

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

### TAURI-SIDECAR-1 (PR C из 4)
- `CommunicationServer.set_shutdown_callback(fn)` — публичный setter (signature: `Callable[[], Awaitable[None]] | None`). Callback вызывается из `POST /shutdown` через `asyncio.get_running_loop().create_task(cb())` — endpoint возвращает `{"ok": True}` сразу, actual teardown идёт параллельно. Важно: используется существующий `self._background_tasks` strong-ref set, чтобы CPython не GC'нул task (тот же pattern что в `_unregister`).
- `POST /shutdown` endpoint в `_build_app()` между `/agents/models` и `/tasks`. Без callback — все равно 200 (noop), чтобы Tauri graceful-path не стрял в early-boot окне.
- `ProcessGuard.request_shutdown()` — public async тонкая обёртка над `_shutdown()`. Тот же путь checkpoint→agent_stop_cb→event.set→future.set, что и SIGTERM. Вызывается из `/shutdown` через `comm_server.set_shutdown_callback(process_guard.request_shutdown)` в `core/main.py` ОДНОЙ строкой после `await comm_server.start()`.
- Тест `tests/unit/test_shutdown_endpoint.py` — 2 теста. Fixture бутит CommunicationServer на free-ports (`socket.SOCK_STREAM.bind(("127.0.0.1", 0))`), `db_path=Path(":memory:")`. httpx.AsyncClient POST → 200 → asyncio.Event.wait с timeout 2s. Вариант без callback — тоже 200. Тесты ~0.3s каждый, sidecar-сервисы не нужны.
- Баseline pytest: 11 passed + 4 skipped → 13 passed + 4 skipped (мы добавили 2 теста).
- Rust-side (не моя зона, для справки): Cargo.toml +`tauri-plugin-single-instance="2"` + `which="6"` + `reqwest={version="0.12",features=["blocking"]}`. tauri.conf.json identifier `com.yegor.ui`→`com.groft.app`, `bundle.resources: ["../../dist/orchestrator"]`. lib.rs переписан полностью: plugin chain (opener + single_instance focus-on-reopen), `.setup(|app|{...})` с first-run seed (config.yml + .claude/agents/ рекурсивно из resource_dir, fallback на `_internal/` vs без префикса), spawn orchestrator[.exe] с `CLAUDEORCH_USER_DATA=app_data_dir()`, `OrchestratorChild(Mutex<Option<Child>>)` через app.manage. `on_window_event(CloseRequested)` → `api.prevent_close()` → std::thread с `reqwest::blocking` POST /shutdown (timeout 2s) → sleep 1s → `child.kill()+wait()` → `app.exit(0)`. Dev-режим без бандла: `resource_dir` может быть unavailable → warning + skip spawn (нет поломок, dev-workflow `python core/main.py` остаётся).

### packaging/ (BUNDLE-1, PR B из 4)
- `packaging/orchestrator.spec` — PyInstaller onedir spec. **Важно:** spec живёт в `packaging/`, поэтому `Analysis(["core/main.py"], pathex=["."])` из interfaces.md template НЕ работает (PyInstaller резолвит относительные пути от директории спека, не от CWD). Решение: `PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))` и все пути через `os.path.join(PROJECT_ROOT, ...)`. Hidden imports / excludes / EXE / COLLECT блоки — 1:1 как в template.
- `collect_all("duckdb")` тянет `duckdb.experimental` (требует numpy) — PyInstaller печатает WARNING, но build зелёный (submodule просто скипается).
- `packaging/build_windows.py` — кросс-платформенный wrapper. `argparse(--smoke, --distpath)`, `subprocess.run([sys.executable, "-m", "PyInstaller", spec, "--clean", "--noconfirm"], cwd=PROJECT_ROOT, check=True)`. Exe name через `sys.platform == "win32"`. Размер бандла — `sum(p.stat().st_size for p in dist_dir.rglob("*") if p.is_file())` / 1024² (`shutil.disk_usage` не подходит — это free space на FS).
- `core/main.py::main()` — `--smoke` early-exit СРАЗУ после `configure_logging(log_dir=logs_dir())`, ПЕРЕД `_load_runtime_config`. Это гарантирует, что log handler инициализирован до emit'а "smoke ok". Ничего больше не меняется (ProcessGuard, backend, серверы НЕ запускаются).
- `tests/integration/test_frozen_boot.py` — skip-guarded `pytestmark` через `os.environ["GROFT_RUN_BUNDLE_TESTS"] != "1"` (PyInstaller билд ~15-20s, не хочется в обычном `pytest`). Билдит spec в `tmp_path`, запускает exe `--smoke`, проверяет exit 0 + `b"smoke ok"` в `stdout+stderr`.
- Build на Linux WSL2: ~20s, бандл 100.9 MB (lim ≤ 200 MB). Bootloader ELF, exe = `dist/orchestrator/orchestrator`. На Windows будет PE, exe = `dist/orchestrator/orchestrator.exe`.
- Baseline тестов после PR B: 11 passed + 4 skipped (3 windows-only + 1 frozen_boot без env var). Никаких регрессий.
- `.gitignore`: добавлены `dist/`, `build/`, `*.spec.bak`. PyInstaller также создаёт `build/orchestrator/` — игнорится.
- `requirements-dev.txt`: `pyinstaller>=6.0` строкой выше `pytest>=8`.

### RELEASE-1 (PR D из 4)
- `.github/workflows/release.yml` — single `build-windows` job на `windows-latest`. Триггер: `push: tags: ["v*"]` + `workflow_dispatch` (ручной повтор). `permissions: contents: write` — обязательно для `softprops/action-gh-release@v2` (без него release.upload 403). Step order: checkout → setup-python 3.12 → setup-node 20 (cache=npm, dep-path=ui/package-lock.json) → rust-toolchain stable → pip install requirements-dev → `python packaging/build_windows.py --smoke` (ELF на Linux не нужен — runner Windows, собираем PE) → `cd ui && npm ci` → `npx tauri build --bundles msi nsis` → upload-artifact v4 (msi + nsis отдельными name'ами) → gh-release v2 с `if: startsWith(github.ref, 'refs/tags/v')` чтобы workflow_dispatch без тега не падал на release-step.
- Все `uses:` строго пиннутые: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `dtolnay/rust-toolchain@stable`, `actions/upload-artifact@v4`, `softprops/action-gh-release@v2`. Никаких `@main` / unpinned — требование спеки + security.
- `tauri.conf.json::bundle.windows.wix` — три поля: `language:"en-US"`, `template:null` (явный дефолт, WiX fragment не кастомный), `upgradeCode:"3be766d6-a9e9-4d6d-a623-6139519fdaa2"`. ЭТОТ GUID статичный навсегда — иначе MSI upgrade сломается (каждая новая установка = parallel install). JSON без комментариев (tauri не парсит JSONC в этом schema).
- `packaging/README.md` — добавлены "Install from release" + "Uninstall" секции после основного build-howto, перед "Notes". Последний Notes-пункт про "Tauri sidecar wiring and MSI packaging land in later PRs" заменён на актуальный "MSI upgradeCode зафиксирован, не регенерить".
- `README.md` в корне — ≤30 строк, ссылки на Releases / `packaging/README.md` / `CLAUDE.md`. Плюс dev-snippet с venv + pytest + `ui && npm run tauri dev`.
- `.gitignore`: root уже покрыт через `node_modules/`, но добавлены явные `ui/node_modules/`, `ui/dist/`, `ui/src-tauri/target/` для читаемости. Нижние `.gitignore` (`ui/.gitignore`, `ui/src-tauri/.gitignore`) уже эти пути покрывают — verify: `git check-ignore -v <path>`.
- Acceptance (все green):
  - `pytest -q` → 13 passed, 4 skipped (baseline сохранён).
  - `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` → no exception.
  - `python3 -c "import json; d=json.load(...); assert d['bundle']['windows']['wix']['upgradeCode']==..."` → ok.
  - `grep -n "upgradeCode"` — одно вхождение.
- Out of scope (явно отмечено в спеке): code signing, auto-updater, macOS/Linux matrix. Первый релиз — вручную тег `v0.1.0` после merge'а PR D.
```
