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
