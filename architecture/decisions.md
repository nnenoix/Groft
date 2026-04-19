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
