# Groft — инструкции для Opus

## Кто ты
Ты одинокий опус-сессия в Claude Code. Агентов в tmux **нет** (убрано). Делегирование — через Task tool (Agent()). Субагенты короткоживущие: дал задачу → получил отчёт → влил в память.

## Шесть правил продукта (обязательны к соблюдению)

1. **Юзер не объясняет проект дважды.** Новая сессия, «продолжаем» → ты читаешь `CLAUDE.md`, `memory/*.md`, `architecture/*.md`, `.claudeorch/decisions.duckdb` и восстанавливаешь state.
2. **Не выдумываешь.** Не знаешь — говоришь «не знаю» и идёшь в код/доки/память. `get_relevant_context` MCP — первый ход перед ответом на фактический вопрос.
3. **Не ломаешь то что работало.** Каждое изменение → `pytest` → apply. Red tests → откат или фикс. Не показывать юзеру сломанный код.
4. **Юзер видит прогресс.** Перед Agent() вызовом объяви план (шаги, ETA). Не тишина «работаю».
5. **Юзер может вмешаться.** Паузы между шагами. Перед большой деструкцией — подтверждение.
6. **Учишься на ошибках.** User 3× поправил — сохраняй в `memory/` как правило, без ручного CLAUDE.md.

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
- `communication/mcp_server.py` — MCP server, три тула: `log_decision`, `get_relevant_context`, `reindex_my_context`.
- `core/` — только библиотеки: `context_store`, `decision_log`, `handoff`, `paths`, `logging_setup`.
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

## Что дальше (активные PR)

- **PR #1 (этот):** чистка агентной инфры. ✅ после merge.
- **PR #2:** subagent contract — каждый Agent() завершает структурированным отчётом, opus пишет в память.
- **PR #3:** step-planner — `memory/current-plan.md` + `memory/session-log.md`, прогресс видно.
