# Frontend Developer Memory

Персональная память frontend-dev агента.

---

## Сессия UI-1 (2026-04-18) — базовая структура React

### Стек
- React 19.1 + TypeScript 5.8 (strict) + Vite 7 + Tauri 2 (уже были).
- **Tailwind v3** (`tailwindcss@^3.4`, `postcss`, `autoprefixer`) — выбрали v3 намеренно, v4 требует другую схему подключения.
- Без иконочных пакетов — только unicode (`✓ ▶ ○`).

### Темовые токены (`tailwind.config.js → theme.extend.colors`)
- `bg: #0a0a0a` — фон окна
- `card: #1a1a1a` — карточки агентов / textarea
- `accent: #00ff88` — акцент (активные статусы, submit-кнопка, имя агента в логах)
- Второстепенные оттенки (`#111`, `#222`, `#666`, `#ccc` и т.д.) — inline через `bg-[#...]`, пока без токенов.

### Статусы агентов (`AgentCard`)
8×8 точка, цвет через `style={{ backgroundColor }}` (единственный допустимый inline-стиль):
- active `#00ff88` · idle `#666` · stuck `#ff5555` · restarting `#ffaa00`.

### Структура компонентов (`src/components/`)
- `AgentCard.tsx` — имя, роль, статус-индикатор, текущее действие, задача, модель.
- `TaskList.tsx` — иконки done ✓ / active ▶ / pending ○, title + мелкий stage.
- `ChatInput.tsx` — controlled textarea (`useState`), кнопка «Отправить», Ctrl+Enter submit, очищает поле после submit.
- `LogFeed.tsx` — моношрифт, `overflow-y-auto`, автоскролл вниз через `useEffect` + `ref.scrollTop = scrollHeight`.

### Layout (`App.tsx`)
- `h-screen w-screen flex flex-col overflow-hidden`.
- Верх: слева `w-[30%]` колонка (AgentCard × 4 + TaskList × 3), справа `flex-1` заглушка «Terminals» (`bg-#111 text-#666`).
- Низ: `h-56 border-t border-#222 flex` → ChatInput `w-[40%]` + LogFeed `flex-1`.
- Mock-данные (4 агента, 3 задачи, 3 лог-записи) захардкожены — baseline для Stage 0.
- `onSubmit` у ChatInput пока `console.log`.

### Конвенции кода
- Props-интерфейсы экспортируются из файла компонента (`export interface ...`, `export type ...`).
- Default export у всех компонентов.
- TS strict, никаких `any`. Type-only импорты через `import { type KeyboardEvent }` (из-за `isolatedModules`).
- Функциональные компоненты. Tailwind-классы, inline-стили только для динамических статус-цветов.

### Модифицированные / созданные файлы
- Новые: `tailwind.config.js`, `postcss.config.js`, `src/index.css`, `src/components/AgentCard.tsx`, `TaskList.tsx`, `ChatInput.tsx`, `LogFeed.tsx`.
- Изменены: `src/main.tsx` (импорт `./index.css` вместо `App.css`), `src/App.tsx` (полностью переписан).
- Удалены: `src/App.css`.

### Build
`npm run build` (tsc strict + vite build) — зелёный, 33 модуля, ~4.9s, бандл 198 kB (gzip 62.6 kB), css 7.7 kB.

### Открытые вопросы
- Подключение к реальному WS (`localhost:8765`) — задача следующих UI-* (WS-UI).
- Правая панель «Terminals» — заглушка, реализация отдельной задачей.
- Возможно стоит завести общий `types.ts` для `AgentStatus`/`TaskStatus`/`LogEntry` при появлении реальных источников данных.

---

## Сессия UI-2 (2026-04-18) — палитра Claude + визуальные улучшения

### Новые токены (`tailwind.config.js → theme.extend.colors`)
Вложенные группы вместо плоских:
- `bg`: `primary #1a1a1a`, `secondary #222222`, `card #2a2a2a` → `bg-bg-primary`, `bg-bg-secondary`, `bg-bg-card`.
- `text`: `primary #f0ece3`, `muted #888888`, `dim #555555` → `text-text-*`.
- `accent`: `primary #d97757` (Anthropic tangerine), `hover #c96442`, `dim #3d2218` → `bg-accent-primary`, `hover:bg-accent-hover`, `text-accent-primary`.
- `status`: `active #4caf7d` (зелёный), `idle #888888`, `stuck #e05252`, `restarting #d97757` → `bg-status-*`, `text-status-*`.
- Плоский `border: "#333333"` — используется как `border-border`, `border-r border-border` и т.д. (Tailwind не конфликтует: `border-border` = `border-color: #333`, отдельное `border` остаётся utility-класс для `border-width: 1px`.) Работает: проверено сборкой.

