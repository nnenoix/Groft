# Code Review: React UI

Дата: 2026-04-18
Ревьюер: ui-reviewer

Скоуп: `ui/src/**` (App, main, index.css, 8 компонентов, 2 хука, store) + сверка контракта с `communication/server.py` и `ui/src-tauri/tauri.conf.json`.

## Критично (блокирует работу)

- **Tasks в сторе — полностью mock, нет WS-действия для их обновления.**
  `ui/src/store/agentStore.tsx:107-128` задаёт `INITIAL_TASKS` (b1/b2/c1/d1) и никакая `Action` их не трогает (`Action` = `UPSERT_AGENT_STATUS | APPEND_TERMINAL | APPEND_LOG`). В UI навсегда видны фейковые `AUTH-1 / UI-2 / HEALTH-1 / INIT-1`, независимо от того, что делает оркестратор. Memory UI-5 прямо обещает, что tasks заменятся WS-данными — этого не произошло. Рекомендация: завести `UPSERT_TASKS` / `SET_TASKS` action, а на стороне сервера (или хотя бы в `useOrchestrator`) — протокол `{type:"tasks", backlog, current, done}`. До этого TASKS-панель вводит пользователя в заблуждение.

- **INITIAL_AGENTS — захардкоженный список из 4 агентов, никогда не синхронизируется с сервером.**
  `ui/src/store/agentStore.tsx:68-105`. UI должен получать список подключённых агентов через REST `localhost:8766/agents` (см. `server.py:144`) и/или через status-broadcast. Сейчас:
  (1) если реальных агентов меньше — UI всё равно показывает 4 idle-карточки с вымышленными моделями;
  (2) если больше — неизвестный агент добавляется через `UPSERT_AGENT_STATUS` с `role = action.name` (`agentStore.tsx:154`) и пустой моделью.
  Рекомендация: либо polling `GET /agents` раз в N секунд, либо расширить server.py рассылкой присутствия, плюс action `SET_AGENT_ROSTER`. Стартовое состояние — пустой массив.

- **`ChatInput` очищает поле до подтверждения отправки.**
  `ui/src/components/ChatInput.tsx:10-15` всегда `setText("")`. `sendMessage` в `useWebSocket.ts:157-170` возвращает `false` при offline и **молча дропает**. Пользователь видит пустое поле и считает, что сообщение ушло, хотя оно потеряно. Рекомендация: `if (!onSubmit(trimmed)) return;` (сделать `onSubmit` возвращающим `boolean`) либо визуальный toast/красная подсветка при offline.

## Важно (нужно исправить)

- **Контракт `status`: UI ждёт `currentAction`/`currentTask`, сервер их не шлёт.**
  `useOrchestrator.ts:60-71` читает `msg.currentAction`, `msg.currentTask`. В `server.py:243-245` на UI форвардится строго `{type:"status", agent, status}` — никаких дополнительных полей. Поля будут всегда `undefined` → reducer сохраняет прежние значения. Либо расширить сервер (включая `_forward_to_ui`), либо убрать эти поля из `UPSERT_AGENT_STATUS` payload, чтобы не создавать иллюзию контракта.

- **Таймстемп логов берётся на стороне UI, а не от отправителя.**
  `useOrchestrator.ts:21-25` `nowHHMMSS()` — локальное время приёма фрейма. При лагах или разнице часовых поясов порядок в LogFeed может не соответствовать порядку событий. Рекомендация: поле `timestamp` из фрейма (если сервер добавит) либо хотя бы ISO-время приёма без преобразования к HH:MM:SS.

- **`APPEND_TERMINAL` для неизвестного агента молча теряет строки.**
  `agentStore.tsx:179-191`: `if (idx === -1) return state;`. Если агент подключился после старта UI и сразу прислал snapshot, строки будут дропнуты, пока его не заведёт `status`-фрейм. Рекомендация: при `idx === -1` создавать минимальную запись как в `UPSERT_AGENT_STATUS`.

