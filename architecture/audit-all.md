# Groft UI Audit — 45+ gaps (2026-04-19)

Сведён из 5 параллельных отчётов агентов (backend-dev, frontend-dev, tester, reviewer, auditor). Все файлы лежат в `architecture/audit-{role}.md` если нужен оригинал с контекстом.

---

## 🔴 Критичные (ломают базовый UX)

### Agents / AgentDrawer — всё нефункционально

- `ui/src/components/AgentDrawer.tsx:260` — textarea «System prompt» показывает **hardcoded шаблон**, не читает `.claude/agents/{name}.md`. verdict: **fake**
- `AgentDrawer.tsx:265` — кнопка «Сбросить» без `onClick`. verdict: **stub**
- `AgentDrawer.tsx:266` — кнопка «Сохранить» без `onClick`. verdict: **stub**
- `AgentDrawer.tsx:274` — кнопка «Очистить историю» без `onClick`. verdict: **stub**
- `AgentDrawer.tsx:277-279` — кнопка «Kill» без `onClick`. verdict: **stub**
- `AgentDrawer.tsx:282-283` — кнопка «Удалить» без `onClick`. verdict: **stub**
- `AgentDrawer.tsx:125-146` — слайдеры (maxTokens/temperature/stuckThreshold) и тогглы (autoRestart/pauseOnDone) — локальный state, **не сохраняется**, сбрасывается при смене агента.
- `AgentDrawer.tsx:238` — `TagInput tools` захардкожен `["Read","Write","Edit","Bash"]`. verdict: **fake**
- `AgentDrawer.tsx:228-248` — Select модели без Save-кнопки, изменение теряется. verdict: **missing-wiring**

### Backend — нет HTTP-эндпоинтов для Agents

- В `communication/server.py` **нет** `/agents/spawn`, `/agents/despawn`, `/agents/kill`, `/agents/clear-history`. Python-слой (`core/orchestrator.py` + `core/spawner.py`) полностью готов, но UI-кнопкам некуда звать. verdict: **missing-wiring**
- (Побочный gap: UI полагается на slash-commands через WS `to=opus`. Это единственный путь spawn/despawn сейчас.)

### Tasks view — read-only

- `ui/src/components/TasksView.tsx:139` — кнопка «Граф» без `onClick`
- `TasksView.tsx:140` — кнопка «+ Задача» без `onClick`
- `TaskCard` имеет `draggable?` prop, но **нет** `onDragStart/onDragOver/onDrop` — drag-drop не реализован
- Нет REST API для создания/редактирования/удаления задач
- Источник данных: `tasks/{backlog,current,done}.md`, read-only через `poll_tasks_loop`

### Composer — потеря данных

- `ui/src/components/primitives/Composer.tsx:73` — **`files[]` не попадает в `onSubmit`**. Пользователь видит прикреплённые файлы, но в WS фрейм они не уходят. **Молчаливая потеря данных**
- `Composer.tsx:163` — кнопка «Прикрепить» (compact) без `onClick`. verdict: **stub**
- `Composer.tsx:255` — кнопка «Прикрепить» (full) генерирует **фейковые** `file_1.py`, `file_2.py` вместо Tauri `dialog.open()`
- `Composer.tsx:258` — кнопка «Голосом» без `onClick`. verdict: **stub**
- `useOrchestrator.ts:56` — `isMode()` дропает `"review"`, хотя Composer его шлёт. Тип не добавлен.
- `ComposerModal.tsx:47` — hardcoded `claude-opus-4-7` в заголовке, не из state
- `CommandCenterLayout.tsx:58,108` — `openCmdK?` optional, кнопка «⌘K» молчит если родитель не передал handler. **CommandPalette-компонента нет вообще**

### Settings — полная in-memory беспамятность

- `UISettings` живёт в `useState<CommandCenterState>` в `App.tsx` — **ни localStorage, ни файла, ни бэка**. Refresh = всё сброшено на дефолты. `useUISettings.ts` не существует
- **Project-folder picker отсутствует** — `SystemSettings` показывает захардкоженный `/mnt/d/orchkerstr` в обычном `Input` без кнопки «Обзор», без `dialog.open()`. **Блокирует запуск на любой машине кроме dev-ноутбука**
- 11 toggle без `onChange` (уведомления, авто-рестарт, TDD, GPG, авто-коммит и т.п.)
- 5 кнопок без `onClick` (Перезапустить оркестр, Сбросить настройки, Удалить checkpoints, Очистить кэш, Сообщить о баге)
- `href="#"` на GitHub и docs.orch.dev
- `StubPanel`-заглушки: Discord, iMessage, Webhook

### Terminals — read-only, без управления

- Ввод В терминал из UI **невозможен** — нет `<input>`, нет `invoke`. Composer шлёт в оркестратора, не в tmux-pane
- Copy/Clear в `TerminalBlock`: `onClick` только `e.stopPropagation()`, тела нет
- Stop/Restart в meta-strip: нет `onClick`
- Pause All в header: нет `onClick`

### Messengers — частично работает

- Telegram wizard рабочий до Step 3, но `useChannels.configureTelegram` возвращает **сырой tmux stdout**, не структурированный ответ. `setStatus("connecting")` до прихода реального WS-события
- `username` после connect всегда `null`
- Discord/iMessage/Webhook = `StubPanel`

---

## 🟠 Архитектурные гапы, замеченные в бэкенде (я их нашёл пока спауном 5 агентов)

1. **REST `/agents` возвращает только WS-registered** (opus, ui), а `statuses` в той же эндпоинте — все спауненные. Два несогласованных источника. UI'у склеивать
2. **`config.yml` читается один раз при старте** spawner'а. Добавить роль без рестарта = нельзя. Убил бы 5 уже активных агентов
3. **WS-сервер дропает соединение кодом 1000 "reconnect"** после 3-4 команд из одного клиента. Наверное race с handshake
4. **Watchdog слишком агрессивно шлёт "wake up, are you there?"** пока агент пишет длинный отчёт. Reviewer получил wake-up на 1m40s thinking
5. **Sub-агенты спауненные через `spawner.spawn()` НЕ подключены к MCP** `claudeorch-comms` — у них нет способа слать сообщения через WS. Только opus-в-нулевом-окне имеет `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, а спауненные — нет

---

## Общий счётчик

| Категория | Штук |
|---|---|
| Кнопки без `onClick` | 17 |
| Toggle без `onChange` | 11 |
| Hardcoded inputs | 6 |
| Нет персистентности | 3 зоны (UISettings, AgentDrawer, Composer.files) |
| StubPanel-разделы | 5 (Discord, iMessage, Webhook + 2 в AgentDrawer) |
| Архитектурные дыры | 5 (нет HTTP-spawn API, нет MCP у sub-ов, нет CommandPalette, isMode drops review, no project picker) |
| **Итого gap'ов** | **~45** |
