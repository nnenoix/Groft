# Current Task

## Pivot 2026-04-21 — solo-opus-only model

Отказ от long-lived tmux-агентов (AgentSpawner/WS/watchdog). Groft = одна Claude Code сессия (opus) + субагенты через Task tool + память + MCP-тулы (`log_decision`, `get_relevant_context`, `reindex_my_context`).

Цель стройки — шесть правил продукта из `memory/project_groft_product_charter.md`:
1. Не объяснять дважды (✅ ~90% — memory/decisions/CLAUDE.md).
2. Не выдумывать (⚠️ prompt-layer).
3. Не ломать что работало (❌ нужен startup smoke + pre-merge gate).
4. Прогресс видно (❌ нет step-planner).
5. Юзер может вмешаться (⚠️ только git-rollback).
6. Учиться на ошибках (❌ авто-ingest из поправок).

## Активные PR

- **PR #1 (этот):** cleanup — удалить агентную инфру. 25 тестов зелёные post-cleanup.
- **PR #2 (после merge #1):** subagent contract — `{did, changed_files, decisions, questions, memory_deltas}` отчёт + `ingest_subagent_report(...)` pipeline.
- **PR #3:** step-planner + `memory/current-plan.md` + `memory/session-log.md`.

Дальше по фазам — Phase 16 (memory v2), Phase 17 (decision log enforcement), Phase 20 (startup observability), Phase 19 (secrets).