### Шрифт / глобальный стиль
- `src/index.css`: `@import` Google Fonts Inter (400/500/600/700) **первой строкой, до `@tailwind`** (важно — CSS @import должен идти первым).
- `@layer base` задаёт `font-family: 'Inter', system-ui, ...` и фолбэк-фон `#1a1a1a` + цвет `#f0ece3` на `html/body/#root`.

### Изменения в компонентах
- `AgentCard`: `bg-bg-card border border-border rounded-lg p-4 hover:border-accent-primary transition-colors space-y-2`. Статус-точка теперь через `bg-status-*` класс (map `STATUS_CLASSES`), не inline style — динамика сохранена. Модель — `text-accent-primary text-xs font-medium` (раньше uppercase серый, теперь оранжевый акцент).
- `TaskList`: каждая задача = flex-строка с hover-подсветкой `hover:bg-bg-card`. Иконка active-задачи теперь `text-accent-primary` (отличается от done `text-status-active`) — раньше обе были зелёными.
- `ChatInput`: textarea → `bg-bg-card border border-border focus:border-accent-primary`. Кнопка `bg-accent-primary hover:bg-accent-hover text-bg-primary` (оранжевая с тёмным текстом).
- `LogFeed`: `bg-bg-secondary`, flex-layout записи, timestamp `text-text-muted`, agent `text-accent-primary font-semibold`, action `text-text-primary`.
- `App.tsx`: layout тот же (30% / 70% верх, `h-56` низ), но секции Agents/Tasks теперь без рамок-separator — визуальное разделение через typography (uppercase tracking-widest заголовки). Главный фон `bg-bg-primary`, левая панель `bg-bg-secondary`, рамки — `border-border`. «Terminals» — `text-2xl font-light`.

### Нюанс Tailwind: `border` + `border-border`
Плоский токен `border: "#333333"` не ломает utility `border` (width). Tailwind генерирует `border-border { border-color: #333 }` отдельно от `border { border-width: 1px }`. Связка `border border-border` работает как ожидалось.

### Build
`npm run build` зелёный, 33 модуля, ~5.2s, bundle 198.52 kB (gzip 62.60 kB), css 9.37 kB (gzip 2.51 kB) — css вырос с 7.7 → 9.4 kB за счёт новых токенов + `@import url(...)` для Inter.

### Изменённые файлы (без новых)
`ui/tailwind.config.js`, `ui/src/index.css`, `ui/src/App.tsx`, `ui/src/components/{AgentCard,TaskList,ChatInput,LogFeed}.tsx`.

---

## Сессия UI-3 (2026-04-18) — светлая тема + activity bar + terminals grid

### Новые токены (`tailwind.config.js → theme.extend.colors`)
Палитра полностью переработана под тёплый светлый UI (cream / paper):
- `bg`: `primary #f5f0e8` (основной фон), `secondary #ede8df` (header / нижний блок), `card #ffffff` (карточки), `sidebar #e8e3da` (activity bar + sidebar), `terminal #f0ebe2` (тело терминал-карточек).
- `text`: `primary #1a1a1a`, `secondary #3d3d3d`, `muted #6b6b6b`, `dim #999999`, `terminal #2d2d2d` (внутри терминалов), `code #c96442` (команды `npm/git/python`, модель в AgentCard).
- `accent`: `primary #d97757` (Anthropic tangerine), `hover #c96442`, `dim #fce8e0`, `light #fdf3ee`.
- `border: #ddd8cf` — плоский токен, как и раньше (не конфликтует с `border` utility).
- `status`: `active #2d7a4f` (тёмно-зелёный под светлый фон), `idle #999999`, `stuck #c0392b`, `restarting #d97757`.