- **React StrictMode двойной mount даёт лишний register.**
  `main.tsx:8` использует `<React.StrictMode>`. `useWebSocket.useEffect` (`useWebSocket.ts:138-155`) на первом mount открывает сокет, cleanup закрывает, второй mount открывает снова. Сервер `_register` (`server.py:188-198`) увидит вторую регистрацию `"ui"` и вышвырнет первое соединение с кодом 1000. В dev — безобидно, но это лишний цикл каждую перезагрузку. Рекомендация: либо guard через `useRef` на "first mount done", либо оставить и задокументировать.

- **`message` и `broadcast` обрабатываются идентично — дубль кода.**
  `useOrchestrator.ts:93-112`. Один case через fallthrough (или общий helper) нагляднее и устраняет риск расхождения. Мелочь, но два одинаковых блока уже есть.

- **Header: плохая плюрализация.**
  `ui/src/components/Header.tsx:17` — `{agentCount} агента` работает только для 2/3/4. Для 1 ("1 агент") и 5+ ("5 агентов") русская морфология другая. Рекомендация: функция-плюрализатор или нейтральное "Агенты: N".

- **`sendMessage` принимает `unknown`.**
  `useWebSocket.ts:157` — `(obj: unknown) => boolean`. В проекте TS strict, нет `any`, но `unknown` у публичного API удаляет контроль над исходящими фреймами. Рекомендация: типизированный union `OutgoingFrame = RegisterFrame | MessageFrame | BroadcastFrame | StatusFrame | SnapshotFrame`; `sendMessage(obj: OutgoingFrame)`.

- **`ChatInput` всегда шлёт на `"opus"`.**
  `App.tsx:112-119`: `to: "opus"` захардкожено. Если появятся чаты с другими агентами, маршрут недоступен. Рекомендация: параметр получателя (например, selected agent в ActivityBar/Sidebar), fallback `"opus"`.

## Замечания (можно улучшить)

- **`TerminalGrid` использует `key={idx}`.**
  `ui/src/components/TerminalGrid.tsx:58`. Буфер обрезается в `agentStore` (`slice(len - 100)`) — индексы сдвигаются, React будет реконсилить "не ту" строку. Визуально обычно незаметно, но возможны артефакты при быстром скролле. Альтернатива: уникальный monotonic id при записи в стор.

- **`TaskList` — `cursor-pointer` без onClick.**
  `ui/src/components/TaskList.tsx:32` даёт руку-указатель, хотя клик ничего не делает. Либо добавить handler, либо убрать cursor.

- **`LogFeed` всегда скроллит вниз, даже если пользователь отмотал вверх.**
  `ui/src/components/LogFeed.tsx:17-22`: `scrollTop = scrollHeight` на каждом изменении `entries`. Лучше проверять "был ли пользователь у низа" (`scrollHeight - scrollTop - clientHeight < threshold`) и только тогда скроллить.

- **`App.tsx:97` читает `logs` через `useLogs()` и тут же маппит в новый массив каждый рендер.**
  Приводит к новому массиву `logEntries` на любом изменении стора. `LogFeed` мемоизацию не применяет — перерисовывается всегда. Для 200 записей приемлемо, но `useMemo` был бы корректнее.

- **`main.tsx` — `document.getElementById("root") as HTMLElement`.**
  Безусловный type assertion. Если `#root` отсутствует, `createRoot` упадёт глубже с неинформативной ошибкой. Рекомендация: `const root = document.getElementById("root"); if (!root) throw new Error(...)`.

- **Unicode-иконки ActivityBar.**
  `ActivityBar.tsx:15-19`: `👥 ✓ 📋 ⚙`. Эмодзи рендерятся по-разному на Windows / macOS / Linux; могут быть цветными (у ✓ — нейтральный) или монохромными. В Tauri это fixed, но для единого вида проект рано или поздно перейдёт на икон-шрифт/svg. Пометить как технический долг.

- **`ConnectionStatus` "Connecting..." vs "Reconnecting..." — одинаковый цвет, разная лейбл.**
  `ConnectionStatus.tsx:19-28`. Норм, но "Connecting..." видится только на доли секунды перед первой ошибкой; после этого всегда "Reconnecting...". Можно упростить до одного лейбла или добавить retry-count (`Reconnecting (3)...`) — полезнее для отладки.

