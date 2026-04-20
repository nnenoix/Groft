# Groft Resume Plan — 2026-04-20

Проект поставлен в ящик. Этот файл — точка возобновления для любой будущей Claude-сессии.

## Как использовать этот файл

Запусти новую Claude-сессию в `/mnt/d/orchkerstr/`, прочитай:
1. `CLAUDE.md` — поведенческие правила проекта
2. **Этот файл** — текущее состояние + pending work
3. `architecture/audit-phase12.md` — bug list, с которого надо стартовать
4. `architecture/decisions.md` — архитектурная история

После этого у тебя полный контекст.

---

## Экономическое ограничение (важно)

**Team-режим Groft (параллельные tmux-агенты) не окупается на Max-подписке.** В сессии 2026-04-20 мы сожгли 5h rolling window за ~3 часа активной работы с 4 параллельными агентами (opus + backend-dev + frontend-dev + reviewer). Причины: shared 5h window на все claude-CLI процессы, `xhigh` thinking effort, полный CLAUDE.md в контексте каждой reply.

**Рабочая модель:**
- **Solo agent, long-running** (1 backend-dev накапливает memory сутками, доступен через Telegram) — подписка окупается, агент 80% idle.
- **Team-mode** — использовать только на API-биллинге, не подписке. Либо Max-20x + осторожная параллельность.
- **Task tool Claude Code** — для burst-параллели дешевле AgentSpawner, используй его внутри живого AgentSpawner-агента.

Это уже отражено в `CLAUDE.md` раздел «Dogfood-правило». Будущему Claude: не запускай 4 агента сразу если не знаешь, как оплачивается сессия.

---

## Что сделано в сессии 2026-04-20 (всё смержено в master)

| # | Фаза | PR | Коммит |
|---|------|----|----|
| 1 | Phase 10: hot-boot telegram bridge + watchdog skip_liveness для opus | #17 | `745ddf5` |
| 2 | Phase 8: Decision log (DuckDB + MCP + REST + backfill) | #18 | `53223ef` |
| 3 | Phase 8.5: UI Decisions tab | #19 | `217f9e5` |
| 4 | Phase 8.6: CLAUDE.md rule for log_decision | — | `9930024` |
| 5 | Phase 9: Context retrieval (DuckDB FTS + MCP) | #20 | `e6586b8` |
| 6 | Phase 11.3: tmux submit C-j fix | #21 | `329ff96` |
| 7 | Phase 11.2: no fallback-to-opus for unknown targets | #22 | `f0345b5` |
| 8 | Phase 11.1: role-aware WS registry | #23 | `608ac5d` |
| 9 | Phase 12 audit report (bugs found, НЕ починены) | — | `a149210` (ветка `chore/phase12-audit`) |

Тесты: **192 passed, 5 skipped** на момент останова.

---

## Куда продолжать (по приоритету)

### Стартовая точка: Phase 12 — P0 блокер

**Файл:** `core/main.py:227` — `UnboundLocalError` на старте оркестратора.

`decision_log` передаётся в `CommunicationServer(decision_log=decision_log)` на строке 227, но объявляется через `decision_log = DecisionLog()` на строке 242. Python считает переменную локальной на всей функции → обращение до присвоения = падение.

**Что делать первым в новой сессии:**
1. `git checkout master && git pull`
2. Прочитать `architecture/audit-phase12.md` (полный список: 1 P0, 4 P1, 4 P2, 4 P3)
3. Починить P0 (три строки: поднять `DecisionLog()` выше в функции) — это разблокирует рестарт оркестратора
4. Убедиться что orch стартует: `python3 core/main.py --smoke`
5. Смержить `chore/phase12-audit` в master, потом закрыть Phase 12 по PR на каждый P1

### Phase 12 — P1 (после P0)

Все детали в `architecture/audit-phase12.md`:
- P1.1: websockets deprecated API → мигрировать на `websockets.asyncio.client.connect` / `server.serve`
- P1.2: `_context_store_lock` не используется → обернуть `_get_context_store` в `async with lock`
- P1.3: `get_messages` без ROLLBACK в MCP server → `try/except/finally` с `db.rollback()`
- P1.4: `TmuxBackend.spawn` shell-инъекция через env → переделать на list-args без shell

### Phase 13–20 (roadmap)

Проставлен в taskstore (см. Task IDs ниже). Все ТЗ — в этом же файле ниже.