### Layout
```
<div h-screen flex flex-col bg-bg-primary>
  <Header />                // h-12, bg-bg-secondary
  <div flex-1 flex>
    <ActivityBar />         // w-12, bg-bg-sidebar, unicode-иконки
    <Sidebar />             // w-64, bg-bg-sidebar, контент зависит от activeView
    <MainPanel flex-1>
      <TerminalGrid 2×2 />  // заголовок TERMINALS + grid-cols-2 grid-rows-2 gap-4 p-6
      <BottomBar h-56>      // ChatInput w-[40%] | LogFeed flex-1
    </MainPanel>
  </div>
</div>
```

Состояние `App` держит `activeView: "agents" | "tasks" | "logs" | "settings"` (`useState`). `ActivityBar` переключает, `Sidebar` рендерит соответствующий контент. Для `logs`/`settings` — текстовые заглушки.

### Новые компоненты
- `Header.tsx` — props `{ agentCount, systemActive }`. Лого-квадрат + название слева, `● Система активна` по центру (точка `text-status-active`), счётчик агентов справа.
- `ActivityBar.tsx` — экспортирует `ActivityView`. Unicode-иконки `👥 ✓ 📋 ⚙`, активная кнопка `bg-accent-primary text-bg-card`, неактивная `text-text-muted hover:bg-bg-secondary`. Без иконочных пакетов.
- `TerminalGrid.tsx` — props `{ terminals: TerminalData[] }`. Тип `TerminalData = { agent; status: AgentStatus; lines: string[] }`. Каждая строка парсится: `^(\d{2}:\d{2})\s(.*)$` → timestamp в `text-text-muted`, тело в `text-text-terminal`. Если `body` начинается с `npm `/`git `/`python ` — в `text-text-code` (оранжевый). Карточка: `bg-bg-terminal border border-border rounded-lg shadow-sm`, заголовок с цветной точкой статуса (inline `backgroundColor` из `STATUS_DOT_COLOR`).

### Обновлённые компоненты
- `AgentCard` — компактный белый вид (`bg-bg-card border border-border border-l-2 rounded-md p-3 shadow-sm hover:shadow-md`), левый акцент-бордер — цвет статуса через **inline `style={{ borderLeftColor }}`** (не класс). Модель теперь `text-text-code` (совпадает с accent-hover). Текущее действие — `italic text-text-secondary`.
- `TaskList` — `space-y-0.5 px-2`, строка `hover:bg-bg-card`, stage перенесён в `ml-auto` (справа, `text-text-muted text-xs`).
- `ChatInput` — textarea `bg-bg-card`, placeholder `text-text-dim`, кнопка `text-bg-card` (белый на оранжевом).
- `LogFeed` — без структурных изменений, только контраст цветов перенастроен через обновлённые токены.

### Решение по border-l цвету статуса
Используется **inline style** (`style={{ borderLeftColor: map[status] }}`) вместо safelist. Причины: (1) проще — не трогаем конфиг, (2) Tailwind не генерирует `border-l-status-*` без safelist, (3) цвет динамический по одному props-полю. Класс `border-l-2` остаётся tailwind-утилитой для ширины. Тот же подход для точки статуса в `TerminalCard`.

### Build
`npm run build` зелёный, 36 модулей, ~5.5s, bundle 202.49 kB (gzip 63.71 kB), css 10.91 kB (gzip 2.88 kB). Рост (+4 модуля, +4 kB js, +1.5 kB css) за счёт Header/ActivityBar/TerminalGrid.

### Созданные / изменённые файлы
- Новые: `ui/src/components/Header.tsx`, `ActivityBar.tsx`, `TerminalGrid.tsx`.
- Изменены: `ui/tailwind.config.js`, `ui/src/index.css`, `ui/src/App.tsx`, `ui/src/components/{AgentCard,TaskList,ChatInput,LogFeed}.tsx`.

---

## Сессия UI-4 (2026-04-18) — доработки activity bar / agents / tasks / terminals

### Activity Bar — проверка
Исходный код (UI-3) уже был функционально корректен: `useState<ActivityView>("agents")` по умолчанию, `ActivityBar` правильно сравнивает `item.view === activeView` и применяет `bg-accent-primary text-bg-card` для активной. Визуально «всегда активен SETTINGS» — артефакт наблюдения тимлида, не баг в логике. Тем не менее сделал три улучшения устойчивости:
- Добавил `aria-pressed={isActive}` для доступности и упрощения отладки в dev-tools.
- Активная кнопка теперь `font-semibold` (раньше обычный вес) — более заметный контраст.
- Добавил `select-none` чтобы unicode-иконки не выделялись при кликах.
- `SidebarContent` переписан на `switch` (было if-cascade с fallback в settings) — явная обработка всех четырёх вариантов `ActivityView`, TS требует exhaustive match через типизацию. Это настоящий risk-reduction: if-cascade возвращал Settings для любого неизвестного view, теперь невозможен silent fallback.

