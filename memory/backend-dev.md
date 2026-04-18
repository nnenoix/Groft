# Backend Developer Memory

Персональная память backend-dev агента (Sonnet 4.6). Хранит контекст работы с API, БД, бизнес-логикой: схемы данных, принятые паттерны, известные баги и их обходы, используемые библиотеки и их версии, соглашения по структуре сервисов.

## Sessions

### 2026-04-19 — P3.2 HTML component parser (task #33)

Extended `core/handoff.py` to extract component identifiers from HTML files in
the handoff payload.

**Files:**
- `requirements.txt` (new) — `beautifulsoup4>=4.12`. Repo had no Python deps file
  before (no pyproject.toml either), so created one.
- `core/handoff.py`:
  - Added module constants: `_COMPONENT_CLASS_MARKERS` (9 markers), `_PASCAL_RE`.
  - Added `_extract_components(html_files: list[Path]) -> list[str]`. Imports
    `bs4` lazily with ImportError → warning + return []. Per-file try/except
    around `read_text` + `BeautifulSoup(text, "html.parser")`, `log.warning`
    with `exc_info=True` on failure. Collects tag names matching PascalCase or
    containing '-', plus class names whose lowercase contains any marker.
    Returns `sorted(list)` from a dedup set.
  - In `scan_and_record_handoff`: after `_collect_files`, filter HTML subset
    and call `_extract_components`. Appended components string to the
    fingerprint so changed components trigger re-emit and identical scans
    still dedupe. After writing `inventory + fingerprint_comment`, if
    components non-empty, append `## Обнаруженные компоненты` section with
    `- \`{name}\`` bullets.

**Решения:**
- Lazy bs4 import inside `_extract_components` keeps tests runnable on
  machines without bs4 — in practice install via requirements.txt is expected.
- `html.parser` lowercases tags (unlike lxml), so PascalCase tag detection
  rarely fires on real HTML; hyphenated custom elements and class-marker
  matching remain effective. ТЗ явно требует `html.parser, no lxml dep`.
- Components in fingerprint: `fingerprint_parts` list, joined with `\n`.
  Only added if non-empty, to keep fingerprints stable for HTML-less handoffs.
- `## Обнаруженные компоненты` kept as `##` per literal ТЗ string (not `###`),
  appended AFTER `fingerprint_comment` so the comment stays attached to the
  inventory block.
- `classes = tag.get("class") or []`; bs4 returns list for multi-valued attr,
  but defensive `isinstance(classes, str): classes.split()` branch handles
  rare cases (e.g. custom soup states).

**Тесты:** `python3 -m pytest tests/integration/test_spawn_flow.py -xvs` — 4/4 PASS.

**Smoke:**
- Real `ork-handoff/*.html` files are React shells with empty static classes
  → extractor correctly returns 0 components. No spurious section appended.
- Synthetic HTML with `<sidebar-item>`, `class="sidebar-nav info-card
  header-top drawer-open modal-backdrop"` → produces sorted list of 6 names.

### 2026-04-19 — P6.2 cosmetic polishes (task #34, commit e8ca798)

Three-item polish. Outcome:
- **Item 1 (mcp_server.py `_ensure_connected`)**: verified as already single-check under `_connect_lock`, not double-check. No change.
- **Item 2 (useWebSocket.ts line 171 dep array)**: skipped — ui/ has no `eslint.config.js`, so `npx eslint` errors before scanning. No warning to address; rationale for hand-picked deps already in inline comment above lines 153-155.
- **Item 3 (server.py snapshot branch, line 338)**: changed `_log_message(sender, None, "snapshot", msg)` → `_log_message(sender, agent_for_ui, "snapshot", msg)` so `messages.duckdb.msg_to` captures UI-facing agent name for analytics. `agent_for_ui` already computed at 333-337.

**Тесты:** `pytest tests/integration/test_spawn_flow.py -xvs` — 4/4 PASS.
**Коммит:** `e8ca798` в master, pushed.

### 2026-04-19 — P4.1 shared memory compression loop (task #31, commit f072696)

Extended per-agent `MemoryManager.compress` to also handle `memory/shared.md`,
driven by a periodic background task in `core/main.py`.

**`memory/manager.py`:**
- Added `import logging` + module `log`.
- Extracted shared body into private `_compress_path(path, log_agent_name, archive_prefix, default_title)`.
- `compress(agent_name)` now delegates to `_compress_path` with agent-specific params.
- New `compress_shared()` does the same for `shared_memory_path()`, archive prefix `"shared"`,
  logs with `agent_name="shared"`, default title `"# Shared Team Memory"`. Wrapped in
  try/except with `log.exception("compress_shared failed")` → `return False` so a crash can't
  bubble up into the scheduler.
