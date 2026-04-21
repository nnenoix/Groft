# Phase 12 Audit — 2026-04-20

Reviewer: reviewer-agent, scope 46081cb..HEAD (phases 6–11), файлов просмотрено: 14 Python + pyproject.toml.

---

## P0 — блокеры (fix немедленно)

### P0.1 — `decision_log` передаётся в `CommunicationServer` до своей инициализации

**Файл:** `core/main.py:227`

**Проблема:**
`CommunicationServer(decision_log=decision_log)` вызывается на строке 227, а `decision_log = DecisionLog()` объявляется на строке 242.
В Python переменная, которой присваивается значение где-либо в теле функции, считается *локальной* на всём протяжении функции.
Обращение к локальной переменной до её присвоения — `UnboundLocalError` при каждом старте оркестратора.

**Риск:** Оркестратор не стартует. `main()` падает с `UnboundLocalError: cannot access local variable 'decision_log' before assignment`.

**Fix suggestion:** Переместить создание и инициализацию `DecisionLog` выше — до вызова `CommunicationServer`. Либо передать `decision_log=None` и позже вызвать `comm_server._decision_log = decision_log` после инициализации.

**Тест:** `test_main.py::test_main_starts_without_error` — мок подставляет stub-объекты и вызывает `asyncio.run(main())` до точки `await process_guard.wait_for_stop()`.

---

## P1 — важное (fix в этой фазе)

### P1.1 — Deprecated websockets API (`WebSocketClientProtocol`, `WebSocketServerProtocol`)

**Файлы:**
- `communication/client.py:8` — `from websockets.client import WebSocketClientProtocol`
- `communication/server.py:19` — `from websockets.server import WebSocketServerProtocol`

**Проблема:**
Используется `websockets.legacy` API, помеченный `DeprecationWarning` с версии 14.0 и поднятый до полноценного предупреждения в 16.0 (установленной версии). Новый API — `websockets.asyncio.client.ClientConnection` и `websockets.asyncio.server.ServerConnection`. В `websockets` 15+ `legacy` модуль может быть удалён в следующем minor-релизе.

**Риск:** После очередного обновления зависимостей бинарники перестанут импортироваться. В CI это уже генерирует 3 deprecation-warning'а при каждом прогоне тестов (из вывода pytest).

**Fix suggestion:** Мигрировать `CommunicationClient` на `websockets.asyncio.client.connect` (возвращает `ClientConnection`). `CommunicationServer` — на `websockets.asyncio.server.serve`. Типовые аннотации заменить на `ClientConnection`/`ServerConnection`.

**Тест:** Существующие интеграционные тесты в `tests/integration/test_spawn_flow.py` должны покрывать миграцию без изменений.

---

### P1.2 — `_context_store_lock` объявлен, но никогда не используется в `mcp_server.py`

**Файл:** `communication/mcp_server.py:289`

**Проблема:**
`_context_store_lock = asyncio.Lock()` объявлен как защита для `_context_store`, но `_get_context_store()` — обычная (не `async`) функция, не берущая блокировку. При параллельных вызовах `get_relevant_context` и `reindex_my_context` из разных MCP-запросов возможна двойная инициализация `ContextStore` с открытием двух соединений к одному `context.duckdb`.

Дополнительно: `core/main.py:211` и `communication/mcp_server.py:297` открывают один и тот же `context.duckdb` в двух независимых процессах (orchestrator + mcp_server). DuckDB допускает несколько writer-connection к одному файлу, но без координации возможны конфликты при `reindex_agent` (DELETE + INSERT + FTS rebuild) одновременно с поиском.

**Риск:** Редкий race: конкурентный `reindex` может оставить FTS-индекс в частично перестроенном состоянии, что приводит к `fts search failed` и откату на LIKE-поиск. Утечки соединений не возникает (GC закрывает лишний `ContextStore`), но нагрузка на DuckDB удваивается.

**Fix suggestion:** Преобразовать `_get_context_store` в `async`, обернуть в `async with _context_store_lock:`, либо — проще — открывать `ContextStore` в `read_only=True` в mcp_server (только поиск нужен там).

