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
- `python-telegram-bot>=21` — Telegram bridge (long-polling, лениво импортится).

## core/messengers/telegram.py (Phase 6.1)

- `TelegramBridge(token, orchestrator, *, allowlist=None, backend=None, state_path=None, polling_factory=None)`.
- `is_valid_token_format(token)` — regex `^[0-9]+:[A-Za-z0-9_-]+$`. Валидация на конструкторе — `ValueError` если плохой.
- `start()` / `stop()` идемпотентные. `polling_factory(bridge)` подменяется в тестах на `asyncio.sleep(0)` loop — PTB не импортится.
- PTB импорт ленивый внутри `_default_polling` чтобы dep не тянулся в unit-тесты и в процесс без конфигурации Telegram.
- `register_pairing_code(code, ts)` + `accept_pairing(code, user_id, now, ttl=300)` — single-use nonce, автоматический sweep при accept.
- `handle_ask(agent, text)` — `orchestrator.active()` gate → `spawn_role` → `backend.list_targets()[agent]` → `backend.send_text(target, text)`.
- Persist `paired_user_id` в `state_path` (JSON, best-effort).

## communication/server.py — Telegram REST (Phase 6.1)

- Module-level: `TELEGRAM_PAIR_TTL=300.0`, `TELEGRAM_PAIR_CODE_LEN=6`, `_TELEGRAM_PAIR_ALPHABET` (без 0/O/1/I), `_generate_pair_code()` через `secrets`.
- `_telegram_state_path()` → `claudeorch_dir() / "messenger-telegram.json"`. Read/write helpers best-effort.
- `self._telegram_pairs: dict[str, float]` (in-process, loop-monotonic time). `self._telegram_clock = _monotonic_now` — подменяемый в тестах.
- `POST /messenger/telegram/configure`: regex-guard токен → `httpx.AsyncClient(timeout=5.0).get(https://api.telegram.org/bot<TOKEN>/getMe)` → 200+ok → persist `{token, username, paired_user_id?}`. Сохраняет `paired_user_id` при повторной конфигурации.
- `POST /messenger/telegram/start-pairing` → `{code}`. Старые коды остаются валидны 5 мин; GC на каждом issue.
- `GET /messenger/telegram/status` → `{status, username, paired_user_id}`. Состояния: `not-connected` (нет токена), `connecting` (есть токен, нет user_id), `connected` (и то и то).
- Bridge polling НЕ стартует в этом PR — только validate+save.

## tests/unit/test_telegram_bridge.py

- `_isolate_user_data` fixture (autouse): `monkeypatch.setenv("CLAUDEORCH_USER_DATA", tmp_path)` + `paths.install_root.cache_clear() / user_data_root.cache_clear()` до и после. Без этого тесты leak'ают в реальный `.claudeorch`.
- getMe mock: `httpx.MockTransport` + `monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)` — инжектит transport в каждый новый клиент.
- Fake clock: `srv._telegram_clock = lambda: now[0]` + list-based counter для манипуляции.

## core/messengers/telegram.py (Phase 6.2 — polling + handlers)

