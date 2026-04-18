# Current Task Specification

## HEALTH-1 — Express GET /health

**Цель:** Express API с одним endpoint `GET /health`.

**Контракт:**
- Метод: `GET`
- Путь: `/health`
- Ответ: `200 OK`, JSON `{"status": "ok", "timestamp": "<ISO-8601 UTC>"}`
- `timestamp` генерируется в момент запроса (`new Date().toISOString()`).

**Файлы для создания (в worktree `../orchkerstr-feature-health`):**
- `package.json` — минимальный, зависимость только `express`, script `start`.
- `server.js` — Express-приложение, слушает порт из `process.env.PORT || 3000`.

**Критерии приёмки:**
- `npm install` проходит без ошибок.
- `node server.js` стартует сервер.
- `curl http://localhost:3000/health` возвращает JSON с полями `status="ok"` и валидным ISO-8601 `timestamp`.

**Ветка:** `feature/health`.
