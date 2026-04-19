# UI Audit — Messengers & Terminals

Date: 2026-04-19

## Messengers

**Wizard шагов без бэкенда**
Step 2 (`setStep(3)`) — кнопка «Далее» меняет шаг без вызова бэкенда и без ожидания подтверждения, что бот получил `/start`. Это ок по дизайну (инструкция пользователю), но нет способа вернуться к Step 1 после Step 2 → если токен невалиден на сервере, ошибка придёт только на Step 3 и выше.

**«Connect» без handler**
`useChannels.configureTelegram` → `invoke("run_tmux_command", { command: "/telegram:configure …" })`. Возврат команды — строка из tmux, не структурированный ответ. Если tmux-сессия не запущена, `invoke` бросит, `setStatus("error")` выставится, но `errorMessage` будет сырой tmux-ошибкой. Нет проверки успешности выполнения команды — статус переходит в `"connecting"` до прихода реального WS-события.

**Mock QR**
QR-кода нет нигде — Step 2 просит написать боту `/start` вручную, это ожидаемо по текущей архитектуре.

**Disabled-сохранение**
Кнопки `disabled` через атрибут `disabled` + `opacity:0.5` + `cursor:not-allowed` — корректно. Проблем нет.

**Прочее**
- Discord / iMessage / Webhook — `StubPanel`, нет wizard'а, только текст.
- `username` после подключения всегда `null` (см. комментарий в useChannels:138).
- `useEffect` на Step-advance (строки 162–166): зависимость от `status` корректна только если `configureTelegram` всегда завершается до следующего рендера; при быстром двойном клике `submitting` успевает сброситься до прихода нового статуса → step может дважды инкрементироваться.

---

## Terminals

**Ввод в терминал**
`TerminalBlock` — read-only, нет `<input>`, нет `invoke`, нет `send_message`. Ввод невозможен из UI. Composer (ComposerModal/ComposerDock) шлёт сообщение оркестратору, не в tmux-pane.

**Snapshot path**
`useOrchestrator` case `"snapshot"` → `dispatch SET_TERMINAL` → replaces `terminalOutput` (last 100 lines, agentStore:93). `TerminalBlock` рендерит `lines={a.terminalOutput}`. Путь данных рабочий.

**Grid mode**
`gridMode ∈ {1,2,4,"all"}`. `visibleAgents` срезается через `slice(0, gridMode)` с активным агентом первым — корректно. `gridClass` в "all" не задаёт `grid-rows-*` → при нечётном числе агентов последняя строка неполная, но высота ячеек не ломается (flex-1/min-h-0 держат). Работает.

**Focus**
`openTerminal(name)` в CommandCenterLayout устанавливает `view:"terminals"` + `focusAgent:name`. Клик по агенту в сайдбаре, будучи на Terminals, обновляет только `focusAgent`. Tab-strip и meta-strip реагируют. Работает.

**Scroll**
`autoscroll` + `onScroll` в TerminalBlock — threshold 6px, что может фликтовать на Windows (scrollbar ~15px). При `SET_TERMINAL` (`useEffect([lines])`) скролл в конец срабатывает только если `autoscroll===true`. Работает, но порог стоит поднять до 16px.

**Нерабочие кнопки**
- Copy, Clear в TerminalBlock: `onClick` только `e.stopPropagation()`, тела нет.
- Stop, Restart в meta-strip: нет `onClick` вообще.
- Pause All в header: нет `onClick` вообще.
