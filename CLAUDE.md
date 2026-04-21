# Groft — инструкции для Opus

## Кто ты
Ты одинокий опус-сессия в Claude Code. Агентов в tmux **нет** (убрано). Делегирование — через Task tool (Agent()). Субагенты короткоживущие: дал задачу → получил отчёт → влил в память.

## Шесть правил продукта (обязательны к соблюдению)

1. **Юзер не объясняет проект дважды.** Новая сессия, «продолжаем» → ты читаешь `CLAUDE.md`, `memory/*.md`, `architecture/*.md`, `.claudeorch/decisions.duckdb` и восстанавливаешь state.
2. **Не выдумываешь.** Не знаешь — говоришь «не знаю» и идёшь в код/доки/память. `get_relevant_context` MCP — первый ход перед ответом на фактический вопрос.
3. **Не ломаешь то что работало.** Каждое изменение → `pytest` → apply. Red tests → откат или фикс. Не показывать юзеру сломанный код.
4. **Юзер видит прогресс.** Перед многошаговой задачей вызови `set_plan(goal, steps)` (MCP), после каждого шага — `advance_step()`. План живёт в `memory/current-plan.md`, переживает /compact и рестарт. Не тишина «работаю».
5. **Юзер может вмешаться.** Паузы между шагами. Перед большой деструкцией — подтверждение.
6. **Учишься на ошибках.** Юзер поправил подход — сразу вызови `save_feedback_rule(rule, why, how_to_apply)` (MCP). Правило запишется в auto-memory + MEMORY.md индекс, следующая сессия увидит.

## Цикл работы

1. **Прочесть память.** Начало сессии: `MEMORY.md` + relevant `memory/*.md` + последние `architecture/decisions.md`.
2. **Оценить задачу.** Атомарная (1 файл / 1 функция / одно изменение) → делай сам. Шире → разбей или делегируй Agent() субагенту.
3. **Для делегирования — Task tool (Agent).** `isolation: "worktree"` когда изменения большие и нужна изоляция. Без worktree — для чтения/анализа.
4. **После каждого изменения** → `pytest` → git commit → если набралось 2–3 → `git push`.
5. **Перед сменой фазы** → `gh pr create` + merge в master.
6. **Каждое нетривиальное решение** → `log_decision(category, chosen, alternatives, reason, task_id?)` через MCP + запись в `architecture/decisions.md`.

## Структура

- `architecture/` — ТЗ, decisions.md, design-handoff.md, audit reports.
- `memory/` — `shared.md` + per-role `.md` + `archive/`.
- `.claudeorch/` — `decisions.duckdb`, `context.duckdb` (FTS по memory).
- `communication/mcp_server.py` — MCP server, тулы: `log_decision`, `get_relevant_context`, `reindex_my_context`, `ingest_subagent_report`, `set_plan`, `advance_step`, `get_plan`, `save_feedback_rule`.
- `core/` — только библиотеки: `context_store`, `decision_log`, `handoff`, `paths`, `logging_setup`, `subagent_ingest`, `step_planner`, `auto_learn`, `memory_rotation`.
- `memory/archive/` — ротированные блоки `session-log.md` (создаётся автоматически при переполнении порога 50 блоков). ContextStore индексирует архив вместе с основными файлами, поиск через `get_relevant_context` достаёт старые блоки прозрачно.
- `tests/` — pytest unit+integration. Зелёный suite — инвариант.

## Разработка

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

MCP-сервер запускается Claude Code автоматически через `.mcp.json`. Отдельный процесс Python-оркестратора больше не нужен.

## Интеграция с Claude Design

`ork-handoff/` → `core/handoff.py` при вызове записывает инвентарь в `architecture/design-handoff.md`. Не автомат — дёргается по необходимости. Opus читает инвентарь, анализирует дизайн, делегирует реализацию через Agent() субагентов.

## Что дальше

- ✅ **PR #1 (merged #25):** чистка агентной инфры.
- ✅ **PR #2 (merged #27):** subagent contract — отчёты субагентов записываются в память.
- ✅ **PR #3 (merged #28):** step-planner — `memory/current-plan.md` живёт между сессиями.
- ✅ **PR #4 (merged #29):** auto-learn — `save_feedback_rule` MCP-тул, корректировки юзера пишутся в auto-memory одним вызовом.
- ✅ **PR #5 (this):** Memory v2 — ротация `session-log.md` в `archive/`, `ContextStore` индексирует архив автоматически, `get_relevant_context` находит старые блоки без засорения стартового контекста.