| Task | Фаза | Что |
|------|------|-----|
| #26 | 13 | Hot-reload orch без killa opus pane'а. Выбрать один из 4 подходов (A/B/C/D в брифе ниже). **Самая болезненная боль.** |
| #27 | 14 | Unified AgentRegistry — source-of-truth для AGENT_NAME / tmux / MCP / messenger. |
| #28 | 15 | Watchdog heartbeat вместо таймера — не спамить работающего агента. |
| #29 | 16 | Memory v2: structured sections, rotation, shared.md auto-compress. |
| #30 | 17 | Decision log — либо hard-enforce через MCP hook, либо удалить DuckDB layer (markdown достаточен). |
| #31 | 18 | MessengerBus — 4 мессенджера копируют политику/pair-flow. Вынести в общий bus. |
| #32 | 19 | Secret management — токены из plain JSON в OS keyring. Критично перед opensource-релизом. |
| #33 | 20 | Startup observability: `/ready` endpoint + per-subsystem progress. |

---

## Phase 13 — детальный бриф (самая важная фаза)

**Проблема:** любой фикс в `communication/` или `core/` = `stop.sh` + `start.sh` = убитый opus pane = потерянный контекст. Сейчас это главный источник трения в саморазработке.

**4 подхода, выбрать через `log_decision`:**
- A) Subprocess-per-subsystem (WS/REST/watchdog/messenger как child-процессы main orch, main держит opus WS-client постоянно)
- B) `importlib.reload()` для module-level changes (быстрый но хрупкий)
- C) Checkpoint + `os.execv()` self-replace (orch замещает свой бинарь, грузит checkpoint — opus всё равно теряется)
- D) Sidecar pattern (orch = тонкий WS-proxy, вся логика в reloadable sidecar-процессе)

**Acceptance:** opus сам применяет фикс в `communication/server.py` без killa своего pane'а.

---

## Technical debt (не в task-списке, но держать в голове)

Из `memory/project_groft_dogfood_bugs.md` (теперь помечено FIXED):
- Явно починено в Phase 11: tmux Enter, fallback echo, role-aware registry
- Осталось: MCP inbox persistence через `.claudeorch/mcp_inbox.db` (opus сказал "already fixed" через SQLite, но не верифицировано в этой сессии — проверить)

Из `architecture/decisions.md` (вручную ведётся opus'ом):
- Запись 2026-04-20 — self-dogfood валидация работает, но экономика team-mode на Max сомнительна (см. выше)

---

## Running state при останове (может быть уже не актуально)

- tmux session `claudeorch` с 4 окнами: `opus` / `backend-dev` / `frontend-dev` / `reviewer`
- Все процессы clude-CLI получили rate-limit "You've hit your limit · resets 11pm (Asia/Tomsk)"
- Оркестратор PID 2725, `.claudeorch/orch.pid`, жив
- Ветка `chore/phase12-audit` — только audit-report, ни одного fix commit'а

**При возобновлении:**
1. `./stop.sh` — чистая остановка
2. Применить P0 фикс локально (мелкая правка `core/main.py`)
3. `./start.sh` — проверить что orch поднимается
4. Дальше по плану

---

## Ссылки

- **Product name:** Groft (repo codename: claudeorch)
- **Repo:** `https://github.com/nnenoix/Groft`
- **Architecture decisions:** `architecture/decisions.md`
- **Audit report:** `architecture/audit-phase12.md`
- **Dogfood bugs (fixed):** `~/.claude/projects/-mnt-d-orchkerstr/memory/project_groft_dogfood_bugs.md`
- **Phase 10 security TODO:** `~/.claude/projects/-mnt-d-orchkerstr/memory/project_phase10_token_revoke.md`

---

## Для будущего Claude: короткий checklist перед стартом

- [ ] Прочитал `CLAUDE.md` целиком (особенно «Dogfood-правило» и «AgentSpawner vs Task tool»)
- [ ] Прочитал этот файл
- [ ] Прочитал `architecture/audit-phase12.md` (P0 + P1 перед стартом любых новых фаз)
- [ ] Проверил `git status` и актуальные ветки (`git branch -a`)
- [ ] Запустил `pytest tests/ -q` — убедился что baseline зелёный (ожидается ~192 passed)
- [ ] Перед spawn'ом агентов — честно оцени лимит пользователя, предложи solo-режим если Max-5x
