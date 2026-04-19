# Frontend Audit — Composer / CommandPalette / Hooks

_Дата: 2026-04-19. Файлы: primitives/Composer.tsx, Composer.tsx, ComposerDock.tsx, ComposerModal.tsx, CommandCenterLayout.tsx, useOrchestrator.ts, OrchestratorProvider.tsx_

---

## Gap-список

### GAP-1 · Кнопка «Прикрепить» (compact) — нет onClick
**primitives/Composer.tsx:163**
```tsx
<button className="btn btn-ghost !px-1.5 !py-1" title="Прикрепить"><Icon.Plus size={11} /></button>
```
Кнопка кликабельна, но ничего не делает.

---

### GAP-2 · Кнопка «Прикрепить» (full) — фейковый file picker
**primitives/Composer.tsx:255**
```tsx
onClick={() => setFiles([...files, `file_${files.length + 1}.py`])}
```
Вместо `<input type="file">` или Tauri `open()` — генерирует `file_1.py`, `file_2.py`.

---

### GAP-3 · `files` не попадает в onSubmit
**primitives/Composer.tsx:73**
```ts
onSubmit?.({ text, mode, model });   // ← files потеряны
```
Список файлов отображается в UI, но в WS-сообщение не уходит.

---

### GAP-4 · Кнопка «Голосом» — нет onClick
**primitives/Composer.tsx:258**
```tsx
<button className="btn btn-ghost !px-2 !py-1 text-[11px]" title="Голосом">
  <Icon.Waveform size={12} />
</button>
```
Нет обработчика.

---

### GAP-5 · Режим «review» дропается в isMode
**useOrchestrator.ts:56**
```ts
function isMode(v: unknown): v is "solo" | "team" {
  return v === "solo" || v === "team";
}
```
`COMPOSER_MODES` содержит `"review"`, Composer шлёт его в WS, но при получении статуса обратно — `mode: "review"` отбрасывается валидатором. Тип не добавлен.

---

### GAP-6 · openCmdK — необязательный пропс, кнопка молчит
**CommandCenterLayout.tsx:58,108**
```ts
openCmdK?: () => void
// ...
<button onClick={openCmdK}>Поиск и команды ⌘K</button>
```
Если вызывающий код не передаёт `openCmdK` — кнопка не работает без какого-либо предупреждения. CommandPalette-компонента нет совсем.

---

### GAP-7 · ComposerModal хардкодит модель в заголовке
**ComposerModal.tsx:47**
```tsx
<div>Оркестратор команды · claude-opus-4-7</div>
```
Строка не берётся из `MODEL_OPTIONS` или `DEFAULT_MODEL` — при смене модели расходится с реальным выбором.

---

## Что НЕ является заглушкой

- **Slash-команды** (`/plan /ship /review /test /fix`) — `applySlash` вставляет команду в textarea, текст уходит Opus как сообщение. Opus интерпретирует префикс. Это архитектурное решение, не stub.
- **mode/model в onSubmit** — передаются в WS-фрейм корректно (`Composer.tsx:16`). Влияние на сторону Opus — за пределами UI.
- **ComposerDock, ComposerModal (логика)** — чистые, заглушек нет.
- **useOrchestrator** — парсинг фреймов полный, без пустых веток.

---

## Вердикт

**4 нефункциональных элемента UI** (GAP-1..4) плюс **3 логических дыры** (GAP-5..7).  
Критичен GAP-3: файлы видны пользователю, но в протокол не уходят — молчаливая потеря данных.  
GAP-5 создаст трудноотлаживаемое расхождение при добавлении review-режима на бэке.  
GAP-6 блокирует весь CmdK-флоу.
