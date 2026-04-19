# Frontend Developer Memory

Память сжата: с ~16 KB (8 сессий подробных отчётов) до ~4 KB ключевых фактов. Сохранены стек, токены, архитектура компонентов/хуков/стора, WS-протокол, конвенции и backend-контракты. Устаревшие промежуточные состояния (UI-1..UI-4 ранние решения, которые были перекрыты) удалены.

## UI persistence (2026-04-19)
- `ui/src/hooks/useUISettings.ts` — LOCALSTORAGE_KEY `"groft:uiSettings"`, DEFAULT_UI_SETTINGS = {theme:"light", font:"inter", density:"spacious", accent:"default", backdrop:"froggly"}. `loadUISettings()` парсит + валидирует per-field type guards (isTheme/isFont/...), merge с дефолтами; невалидные поля дропаются. `saveUISettings()` swallowит QuotaExceededError.
- App.tsx: initial `uiSettings: loadUISettings()`; второй useEffect `saveUISettings(state.uiSettings)` с deps `[state.uiSettings]` сразу после CSS-var effect. `view`/`gridMode` остаются ephemeral (не персистятся).
- `npm run build` → tsc + vite build OK (307 kB JS, 28 kB CSS).

## Telegram REST flow (Phase 6.2, 2026-04-19, feature/phase6.2-tg-ui)
- `ui/src/hooks/useChannels.ts` — вся Telegram-логика через REST `http://localhost:8766/messenger/telegram/{configure,start-pairing,status}`. tmux send-keys дропнут.
  - `connect("telegram", {token})` → POST /configure, парсит `{ok, username, error}`. Валидация клиента: `trim().length >= 20 && !/\s/`. Статус остаётся `"connecting"`.
  - `startTelegramPairing(): Promise<string>` → POST /start-pairing, возвращает `code`, пишет в `pairingCode` state.
  - `pair(_code)` — polling loop 2s × 60 (2m timeout), читает `/status`, уходит из loop на `connected`/`error`.
  - `disconnect()` — local-only (backend reset не реализован, TODO).
  - `getTelegramStatus(): Promise<TelegramStatusSnapshot>` где `TelegramStatusSnapshot = {status, username, pairedUserId}` (camelCase mapping от `paired_user_id`).
- `UseChannelsResult` теперь также экспонит `pairedUserId`, `pairingCode`, `startTelegramPairing`.
- Удалены `TELEGRAM_TOKEN_RE`, `PAIR_CODE_RE`. `DISCORD_TOKEN_RE` сохранён (discord всё ещё через tmux).
- `ui/src/views/MessengerSettingsView.tsx` — `TelegramFlow` свернут с 4 шагов до 3 (Токен / Пара / Готово). Шаг Пара показывает большой code + copy button + инструкцию "найди @{username}, отправь /pair {code}", пуллит статус в фоне. Шаг Готово показывает `@{username}` + `id {pairedUserId}`.
- Build: tsc clean, vite build 321.69 kB JS (gzip 95.32) / 28.44 kB CSS.