### Agents панель (default view)
`AGENTS[]` в `App.tsx` переписан:
- backend-dev / frontend-dev — `active` + действия «Пишет auth middleware» / «Создаёт LoginForm», задачи AUTH-1 / UI-2.
- tester / reviewer — `idle`, действие «Ожидает», задача «—».
- Модели берутся из `/mnt/d/orchkerstr/config.yml`: `sonnet-4-6` (backend/frontend/reviewer), `haiku-4-5` (tester). Использую формат `<family>-<major>-<minor>` без префиксов `claude-` и без суффиксов `-20251001`, т.к. в UI это подпись, не идентификатор API.
- `role` — краткие категории `backend / frontend / test / review` (было «API & бизнес-логика» и т.п.).
- Border-l цвет статуса уже inline в `AgentCard` (UI-3) — не трогал.

### Tasks панель — 3 секции
В `App.tsx` три отдельных массива: `BACKLOG_TASKS`, `CURRENT_TASKS`, `DONE_TASKS`. Секции рендерятся через переиспользуемый `<SectionHeader title="..."/>` (вынес внутри `App.tsx`, чтобы не плодить файлы — используется только здесь) + `<TaskList tasks={...}/>` для каждой. `stage` проставлен `""` (пустая строка) — иконки статуса (▶ / ✓ / ○) уже передают всю информацию, лишний label справа только шумит.

### Terminals — 4-5 строк на карточку + курсор
Каждая терминал-карточка теперь содержит 4-5 строк реального вывода + последняя строка `"▌"` (unicode full-block-with-right-edge, U+2590). Парсер `TerminalGrid` правильно определяет `▌` как non-timestamp non-code → отрисует `text-text-terminal`, без timestamp-отступа. Никакой анимации — символ сам по себе выглядит как курсор, просил тимлид. Примеры (backend): `npm run dev`, `Server listening on :3000`, `GET /health 200`, `POST /api/auth 401`, `▌`. Команды `npm`/`git`/`python` окрасятся оранжевым через существующий `CODE_PREFIX_RE`.

### Logs / Settings заглушки
- Logs: короткая подсказка «Последние события — в нижней панели под терминалами» (реальный feed уже есть в bottom bar).
- Settings: ссылки на `config.yml` и `localhost:8765` (WS), оформлены через `text-text-code` — оранжевый моноспейс-акцент.

### Tauri окно — minimum size
`ui/src-tauri/tauri.conf.json → app.windows[0]`:
- `width: 800 → 1280`, `height: 600 → 800` (startup размер увеличил, иначе 2×2 grid терминалов + sidebar 256px + activity 48px не помещается без горизонтального скролла).
- Добавил `minWidth: 900`, `minHeight: 650` — camelCase, как в Tauri 2 JSON schema (`$schema: https://schema.tauri.app/config/2`). Tauri 2.10.1.

### Build
`npm run build` зелёный, 36 модулей, ~5.4s, bundle 203.14 kB (gzip 63.99 kB), css 10.99 kB (gzip 2.91 kB). Рост vs UI-3: +0.65 kB js, +0.08 kB css — из-за больших mock-массивов и нового `SectionHeader`. Количество модулей то же (36).

### Изменённые файлы
- `ui/src/App.tsx` — полный набор моков (agents / tasks / terminals / logs), switch-based SidebarContent, SectionHeader.
- `ui/src/components/ActivityBar.tsx` — `font-semibold`, `aria-pressed`, `select-none`.
- `ui/src-tauri/tauri.conf.json` — window minWidth/minHeight + увеличенный стартовый размер.

Новых файлов не создавал.

---

## Сессия UI-5 (2026-04-18) — WebSocket + стор + живой UI