**Тест:** `tests/unit/test_context_store.py` — добавить тест на одновременный `reindex_agent` + `search` из двух потоков/coroutine-ов.

---

### P1.3 — `get_messages` в `mcp_server.py`: нет `ROLLBACK` при исключении между `BEGIN IMMEDIATE` и `COMMIT`

**Файл:** `communication/mcp_server.py:123–138`

**Проблема:**
```python
await db.execute("BEGIN IMMEDIATE")
# ... SELECT, UPDATE ...
await db.commit()
```
Если `json.loads(row[1])` (строка 139) или `db.executemany` бросает исключение, транзакция остаётся открытой. При `asyncio_mode=WAL` SQLite залочится, следующий `BEGIN IMMEDIATE` завис на таймауте.

**Риск:** Если в inbox попадёт невалидный JSON (например, от баги в `_consume`), `get_messages` заблокирует все последующие вызовы до перезапуска MCP-сервера.

**Fix suggestion:** Обернуть тело в `try/except` с `await db.rollback()` в `finally`, или использовать `async with db` как контекстный менеджер (aiosqlite поддерживает).

**Тест:** Внедрить невалидный JSON в `messages`, убедиться что второй вызов `get_messages` не зависает.

---

### P1.4 — `TmuxBackend.spawn` передаёт env-переменные через shell-строку без экранирования

**Файл:** `core/process/tmux_backend.py:51–55`

**Проблема:**
```python
env_prefix = " ".join(f"{k}={v}" for k, v in env.items()) + " "
shell_line = env_prefix + " ".join(cmd)
```
Значения переменных окружения (например, `AGENT_NAME=backend-dev`) вставляются в shell-строку без кавычек и экранирования. Если `v` содержит пробел, `;`, `&&`, `|` или `$(...)`, оболочка интерпретирует это как отдельные команды. `send-keys ... Enter` — это буквальный ввод в оболочку tmux, т.е. injection — реальная угроза.

Сейчас `AGENT_NAME` приходит только из `config.yml` (пути `known_roles()`), поэтому на практике безопасно. Но если кто-то добавит роль с пробелом в имени или вставит `WS_URL` с произвольным значением из env — вектор открыт.

**Риск:** При вредоносном или случайно некорректном значении `v` — выполнение произвольных команд в tmux-сессии оркестратора.

**Fix suggestion:** Использовать `shlex.quote(v)` при формировании `env_prefix`. Либо передавать env через `tmux setenv -t <session> KEY VALUE` отдельным вызовом (без shell-интерпретации).

**Тест:** `test_tmux_backend.py` — добавить случай с `AGENT_NAME` содержащим пробел и убедиться, что `_run_tmux` получает правильно экранированный аргумент.

---

## P2 — накопить в backlog

### P2.1 — `asyncio_mode = "auto"` применяет `@pytest.mark.asyncio` к синхронным тестам

**Файл:** `pyproject.toml:2`, тесты в `tests/unit/test_usage_tracker.py`, `test_webhook_bridge.py`, `test_vision.py`

**Проблема:** При `asyncio_mode = "auto"` pytest-asyncio автоматически помечает *все* тесты, включая синхронные `def test_*`. Это генерирует `PytestWarning: is marked with '@pytest.mark.asyncio' but it is not an async function` — 46 предупреждений в текущем прогоне. Предупреждения маскируют реальные проблемы и засоряют CI-лог.

**Fix suggestion:** Убрать `@pytest.mark.asyncio` с sync-функций, или переключить `asyncio_mode = "strict"` и добавить явные метки только на async-тесты.

---

### P2.2 — `ContextStore.reindex_agent` и `search` — синхронные DuckDB-вызовы, вызываются из async-кода в `main.py` без `run_in_executor`

**Файл:** `core/main.py:216`

**Проблема:**
```python
_count = context_store.reindex_agent(_agent_name, _memory_root)
```
`reindex_agent` делает `path.read_text()` + несколько DuckDB INSERT + FTS rebuild. Всё это — блокирующий I/O и CPU внутри async event loop. На больших файлах памяти (~10KB+) это блокирует loop на сотни мс, задерживая старт `comm_server`.

