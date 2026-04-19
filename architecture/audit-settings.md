# Settings View — Audit

_Date: 2026-04-19_

## Как хранится UISettings

`UISettings` живёт в `useState<CommandCenterState>` в `App.tsx` — **чистая in-memory React-state**.  
`localStorage` не используется, файл не пишется, бэкенд не вызывается.  
При перезагрузке страницы все настройки сбрасываются в `INITIAL_CMD_STATE`.

`useUISettings.ts` не существует.

---

## Критические gap'ы

### 1. Project-folder picker — отсутствует полностью
`SystemSettings` показывает захардкоженную строку `/mnt/d/orchkerstr` в обычном `Input`.  
Нет кнопки "Обзор…", нет вызова Tauri `dialog.open()`, нет сохранения пути.  
**Это блокирует запуск на любой машине кроме dev-ноутбука разработчика.**

### 2. AgentsSettings и SystemSettings — изолированы от персистентности
Оба компонента не получают `setState` prop.  
Все слайдеры, тоглы, инпуты — локальный `useState`, умирает при смене вкладки.

---

## Toggles без эффекта

| Компонент | Строка | Что сломано |
|-----------|--------|-------------|
| GeneralSettings | 270 | `<Toggle checked />` — нет `onChange`, всегда включено |
| GeneralSettings | 319, 334, 337 | Три тогла уведомлений — нет `onChange` |
| AgentsSettings | 458, 463, 482, 485 | Авто-рестарт, уведомлять opus, TDD, аудит — нет `onChange` |
| SystemSettings | 513, 540, 543 | Авто-реконнект, авто-коммит, GPG — нет `onChange` |

---

## Кнопки без onClick

- **Перезапустить оркестр** (line 549) — нет обработчика
- **Сбросить настройки** (line 555) — нет обработчика  
- **Удалить checkpoints** (line 561) — нет обработчика
- **Очистить кэш** (line 528) — захардкожено "142 MB", нет обработчика
- **Сообщить о баге** (line 603) — нет обработчика

---

## Hardcoded значения без сохранения

- `MCP server` = `"stdio://"` (захардкожено, не из конфига)
- `Ветка по умолчанию` = `"main"` (без onChange)
- `Select "Открывать на старте"` = `"Последний открытый"` (без onChange)
- Слайдеры Watchdog: threshold=3м, попытки=3, токены=120k — local state

---

## Разделы-заглушки

`MessengerSettingsView.tsx`:
- **Discord** — `StubPanel`, пустышка
- **iMessage** — `StubPanel`, "требуется macOS-bridge"
- **Webhook** — `StubPanel`, пустышка

`AboutSettings`:
- `href="#"` на GitHub и docs.orch.dev
- `KbdCapture` — декоративная кнопка, не захватывает нажатия

---

## Итог

| Категория | Кол-во |
|-----------|--------|
| Toggles без onChange | 11 |
| Кнопки без onClick | 5 |
| Hardcoded inputs | 6 |
| Нет персистентности (архитектурно) | 2 секции |
| Заглушки-разделы | 3 |
| **Критический gap** | project-folder picker |
