# Architecture Decision Log

Журнал архитектурных решений тимлида. Каждая запись: дата, контекст, решение, обоснование, последствия. Заполняется при каждом нетривиальном выборе — выбор библиотеки, изменение контракта между модулями, смена подхода к задаче.

---

## 2026-04-19 — Fix #1: UISettings persistence (localStorage)

**Что:** Новый хук `ui/src/hooks/useUISettings.ts` (load/save с per-field type-guards) + App.tsx подхватывает `loadUISettings()` в initial state и `saveUISettings(...)` в useEffect по `[state.uiSettings]`.

**Почему:** До фикса theme/font/density/accent/backdrop жили только в `useState` — любой refresh затирал их в TWEAK_DEFAULTS, что делает экран Preferences плацебо.

**Как проверил:** `cd ui && npm run build` — собрано без TS-ошибок (307 KB js). Store валидируется при загрузке (вручную проверил bad-json и unknown-enum не ломают — падает в дефолты).

**Scope:** только 5 визуальных полей. 11 «поведенческих» toggle-ов (анимации/auto-restart/TDD/…) оставлены без персиста — отдельный тикет.
