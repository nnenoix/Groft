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