- Threshold unchanged (`COMPRESSION_THRESHOLD_BYTES = 10 * 1024`). No compression happens
  on boot — only on loop tick. Pre-compression copy goes to `memory/archive/{prefix}-{ts}.md`.

**`core/main.py`:**
- Added `memory_compress_loop()` — `await asyncio.sleep(600.0)` then iterates
  `orchestrator.known_roles()` calling `memory_manager.compress(name)`, then
  `memory_manager.compress_shared()`. Each call wrapped in its own `try/except` with
  `log.exception`; outermost also wrapped so a single iteration crash never kills the loop.
- Created task after existing `inbox_task`/`tasks_task`/`handoff_task`; added `memory_task`
  to both teardown tuples (cancel + await).

**Тесты:** `python3 -m pytest tests/integration/test_spawn_flow.py -xvs` — 4/4 passed.

**Нюанс с race condition:** P2.2 (decisions.md) и P3.1 (handoff rescan) параллельно редактировали
те же файлы (`memory/manager.py`, `core/main.py`). Мои Edit'ы затирались их работой несколько раз.
Решение: дождался, пока P2.2 и P3.1 закоммитились, потом применил свои изменения на чистом HEAD
и сразу закоммитил. На будущее — при параллельной работе в том же worktree лучше договариваться
о порядке, либо использовать отдельный worktree.

### 2026-04-19 — P3.1 runtime handoff rescan (task #30)

Periodic rescan + on-demand `/rescan-handoff` + WS `handoff` frame to UI.

**Файлы:**
- `core/handoff.py` — `scan_and_record_handoff` теперь возвращает `list[str]` (relative paths) вместо bool. Модульный кэш `_last_fingerprints: dict[Path, str]` дедупит повторные вызовы (быстрый skip без чтения markdown). При смене fingerprint: апендим инвентарь как раньше + сохраняем new fingerprint + возвращаем список путей. Cross-process дедупа против существующего файла остаётся (на случай рестарта процесса).
- `communication/client.py` — новый метод `handoff_event(files: list[str])`, шлёт `{type:handoff, files:[...]}`.
- `communication/server.py` — в `_dispatch` ветка `mtype == "handoff"`: валидирует список, отфильтровывает не-строки, форвардит на UI через `_forward_to_ui`, дублирует в duckdb-лог.
- `core/main.py` — slash-команда `/rescan-handoff` (зовёт scan, всегда шлёт handoff_event даже с пустым списком). Корутина `handoff_poll_loop` спит 30 сек и зовёт scan; emit handoff_event только если non-empty. `handoff_task = asyncio.create_task(...)`, добавлено в обе teardown-tuple.

**Решения:**
- `list[str]` вместо bool/dict — простой контракт для loop: empty → skip emit, non-empty → emit.
- Module-level dict вместо instance state — `scan_and_record_handoff` это free function. Per-project_root key позволяет тестам с разными roots не конфликтовать.
- Cross-process dedupe сохранён через grep по существующему markdown — выживает рестарт оркестратора.
- `/rescan-handoff` шлёт event даже на empty diff — UI хочет видеть что команда сработала. Loop же фильтрует, чтобы не шуметь каждые 30 сек.

**Тест:** `pytest tests/integration/test_spawn_flow.py -xvs` — 4/4 PASS.
**Коммит:** `3e709f2 feat: P3.1 runtime handoff rescan...` в master, без push.
**Контекст:** работал параллельно с P2.2/P4.1/P6 в одном master без worktree. Лид несколько раз ресетил working tree во время моей работы; правки переносил заново. Финальный коммит — только мои 4 файла, остальные правки не тронуты.

### 2026-04-19 — P2.2 decisions.md auto-append (task #29)

Programmatic path to write `architecture/decisions.md` — WS frame `type=decision` + `/decide` slash command; Opus writes the file via `MemoryManager`.

**Файлы:**
- `memory/manager.py` — новый метод `append_decision(title, context, decision, rationale)`. Формат: heading `## <ISO UTC timespec=seconds> — <title>`, потом три H3 подсекции `Context` / `Decision` / `Rationale` как параграфы. `path.open("a")` создаёт файл если отсутствует, директория создаётся через `mkdir(parents=True, exist_ok=True)`. Файловая запись в `run_in_executor` — event loop не блокируется на диске. DuckDB лог операции `append_decision`.
- `core/main.py` — импорт `json`; в `_dispatch_inbox_command` ветка `/decide`. Берём остаток строки через `stripped[len(cmd):].strip()` (не `parts[1:]`, чтобы не коллапсить пробелы внутри JSON), `json.loads`, валидируем что все 4 поля — str, вызываем `memory_manager.append_decision(**payload)`. `memory_manager` уже в closure-scope main(). Ошибки JSON/валидации/записи логгируются через `log.info`/`log.exception` и возвращают без креша.
- `communication/server.py` — в `_dispatch` ветка `mtype == "decision"`. Валидирует 4 required строковых поля, синтезирует `{"type":"message","from":<sender>,"to":"opus","content":"/decide <json>"}` и отправляет через `_route_direct(SNAPSHOT_SINK_AGENT, ...)`. Сервер сам в файл НЕ пишет — только forward к Opus. Пишем duckdb-лог `decision` для аналитики.