- **`useOrchestrator` возвращает `connected`, но в App используется только `status`.**
  `App.tsx:95` деструктурирует `{ status, sendMessage }`. `connected` — лишний публичный член. Упростить до одного поля.

- **`ChatInput` placeholder — "Опиши задачу для Opus".**
  Жёсткая привязка к Opus в плейсхолдере дублирует hardcoded `to: "opus"`. При изменении адресата нужно будет править обе точки.

- **`index.css` `@import url(...)` Google Fonts — сетевой запрос в offline / Tauri bundle.**
  Для Tauri-приложения желательно self-host шрифта или `display=swap` + локальный фолбэк уже описан. Минорно.

- **`SidebarContent` вызывает `useTasks()` даже для view `agents`/`logs`/`settings`.**
  `App.tsx:32`. Хук подписан на стор всегда; компонент перерисуется при любом изменении tasks, даже когда пользователь на другом экране. Пока INITIAL_TASKS мёртвые — неважно; когда задачи станут живыми — стоит переместить `useTasks()` внутрь `case "tasks"` (невозможно — хуки не в case). Решение: разделить на `TasksSidebar` / `AgentsSidebar` компоненты.

- **`agentStore.nextLogId` — module-level счётчик.**
  `agentStore.tsx:140-144`. При HMR и при наличии нескольких провайдеров в тестах счётчик разделяется, что даёт коллизии id. Для текущего single-tree провайдера нормально, для тестов — дырка. Рекомендация: переместить в состояние reducer или в ref провайдера.

- **Нет error boundary вокруг `<App/>`.**
  Ошибка в рендере любого компонента (например, неожиданный формат `terminal`-строки) свалит всё приложение. Добавить простой `ErrorBoundary` на уровне `main.tsx`.

- **`vite-env.d.ts` не прочитан — проверить наличие `import.meta.env` использований.**
  URL `ws://localhost:8765` захардкожен в `useOrchestrator.ts:49`. Для разных окружений стоит вынести в `import.meta.env.VITE_WS_URL` с fallback.

## Хорошо сделано

- **WS reconnect корректно реализован через ref-замыкание.** `useWebSocket.ts:49,134-136` — `connectRef` разрывает циклическую зависимость `connect ↔ scheduleReconnect`, timer-ref чистится, `shouldRunRef` защищает от реконнекта после unmount.
- **Cleanup сокета полный.** `useWebSocket.ts:141-153` — clear timer, close ws, reset status. Ни одной утечки не увидел.
- **Discriminated union для `Action`** (`agentStore.tsx:45-54`) + exhaustive `switch` без default — TS ловит забытый case.
- **Type-guard `isAgentStatus`** + `asString` (`useOrchestrator.ts:13-19`) — строгая валидация неизвестных фреймов, без `any`.
- **Буферы terminal/logs обрезаются через `slice`** (`agentStore.tsx:184-198`) — сохранён immutable-контракт reducer'а, ограниченная память.
- **`useMemo` на context value** (`agentStore.tsx:217`) — предотвращает лишние перерисовки подписчиков.
- **Селекторные хуки `useAgents`/`useLogs`/`useTasks`/`useDispatch`** — чистый public API, не утекают внутренности StoreContext.
- **tsconfig `strict + noUnusedLocals + noUnusedParameters + noFallthroughCasesInSwitch`** — строгий режим реально включён, `any`/`@ts-ignore` в коде не встречаются.
- **`SidebarContent` на exhaustive `switch` по `ActivityView`** — убирает silent fallback на settings, описанный в UI-4.
- **Контракт `register` как первого фрейма** (`useWebSocket.ts:89-97`) точно совпадает с требованием server.py (иначе close 1008).
- **`AgentStoreProvider` правильно обёрнут в `main.tsx`**, `useOrchestrator()` вызывается один раз внутри `<App/>` под провайдером.
- **Обработка snapshot’а устойчива** к разным форматам (`terminal: string`, `lines: string[]`, `content: string`) — щадящая совместимость с будущими версиями server.py.
- **Tauri конфиг с `minWidth: 900` / `minHeight: 650`** (`tauri.conf.json`) — предотвращает поломку layout на маленьких окнах.