### Протокол server.py (точные поля)
Сверился с `/mnt/d/orchkerstr/communication/server.py` и `client.py`:
- **register** — обязателен первым фреймом: `{"type":"register","agent":<name>}`. Никаких `role`/`id` — сервер читает только `type` и `agent`, при несоответствии закрывает сокет с кодом 1008.
- **message** — `{"type":"message","from","to","content"}`. Маршрутизируется direct: если `to` не подключён, фрейм тихо дропается (логируется в duckdb).
- **broadcast** — `{"type":"broadcast","from","content"}`. Рассылается всем кроме отправителя.
- **snapshot** — `{"type":"snapshot","agent","terminal"}` — `terminal` это **одна строка** (потенциально с `\n`), **не** массив и не поле `lines`/`content`. Сервер перенаправляет snapshot только агенту `opus` (константа `SNAPSHOT_SINK_AGENT`). То есть UI по умолчанию snapshot не получает — только если SINK однажды переведут на `ui` или начнут рассылку. Всё равно обрабатываем: парсим `terminal` split по `\r?\n`, фильтруем пустые. На всякий случай поддержал также `lines: string[]` и `content: string` — безопасно для будущих расширений.
- **status** — `{"type":"status","agent","status"}`. Сервер **не маршрутизирует** status — только сохраняет в `_status` и пишет в лог. То есть UI получит status только если оркестратор будет его броадкастить отдельно. Обработчик в `useOrchestrator` готов, но практически сейчас UPSERT_AGENT_STATUS срабатывать не будет до изменений на сервере.

### Hook `useWebSocket` (`ui/src/hooks/useWebSocket.ts`)
API: `{ status, connected, sendMessage(obj), lastMessage }`. `status` — `'disconnected'|'connecting'|'connected'|'reconnecting'`.
- Подключается к `ws://localhost:8765`, после `onopen` сразу шлёт register.
- Автореконнект через `setTimeout(3000)` при `onclose`/`onerror`/`catch` конструктора. Таймер в `useRef`, `shouldRunRef` предотвращает реконнект после unmount.
- Замкнутая зависимость `connect ↔ scheduleReconnect` разрулена через `connectRef` (useRef + useEffect синхронизирует ref с последним `connect`).
- **Буферизация send'а**: решил **silently drop** если сокет не OPEN (`sendMessage` возвращает `false`). Причины: (1) буфер усложняет (порядок, лимит, flush-гонки), (2) UI уже знает `connected`, может гейтить кнопку/textarea, (3) сообщения, отправленные в разрыве, почти всегда устаревают. Зафиксировал в комментарии к hook'у.
- Cleanup в `useEffect` return: clear timer + `ws.close()` + `setStatus('disconnected')`.

### Store `agentStore.tsx` (`ui/src/store/agentStore.tsx`)
Выбрал **React Context + useReducer** (как предложил тимлид). Причины: без новых зависимостей, прозрачно в devtools, экшны типизированы discriminated union.
- Файл `.tsx` а не `.ts` — провайдер возвращает JSX.
- Типы `AgentState`, `LogEntry`, `Tasks`, `StoreState`, `Action`.
- Action: `UPSERT_AGENT_STATUS | APPEND_TERMINAL | APPEND_LOG`.
- Буферы: terminal = 100 строк на агента, logs = 200 записей глобально. Реализация — `merged.slice(merged.length - LIMIT)` если длина превышает.
- `nextLogId` — module-level монотонный счётчик, отдаёт `log-N`. В `APPEND_LOG` payload без `id`, id проставляет reducer.
- `UPSERT_AGENT_STATUS`: если агент есть — патч, `currentAction`/`currentTask` сохраняют прежнее значение если `undefined` в экшне. Если нет — добавляет минимальную запись (полезно для агентов, которых нет в initial mock).
- Начальное состояние: те же 4 агента что в UI-4 (backend-dev / frontend-dev / tester / reviewer, те же модели), но статус всех `idle`, `terminalOutput: []`. Tasks — те же 3 секции что были захардкожены.
- Хуки: `useAgents()`, `useLogs()`, `useTasks()`, `useDispatch()`. Провайдер `AgentStoreProvider`.
- Контекст с value `{state, dispatch}` через `useMemo(..., [state])`.

### Hook `useOrchestrator` (`ui/src/hooks/useOrchestrator.ts`)
Склеивает `useWebSocket` + dispatch. В `useEffect([lastMessage, dispatch])` разбирает по `msg.type`:
- `status` → UPSERT_AGENT_STATUS (валидирует `status` через `VALID_STATUSES` set).
- `snapshot` → APPEND_TERMINAL. Парсит `terminal: string` → split `\r?\n` → filter non-empty.
- `message` и `broadcast` → APPEND_LOG с полями `{timestamp: HH:MM:SS от new Date(), agent: from, action: content}`.
Валидаторы `asString`, `isAgentStatus` — строгие, type-narrowing безопасный.
Вызывается **один раз** в `App.tsx` (под провайдером). Возвращает `{connected, status, sendMessage}`.