- `read_state_file(path)` / `load_paired_user_id(path)` — module-level helpers, shared между bridge (персист) и `core/main.py` (boot-hook). Best-effort, пустой dict на любую ошибку.
- `TelegramBridge.paired_user_id` (property) — отдельный slot, set'ится в `accept_pairing`. Construct seeds из allowlist если `len==1` (для сохранения поведения при рестарте из JSON).
- `_on_pair(update, context)`: `context.args[0]` → uppercase → `accept_pairing(code, user.id, loop.time())`. Reply `"Paired ✓"` или `"Invalid/expired code"`. Missing args → usage hint.
- `_on_ask(update, context)`: allowlist-check только по `paired_user_id` (не iterate allowlist). Strangers silently dropped (no reply — не leak'аем bot existence). `args[0]=agent`, `args[1:]=text`. Chat_id из `update.effective_chat.id` пробрасывается в `handle_ask`.
- `_on_fallback`: `MessageHandler(TEXT & ~COMMAND)` — reply "Use /ask <agent> <text> or /pair <code>."
- `handle_ask(agent, text, *, chat_id=None)` — echo confirmation через `_echo(chat_id, "[{agent}] sent: {first-line}")` via `application.bot.send_message`. Chat_id=None → skip echo (для прямых вызовов не из PTB).
- `_default_polling`: PTB 21+ pattern — `Application.builder().token(...).build()` → `add_handler(CommandHandler/MessageHandler)` → `initialize()` → `start()` → `updater.start_polling()` → park в `while bridge._running: sleep(1)`. PTB версия 22.7 работает с этим API.
- `stop()` тирит down Application: `updater.stop()` → `app.stop()` → `app.shutdown()` — всё best-effort, per-step swallow. Затем cancel task.

## core/main.py — Telegram boot hook

- `_maybe_start_telegram_bridge(orchestrator, backend)` → `TelegramBridge | None`. Читает `claudeorch_dir() / "messenger-telegram.json"` через `read_state_file`. Валидирует `is_valid_token_format(token)`. Seed allowlist из `paired_user_id` если int.
- Все failure modes (no file, bad token, PTB missing, ctor raise, start raise) → log + return None. Boot никогда не крашится.
- Вызов после `orchestrator = Orchestrator(spawner)`, перед `CommunicationServer(...)`. Teardown: `await telegram_bridge.stop()` перед `spawner.despawn_all()`.

## core/messengers/imessage.py (Phase 6.5 — outbound-only, macOS)

- `IS_MACOS` module-level (`sys.platform == "darwin"`) — monkeypatch target для тестов вместо мутации `sys.platform`.
- `IMessageBridge(contact)` — validate non-empty + len<=200; `.strip()` at construct.
- `notify(event, agent, text) -> bool` — non-darwin → log warning + False. На darwin: `_escape_for_applescript` (`\`→`\\`, `"`→`\"`), `tell application "Messages" to send "<body>" to buddy "<contact>" of service 1`, `subprocess.run(["osascript","-e",script], timeout=5, capture_output=True)`. FileNotFoundError/TimeoutExpired/generic → swallow+False.
- `test()` → `{ok, platform, error}` dict. На non-darwin возвращает без subprocess.
- Body format: `f"[{event}] {agent}: {text}"` — совпадает с webhook default template.

## communication/server.py — iMessage REST (Phase 6.5)

- `_imessage_state_path()` → `.claudeorch/messenger-imessage.json` (sibling webhook/telegram/discord).
- `sys` import в server.py — читается `sys.platform` live в endpoint'ах (не кэшируется).
- `POST /messenger/imessage/configure` body `{contact}`: shape-validate (non-empty, <=200) → persist `{contact}` → `{ok, platform, supported}`. `supported=false` НЕ блокирует — prep на Linux для sync на Mac.
- `POST /messenger/imessage/test` — 400 если no config; иначе `IMessageBridge(contact).test()` прямая передача результата (200 с ok=false на non-darwin/delivery fail — shape match с webhook/test).
- `GET /messenger/imessage/status` → `{status, contact, platform}`. `status="unsupported"` на non-darwin перекрывает saved config; на darwin: connected если есть contact, иначе not-connected.

## tests/unit/test_imessage_bridge.py

- Mock `sys.platform`: два отдельных хука — `monkeypatch.setattr(imessage, "IS_MACOS", True/False)` для bridge, `monkeypatch.setattr("communication.server.sys.platform", "darwin"/"linux")` для endpoint'ов. Server читает `sys.platform` live, bridge — свою module-level константу.
- `fake_completed(returncode, stderr)` — minimal stub с `.returncode/.stdout/.stderr`; не нужно строить реальный `CompletedProcess`.
- Escape-тест: верифицирует `\"hello\"` и `\\n` в сгенерированном script; проверяет структурную целостность `"<body>" to buddy "<contact>"`.
- 27 тестов, без новых deps. Baseline после: 126 passed, 4 skipped.

## core/vision.py (Phase 7 — experimental)

- `VisionError(Exception)` — единственный wrapping-type; ловят в REST/MCP handlers и сплющивают до 500 / "Vision error:" текста.
- `VISION_MODEL = "claude-sonnet-4-6"` — пиннут. Haiku vision не верифицирован; любые downgrade-попытки должны проходить через обновление константы.
- `capture_screen(monitor_idx=0)` — `run_in_executor(None, _capture_screen_sync, ...)`. mss 1-based (monitors[0] = virtual "all"), публичный API 0-based → `real_idx = monitor_idx + 1`.
- `ask_about_image`/`ask_about_text` — shared `_post_messages(payload)`: `x-api-key`+`anthropic-version:2023-06-01`+`content-type:application/json`. Timeout 30s. Non-200 → `VisionError("Anthropic API error {code}: {body}")`. Malformed body → `VisionError` через `_extract_text` (reject non-dict, empty content[], non-string text).
- Image content ordering: `[{image}, {text}]` — tests проверяют порядок (model behaviour зависит).
- Prompts — module-level templates (`_IMAGE_PROMPT_TEMPLATE`, `_TEXT_PROMPT_TEMPLATE`) чтобы тесты могли assertить точный текст.
- `agent_label=None`/`""` → falls back to `"unknown"` в тексте промпта.
- `_require_api_key` читает `ANTHROPIC_API_KEY` из env, raises VisionError если нет.

## communication/mcp_server.py — vision tools

- `_TMUX_SESSION = "claudeorch"` — duplicated constant между mcp_server.py и server.py. Разные процессы, share нельзя без IPC → duplicate осознанно.
- `_capture_pane_sync(agent_name)` — `subprocess.run(["tmux","capture-pane","-t",f"{session}:{agent}","-p"], capture_output=True, text=True, timeout=5)`. FileNotFoundError/TimeoutExpired/non-zero returncode → VisionError с stderr.
- `_capture_pane` = async wrapper через `run_in_executor(None, _capture_pane_sync, ...)`.
- `@server.tool()` декоратор FastMCP НЕ оборачивает function — возвращает raw callable. Тесты вызывают `mcp_server.see_screen(...)` напрямую (не `.fn`).
- Tool descriptions содержат warning про multimodal cost (5-10x на `see_screen`, ~5x Sonnet на `see_agent_pane` vs Haiku text baseline) — это единственный warning-канал до operator'а.
- VisionError в tool → возвращается как `f"Vision error: {exc}"` (MCP tool signature = str, не raise).

## communication/server.py — /vision/* REST

- `_VISION_TMUX_SESSION = "claudeorch"` + `_capture_tmux_pane_sync` — module-level, зеркалят MCP hook.
- `POST /vision/see-pane` body `{agent, question}`: validate → capture_tmux_pane → `ask_about_text(pane, question, agent_label=agent)`. VisionError → 500 `{error}`. Success → `{answer, token_usage: {input: null, output: null}}` — placeholder shape на будущее.
- `POST /vision/see-screen` body `{monitor_idx, question}`: `capture_screen` → `ask_about_image`. monitor_idx default 0, reject negative/non-int.
- Import `core.vision` внутри handler'а (lazy) чтобы случайный import mss не ломал boot на headless системах до первого vision-вызова.

## tests/unit/test_vision.py

- 20 тестов (1 skipped — capture_screen без display/mss).
- `_install_mock_transport` — same pattern как `test_telegram_bridge.py` для getMe: `httpx.MockTransport` + monkeypatch `httpx.AsyncClient.__init__` инжектит transport в каждый новый клиент.
- `_anthropic_ok(text)` — canned response `{content: [{type: text, text}], usage: {...}}`.
- Skip rule: `"CI" in os.environ or (sys.platform == "linux" and not DISPLAY) or not _mss_available()`.
- MCP tool tests: monkeypatch `mcp_server.capture_screen`/`ask_about_image`/`_capture_pane`/`ask_about_text` на fake coroutines, assert args passed.
- Baseline после: 145 passed, 5 skipped (было 126/4).

## Зависимости

- `mss>=9.0` в `requirements.txt`. НЕ добавляем в `requirements-dev.txt` (transitive через `-r requirements.txt`).
- SDK `anthropic` НЕ тянется — зовем HTTP напрямую через httpx (SDK heavy + pulls tokenizer).

## WSL/Wayland quirks

- WSL2 без X server: `DISPLAY=:0` может быть выставлен системой (WSLg), но реально grab может упасть ("XOpenDisplay failed"). Тест skip'ается по `_mss_available()` если mss не установлен, но даже при установленном mss на headless машине grab fail'нется — falling into `VisionError("screen capture failed: ...")`.
- macOS требует Screen Recording permission в System Settings; без неё CGDisplayCreateImage вернет черный кадр или пустой — не наш code path, делегируем операторам.
- Wayland (Gnome/KDE native): mss использует X11 API → нужен XWayland. Fallback на portals не реализован в mss 9 — документировано как known limitation.

## tests/unit/test_main_telegram_boot.py (Phase 6.2)

- `_maybe_start_telegram_bridge` тестируется напрямую (не весь `main()`). `CLAUDEORCH_USER_DATA` изолирован через fixture.
- Mock `TelegramBridge.start` через `monkeypatch.setattr(tg_module.TelegramBridge, "start", fake_start)` — `fake_start` лишь выставляет `self._running = True` (real_start вызывает polling factory → PTB import).
- Fake Update/Context classes в `test_telegram_bridge.py` (`_FakeMessage/_FakeUser/_FakeChat/_FakeUpdate/_FakeContext`) — mimic только те атрибуты которые handlers читают. Нет PTB dependency в unit тестах.
