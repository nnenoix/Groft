# Tasks View Audit Report

## 1. UI Layer (TasksView.tsx)

### Кнопки без обработчиков
- **Line 139:** `<Icon.GitBranch /> Граф` — нет `onClick`
- **Line 140:** `<Icon.Plus /> Задача` — нет `onClick`

### Drag-drop
- TaskCard имеет `draggable?: boolean` (line 6) — **не используется**
- Нет `onDragStart`, `onDragOver`, `onDrop` обработчиков
- `cursor-grab` стиль есть, но функция не реализована

## 2. Store (agentStore.tsx)

### UPSERT_TASKS
- Полностью функционален (line 229–238)
- Может заменять `backlog`, `current`, `done` целиком
- **Готов к приёму обновлений из UI**
- Но UI не отправляет никаких изменений

## 3. Backend (poll_tasks_loop + task_parser.py)

### Источник данных
- `poll_tasks_loop()` (core/main.py:378) читает `tasks/{backlog,current,done}.md` каждые 5 сек
- `parse_tasks_dir()` парсит markdown секции `## TASK-ID — Title`
- Извлекает: id, title, priority (P0→high), deps, статус (из папки)
- Отправляет в UI через WebSocket фреймы (`push_tasks_to_ui`)

### Задачи (FS-based)
- `/tasks/backlog.md` — HEALTH-1 (заготовка)
- `/tasks/current.md` — пусто
- `/tasks/done.md` — HEALTH-1 (завершена 2026-04-18)

## 4. Missing Implementations

| Функция | Статус | Блокер |
|---------|--------|--------|
| Создание задачи (UI форма) | ❌ | Нет onClick на кнопке |
| Редактирование задачи | ❌ | Нет UI, нет HTTP API |
| Перемещение между колонками | ❌ | Нет drag-drop обработчиков |
| Сохранение изменений | ❌ | Нет HTTP API для write |
| Удаление задачи | ❌ | Нет UI, нет API |

## 5. Mock / Hardcoded

- **Нет mock-rendering** — всё реально читается с FS
- Задачи **hardcoded в markdown** (нет БД)
- Parser полностью полагается на структуру файлов

---

**Вердикт:** UI полностью read-only. Для управления задачами нужны: (1) HTTP API на бэке (POST/PUT/DELETE /tasks), (2) onClick обработчики на кнопках, (3) drag-drop в TaskCard, (4) синхронизация изменений обратно в markdown.
