# Shared Team Memory

Общая память команды ClaudeOrch. Здесь фиксируются факты, договорённости и контекст, которые должны знать все агенты (backend-dev, frontend-dev, tester, reviewer): архитектурные инварианты, конвенции проекта, текущие ограничения, решения тимлида, затрагивающие более одного исполнителя.

---

## Конвенции проекта

### Backend
- **Рантайм:** Node.js + Express. Первая задача (HEALTH-1) закрепила стек.
- **Версия Express:** `^4.19.2`.
- **Порт по умолчанию:** `process.env.PORT || 3000`.
- **JSON-ответы:** через `res.json(...)`, без ручного `Content-Type`.
- **Timestamps:** ISO-8601 UTC через `new Date().toISOString()`.

### Процесс разработки
- Каждая задача → отдельный git worktree: `../orchkerstr-<branch>`.
- Ветки: `feature/<name>`. Merge в `master` через `--no-ff` с сообщением `Merge feature/...`.
- Commit исполнителя делает backend-dev/frontend-dev в worktree. Merge-commit делает тимлид.
- Tester запускается обязательно после каждого цикла разработки.

### Окружение (замечания tester)
- WSL2: после `node server.js &` нужен `sleep 2`, а не `sleep 1` — Node не успевает связать порт.
- После `kill` порт освобождается с задержкой ~1-2с.

## Открытые вопросы между агентами
_пусто_