**Ключевые решения:**
- Один write-site в системе — `MemoryManager.append_decision`. Сервер не дублирует фильсистемную логику, чтобы отделить транспорт от persistence.
- Форвард через `_route_direct`, а не через `_dispatch(message)`, — не нужен tmux-forward для этого кейса (у opus есть WS consumer). Чище + избегаем побочных эффектов.
- Парсинг `/decide` через slice вместо `parts[1:]` — в payload могут быть строки с двойными пробелами, `split()` их бы склеил.
- ISO-timestamp через `isoformat(timespec="seconds")` по ТЗ — выход `2026-04-19T12:34:56+00:00`, стабильный для сортировки.

**Тесты:** `python3 -m pytest tests/integration/test_spawn_flow.py -xvs` — 4/4 PASS (unchanged).

**Коммит:** сделан в master (один коммит feat:, без push).

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

### 2026-04-18 — B-UI-2 (communication/server.py)

Добавил параллельный форвардинг snapshot+status на UI-клиента.

**Файл:** `/mnt/d/orchkerstr/communication/server.py` — только этот.

**Что добавлено:**
- Константа `UI_SINK_AGENT = "ui"` рядом с `SNAPSHOT_SINK_AGENT`.
- Приватный helper `_forward_to_ui(payload: dict)` — best-effort push в сокет UI-клиента через `self._registry.get("ui")`. `ConnectionClosed`/любое исключение — silent + `_unregister` на всякий случай. Нет UI в реестре → `return`.
- В обработчик `snapshot`: ПОСЛЕ старого routing на opus и duckdb-лога — форвард `{"type":"snapshot","agent":<sender>,"terminal":<content>}`. Поле `terminal` беру из `msg["terminal"]`, с fallback на `msg["content"]` (совместимость, если клиент шлёт старое поле).
- В обработчик `status`: ПОСЛЕ duckdb-лога — форвард `{"type":"status","agent":<sender>,"status":<status>}`. DuckDB-запись не трогал, она как была (`_log_message(sender, None, "status", msg)`). Форвард только если `status` — строка (как и запись в `self._status`).

**Ключевые решения:**
- Отправка — через тот же `self._registry.get("ui")` что и `_route_direct`. Не стал переиспользовать `_route_direct` напрямую, потому что это отдельная семантика (форвард с новой формой payload, а не проксирование исходного), плюс здесь важен silent skip без логирования.
- `sender` — это имя из registration (`agent_name` из `_handle_connection`), как и в B-UI-1. Подделать через `msg["from"]` нельзя.
- Порядок в `status`: сначала `_status[sender]=status` → duckdb-лог → форвард на UI. Именно в таком порядке, чтобы UI получал событие уже после того, как сервер записал факт.

**Стиль:** `from __future__ import annotations`, PEP 604 unions, type hints. Без print/logging. Ошибки отправки на отвалившийся UI подавлены.

**Smoke-тест (из ТЗ) — прошёл:**
```
$ python3 -c "...CommunicationServer(); start; sleep 2; stop"
Server running
```
Завершился без трейсбека.

**Доп. функциональная проверка (локально):**
1. Подключил два клиента: `ui` и `backend-dev`. Агент шлёт `{"type":"snapshot","terminal":"pane contents here"}` → UI получает `{'type':'snapshot','agent':'backend-dev','terminal':'pane contents here'}`. Агент шлёт `{"type":"status","status":"busy"}` → UI получает `{'type':'status','agent':'backend-dev','status':'busy'}`.
2. Тот же сценарий без UI в реестре — сервер не падает, snapshot/status обрабатываются как раньше (opus-forward + duckdb).

**Нюансы:**
- Если UI зарегистрируется ПОВТОРНО (reconnect), старый сокет эвиктится в `_register` (поведение уже было). Новый сокет получает все последующие форварды.
- Для snapshot в логе duckdb `msg_to` = "opus" только если opus реально подключён; UI-форвард на это поле не влияет (правильно — duckdb-поле отражает первичный маршрут, а UI-форвард — отдельный канал).
