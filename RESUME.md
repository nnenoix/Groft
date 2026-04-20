# Groft — Resume Plan

## Для чего это вообще

Один постоянно живой агент (backend-dev или frontend-dev) в tmux, который:
- Помнит твой кодовый стиль и историю решений между сессиями
- Принимает задачи через Telegram пока ты не за компьютером
- Не умирает ночью — watchdog перезапускает если завис

Это и есть ценность Groft. Не "4 параллельных агента", не DuckDB-стэк, не MessengerBus.

---

## Что сделано и работает

9 PR смержено в master. Код написан и протестирован (192 passed).

Реально полезное из сделанного:
- **Telegram bridge** — агент доступен с телефона (но /pair пока не работает полностью — см. ниже)
- **WS registry + routing** — агенты адресуются по имени, messages доходят
- **Watchdog** — не пингует opus (лидера), пингует workers
- **tmux C-j submit** — MCP send_message теперь реально сабмитит
- **Memory per agent** — накапливается между сессиями

Сделанное что скорее всего не нужно (но пусть лежит, не мешает):
- DuckDB decision log (красиво, но никто не читает)
- DuckDB context FTS (было проще читать весь memory файл)
- DuckDB messages/memory-log/git-history (5 баз данных на один оркестратор — перебор)
- Vision screenshot (полезно но не критично)
- iMessage bridge (только macOS, мало кому нужно)

---

## Что сломано прямо сейчас

### P0 — оркестратор не запустится после рестарта

**Файл:** `core/main.py` около строки 227

`decision_log` передаётся в `CommunicationServer(decision_log=decision_log)` до того как объявляется. Python падает с `UnboundLocalError` при старте.

**Фикс:** переместить `decision_log = DecisionLog(...)` выше по коду, до вызова `CommunicationServer`. Три строки.

**Проверка:** `python3 core/main.py --smoke` должен вернуть 0.

### Telegram /pair не работает

Пофикшено в коммите `9234105` (sync server↔bridge pair codes) но оркестратор не рестартован. После P0 фикса + рестарта должно заработать. Если нет — смотреть `communication/server.py` `/messenger/telegram/start-pairing`.

---

## Что делать в следующей сессии

### Шаг 1 — P0 фикс (5 минут)
```python
# core/main.py — переместить ДО CommunicationServer(...)
decision_log = DecisionLog(claudeorch_dir() / "decisions.duckdb")
await decision_log.initialize()
```
Потом `python3 core/main.py --smoke` зелёный → коммит → пуш.

### Шаг 2 — Рестарт + тест Telegram (10 минут)
```bash
./stop.sh
./start.sh
```
Открыть UI → Messenger → Telegram → Start Pairing → скопировать код → в Telegram-бот написать `/pair КОД`. Должно спарироваться.

Потом отправить `/ask opus привет` через бота. Проверить что opus ответил.

### Шаг 3 — Один нормальный рабочий сценарий (solo mode)

Не запускать 4 агента сразу. Запустить одного backend-dev:
```
Orchestrator.spawn_role("backend-dev")
```
Дать ему задачу через UI или Telegram. Наблюдать в tmux. Вот это и есть продукт.

Если работает → записать как "getting started" scenario в README.

### Шаг 4 — Watchdog heartbeat (если есть время)

Сейчас watchdog стучит по таймеру. Если backend-dev 20 минут молча пишет код — watchdog думает что он завис.

Простой фикс: tmux content diff. Если `capture-pane` текущий ≠ предыдущему за последние N минут — агент жив. Один файл, 30 строк.

---

## Чего НЕ делать

- Не запускать 4 агента параллельно на Max подписке — сожжёт лимит за 3 часа
- Не добавлять новые DuckDB таблицы без явной необходимости — их и так 5
- Не трогать Phase 14-20 из старого плана — это инфраструктура ради инфраструктуры
- Не рефакторить MessengerBus — нет второго пользователя который страдает от дублирования

---

## Если хочется двигаться дальше после базовой версии

Приоритет по реальной пользе:
1. **Hot-reload** — apply фикс без убийства opus pane. Подход: subprocess-per-subsystem (WS/REST/watchdog как child-процессы). Одна правка в `core/main.py`.
2. **README с getting started** — сейчас проект непонятен без часового объяснения
3. **Telegram /ask → ответ назад** — сейчас однонаправленно. Добавить `reply(chat_id, result)` когда агент завершил задачу.
4. **Секреты в keyring** — токены из plain JSON в OS keyring. Критично перед открытым репозиторием.

---

## Ключевые файлы

| Что | Где |
|-----|-----|
| P0 блокер | `core/main.py` ~строка 227 |
| Telegram bridge | `core/messengers/telegram.py` |
| WS сервер | `communication/server.py` |
| Watchdog | `core/watchdog/agent_watchdog.py` |
| Запуск | `./start.sh` / `./stop.sh` |
| Audit bugs P1 | `architecture/audit-phase12.md` |

## Экономика

Max-5x → solo агент: хватает надолго (агент 80% idle).
Max-5x → team 4 агента: сгорит за 3 часа активной работы.
API биллинг → team режим без ограничений, но дороже.