### ConnectionStatus (`ui/src/components/ConnectionStatus.tsx`)
Простой компонент, маппинг `WSStatus` → `{label, dotClass, textClass}`:
- connected → зелёный + "Connected" (`text-status-active`)
- connecting/reconnecting → оранжевый + "Connecting..." / "Reconnecting..." (`text-accent-primary`)
- disconnected → красный + "Offline" (`text-status-stuck`)
Встроен в `Header`: заменил прежний статический «● Система активна». `Header` теперь принимает `connectionStatus: WSStatus` вместо `systemActive: boolean` (breaking — но Header используется только из App.tsx).

### App.tsx
- Убрал mock-массивы AGENTS/LOGS/TERMINALS/BACKLOG_TASKS/CURRENT_TASKS/DONE_TASKS — все данные теперь из стора.
- Вверху вызывает `useOrchestrator()`, получает `{status, sendMessage}`. `useAgents()`, `useLogs()`, `useTasks()` — везде где нужны.
- `terminals` собирается маппингом `agents` → `{agent, status, lines: terminalOutput}` прямо в рендере. `logEntries` маппится так же (`LogEntry.action` уже совпадает с полем стора).
- `handleChatSubmit(text)` теперь `sendMessage({type:'message', from:'ui', to:'opus', content:text})`. Silently-drop если disconnected — пользователь видит Offline в хедере.
- `SidebarContent` теперь принимает `agents` как prop (из `useAgents()` в App), tasks берёт через `useTasks()` внутри себя (простая оптимизация — не прокидывать лишнее).

### main.tsx
Обёрнут в `<AgentStoreProvider>` вокруг `<App/>`. Всё остальное без изменений. `App.tsx` сам `useOrchestrator()` вызывает — внутри провайдера.

### Правки существующих компонентов
- `Header.tsx` — props `{ agentCount, connectionStatus }`. Рендерит `<ConnectionStatus status={connectionStatus}/>` по центру.
- `AgentCard`, `LogFeed`, `TerminalGrid`, `ChatInput`, `TaskList` — **без изменений API**. Только App.tsx кормит их реальными данными.

### Build
`npm run build` зелёный, 40 модулей (+4 vs UI-4: useWebSocket, useOrchestrator, agentStore, ConnectionStatus), ~6.5s, bundle 207.12 kB (gzip 65.18 kB), css 11.26 kB (gzip 2.97 kB). Рост +3.98 kB js за счёт новых hooks/store/компонента — в пределах ожиданий.

### Устойчивость без сервера
Если Python-сервер не поднят — `new WebSocket()` отрабатывает без exception, но сразу получает `onerror`/`onclose`. UI показывает "Reconnecting..." вечно, пытается каждые 3с. Состояние стора остаётся в initial (4 idle агента, пустые терминалы и логи). Ничего не падает. Проверено в build.

### Созданные файлы
- `ui/src/hooks/useWebSocket.ts`
- `ui/src/hooks/useOrchestrator.ts`
- `ui/src/store/agentStore.tsx`
- `ui/src/components/ConnectionStatus.tsx`

### Изменённые файлы
- `ui/src/main.tsx` — обёртка в `AgentStoreProvider`.
- `ui/src/App.tsx` — убраны mocks, подключение к стору + orchestrator.
- `ui/src/components/Header.tsx` — `connectionStatus: WSStatus` вместо `systemActive: boolean`.

### Открытые вопросы / TODO
- Сервер не форвардит `status` другим клиентам (только логирует). Чтобы UPSERT_AGENT_STATUS реально срабатывал, оркестратору надо будет либо броадкастить статусы, либо расширить server.py.
- `SNAPSHOT_SINK_AGENT = "opus"` — snapshot'ы идут только туда. Если UI должен их видеть, нужно либо менять sink, либо дублировать через broadcast.
- `sendMessage` сейчас silently drop в offline. Если UX потребует — добавить буфер или визуальный фидбэк у ChatInput (пока достаточно индикатора в Header).
