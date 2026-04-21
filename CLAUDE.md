# Groft — инструкции для Opus

## Кто ты
Ты одинокий опус-сессия в Claude Code. Агентов в tmux **нет** (убрано). Делегирование — через Task tool (Agent()). Субагенты короткоживущие: дал задачу → получил отчёт → влил в память.

## Шесть правил продукта (обязательны к соблюдению)

1. **Юзер не объясняет проект дважды.** Новая сессия, «продолжаем» → ты читаешь `CLAUDE.md`, `memory/*.md`, `architecture/*.md` и восстанавливаешь state.
2. **Не выдумываешь.** Не знаешь — говоришь «не знаю» и идёшь в код/доки/память. `get_relevant_context` MCP — первый ход перед ответом на фактический вопрос.
3. **Не ломаешь то что работало.** Каждое изменение → `pytest` → apply. Red tests → откат или фикс. Не показывать юзеру сломанный код.
4. **Юзер видит прогресс.** Перед многошаговой задачей вызови `set_plan(goal, steps)` (MCP), после каждого шага — `advance_step()`. План живёт в `memory/current-plan.md`, переживает /compact и рестарт. Не тишина «работаю».
5. **Юзер может вмешаться.** Паузы между шагами. Перед большой деструкцией — подтверждение.
6. **Учишься на ошибках.** Юзер поправил подход — сразу вызови `save_feedback_rule(rule, why, how_to_apply)` (MCP). Правило запишется в auto-memory + MEMORY.md индекс, следующая сессия увидит.

## Enforcement (Claude Code hooks)

Правила живут не только в доке — каждое завязано на hook, который Claude Code вызывает между шагами. Детектор — `core/constitution.py`, скрипты — `scripts/hooks/`, регистрация — `.claude/settings.json`.

| Правило | Event | Скрипт | Что делает |
|---|---|---|---|
| #1 память | `SessionStart` | `session_start_memory_banner.py` | инжектит `additionalContext` с текущим планом, session-log, MEMORY.md, сводкой 6 правил |
| #2 не выдумывать | `Stop` | `stop_grounding_check.py` | если в последнем сообщении confident claim без Read/Grep/get_relevant_context в текущем ходу — блочит Stop с просьбой свериться |
| #3 не ломать | `PreToolUse` (Bash) | `pre_tool_use_tests_before_commit.py` | перед `git commit`/`git push` гоняет `pytest -q`, красные — deny с хвостом лога |
| #4 прогресс | `PostToolUse` (Edit/Write/set_plan/advance_step) | `post_tool_use_plan_nudge.py` | считает подряд правки, на 5-й без `set_plan` — stderr nudge + exit 2 |
| #5 вмешательство | `PreToolUse` (Bash) | `pre_tool_use_destructive_block.py` | на `rm -rf`/`git reset --hard`/`DROP TABLE`/…— deny; override маркер `# groft-user-confirmed` в команде после подтверждения |
| #6 учиться | `UserPromptSubmit` | `user_prompt_correction_nudge.py` | промпт похож на корректировку (`не так`, `stop`, `wrong`, …) — инжектит напоминание вызвать `save_feedback_rule` |

State между вызовами — `.claudeorch/hook_state.json` (счётчик правок). Override деструктива: добавить `# groft-user-confirmed` после подтверждения юзером. Тесты — `tests/unit/test_constitution.py` (детекторы) + `tests/integration/test_hooks_smoke.py` (скрипты через subprocess).

## Цикл работы

1. **Прочесть память.** Начало сессии: `MEMORY.md` + relevant `memory/*.md` + последние `architecture/decisions.md`.
2. **Оценить задачу.** Атомарная (1 файл / 1 функция / одно изменение) → делай сам. Шире → разбей или делегируй Agent() субагенту.
3. **Для делегирования — Task tool (Agent).** `isolation: "worktree"` когда изменения большие и нужна изоляция. Без worktree — для чтения/анализа.
4. **После каждого изменения** → `pytest` → git commit → если набралось 2–3 → `git push`.
5. **Перед сменой фазы** → `gh pr create` + merge в master.
6. **Каждое нетривиальное решение** → append в `architecture/decisions.md` (формат: `## YYYY-MM-DD — <category>: <chosen>` + `**Why:**` + `**Alternatives:**`).

## Структура

- `architecture/` — ТЗ, decisions.md, design-handoff.md, audit reports. **Архитектурные решения → append в `decisions.md` вручную** (DuckDB decision log retired в Phase 17).
- `memory/` — `shared.md` + session-log + feedback rules + `archive/`.
- `.claudeorch/` — рантайм state (`hook_state.json`, логи). DuckDB больше не используется.
- `communication/mcp_server.py` — MCP server, тулы: `get_relevant_context`, `ingest_subagent_report`, `set_plan`, `advance_step`, `get_plan`, `save_feedback_rule`.
- `core/` — только библиотеки: `context_store` (markdown grep), `handoff`, `paths`, `logging_setup`, `subagent_ingest`, `step_planner`, `auto_learn`, `memory_rotation`, `constitution`.
- `scripts/hooks/` — Python-скрипты, которые Claude Code дёргает через `.claude/settings.json` hooks.
- `memory/archive/` — ротированные блоки `session-log.md` (создаётся автоматически при переполнении порога 50 блоков). `get_relevant_context` делает grep по memory + archive, старые блоки находятся прозрачно.
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
- ✅ **PR #5 (merged #30):** Memory v2 — ротация `session-log.md` в `archive/`, `ContextStore` индексирует архив автоматически, `get_relevant_context` находит старые блоки без засорения стартового контекста.
- ✅ **PR #6 (merged #31):** Constitution enforcement — шесть правил зашиты в Claude Code hooks (`.claude/settings.json`), детекторы в `core/constitution.py`, скрипты в `scripts/hooks/`. Правила #3/#4/#5 блокируют действия; #1/#2/#6 инжектят контекст/нудж.
- ✅ **PR #7 (this):** DuckDB retirement — удалены `core/decision_log.py`, `scripts/backfill_decisions.py`, ~600 LOC; `context_store.py` переписан как markdown grep. MCP потерял `log_decision` и `reindex_my_context`; decisions теперь append в `architecture/decisions.md` руками.
