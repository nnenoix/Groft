# Frontend Developer Memory

Память сжата: с ~16 KB (8 сессий подробных отчётов) до ~4 KB ключевых фактов. Сохранены стек, токены, архитектура компонентов/хуков/стора, WS-протокол, конвенции и backend-контракты. Устаревшие промежуточные состояния (UI-1..UI-4 ранние решения, которые были перекрыты) удалены.

## UI persistence (2026-04-19)
- `ui/src/hooks/useUISettings.ts` — LOCALSTORAGE_KEY `"groft:uiSettings"`, DEFAULT_UI_SETTINGS = {theme:"light", font:"inter", density:"spacious", accent:"default", backdrop:"froggly"}. `loadUISettings()` парсит + валидирует per-field type guards (isTheme/isFont/...), merge с дефолтами; невалидные поля дропаются. `saveUISettings()` swallowит QuotaExceededError.
- App.tsx: initial `uiSettings: loadUISettings()`; второй useEffect `saveUISettings(state.uiSettings)` с deps `[state.uiSettings]` сразу после CSS-var effect. `view`/`gridMode` остаются ephemeral (не персистятся).
- `npm run build` → tsc + vite build OK (307 kB JS, 28 kB CSS).
