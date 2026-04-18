# Tester Memory

Персональная память tester агента (Haiku 4.5). Хранит контекст тестирования: структура тест-сьютов, покрытие по модулям, flaky-тесты и их причины, стратегии интеграционного vs юнит-тестирования, используемые тестовые фреймворки и моки.

## Sessions

### 2026-04-18 — HEALTH-1 (feature/health) — PASS

Worktree: `/mnt/d/orchkerstr-feature-health/`.

**Проверки:**
- `package.json` и `server.js` на месте.
- `package.json`: зависимость `express ^4.19.2`, script `start: "node server.js"`.
- Сервер стартует через `node server.js` (слушает `:3000`).
- `GET /health` → HTTP 200, тело `{"status":"ok","timestamp":"2026-04-18T07:19:40.906Z"}`.
- `timestamp` — валидный ISO-8601 UTC (`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}` ✓, суффикс `Z`).
- `GET /` → HTTP 404 (дефолтный Express 404, других endpoints нет).
- После `kill` порт освобождается (с задержкой ~2с на остановку процесса).

**Замечания / флаки:**
- Первый прогон с `sleep 1` после старта дал `HTTP 000` (Node ещё не успел связать порт в WSL2). Надёжнее `sleep 2` + `nohup ... > /tmp/server.log 2>&1 &`.
- После `kill $PID` процесс `node` умирает не мгновенно — нужно ждать ~1-2 сек, иначе порт остаётся в LISTEN.

**Инструменты:** `curl -s -w "\nHTTP %{http_code}\n"`, `pgrep -af`, `ss -ltn | grep :3000`.