**Fix suggestion:** Обернуть в `await loop.run_in_executor(None, context_store.reindex_agent, ...)`.

---

### P2.3 — `_get_context_store` в `mcp_server.py` — инициализация вне lock, потенциально открывает несколько соединений

**Файл:** `communication/mcp_server.py:292–300`

Подробности см. P1.2. Выделено отдельно как самостоятельная проблема утечки соединений при гонке двух одновременных MCP-вызовов при первом запуске.

---

### P2.4 — `WebhookBridge` не логирует `secret` нигде, но persisted state хранит его в открытом виде

**Файл:** `communication/server.py:796`

**Проблема:**
```python
_write_webhook_state({"url": url, "secret": secret, "template": template})
```
`secret` хранится plaintext в `~/.claudeorch/messenger-webhook.json`. Утечка через backup/git/облачную синхронизацию. В Telegram/Discord аналогичная проблема — token в `messenger-telegram.json`.

**Риск:** Умеренный — файл находится в `~/.claudeorch` и обычно не попадает в git (`.gitignore`?). Но отсутствие защиты стоит задокументировать.

**Fix suggestion:** Добавить `.claudeorch/` в `.gitignore` (если не добавлен), задокументировать риск в README.

---

## P3 — nice-to-have

### P3.1 — `SessionManager.trigger_compaction` устарел по функционалу

**Файл:** `memory/session_manager.py:37–40`

`/compact` отправляется через `backend.send_text` — это правильный путь. Но `track_context_size` работает на основе `len(text) // chars_per_token`, что крайне грубо. Нет автоматического вызова `trigger_compaction` — это требует ручного вызова пользователем или внешнего polling. `SessionManager` вообще не подключён к `main.py`. Модуль существует, но не используется.

**Fix suggestion:** Либо подключить к `memory_compress_loop`, либо задокументировать как "TODO: integrate".

---

### P3.2 — `_context_store_lock` в `mcp_server.py` — мёртвый код

**Файл:** `communication/mcp_server.py:289`

`_context_store_lock` объявлен, но нигде не используется в `async with` или `await`. Создаёт ложное впечатление thread-safety. Удалить или использовать по назначению.

---

### P3.3 — `backfill_decisions.py` обращается к приватному атрибуту `dl._db_lock`

**Файл:** `scripts/backfill_decisions.py:111`

```python
async with dl._db_lock:
    await loop.run_in_executor(None, lambda: dl._conn.execute(...))
```
Нарушение инкапсуляции. `DecisionLog` должен предоставить публичный метод `clear_for_agent(agent, task_id=None)`.

---

### P3.4 — Тестовые warnings: `asyncio_default_fixture_loop_scope = "function"` без `loop_scope` в фикстурах

**Файл:** `pyproject.toml:3`

Объявлен `asyncio_default_fixture_loop_scope = "function"`, но часть фикстур в `tests/unit/` не имеет явного `scope`. При повышении к `session`-скоупу (для оптимизации) эта настройка будет конфликтовать. Минорное.

---

## Замечания / дискуссионное

**`get_messages` транзакция (P1.3):** aiosqlite с `WAL`-журналом автоматически откатывает незакоммиченные транзакции при закрытии соединения. Но поскольку `_db_conn` — singleton в process, "закрытие" не произойдёт до перезапуска MCP-процесса. Риск реален.

**Deprecated websockets (P1.1):** `websockets.legacy` убрать несложно, но нужно аккуратно портировать `_handle_connection` с `async for raw in ws` на новый API. Тесты в `test_spawn_flow.py` используют `websockets.WebSocketClientProtocol` напрямую — их тоже придётся обновить.

**Env-injection в spawn (P1.4):** Текущий набор ролей безопасен (`AGENT_NAME` берётся из `config.yml`). Угроза реализуется только при внешнем вводе в env. Но принцип наименьшей привилегии требует экранирования.

---

*P0: 1 блокер (UnboundLocalError при старте), P1: 4 важных, P2: 4 в backlog, P3: 4 nice-to-have.*
