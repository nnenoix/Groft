# Design Handoff

Журнал handoff-пакетов из Claude Design, принятых ClaudeOrch.

Сюда Opus (тимлид) записывает результат анализа каждого входящего дизайн-пакета: список полученных файлов (HTML/CSS/компоненты/дизайн-система/экраны/интерактивность), план реализации по компонентам, определённый порядок работы (что делать первым, что параллельно), зависимости между компонентами и текущий статус реализации (в работе/готово/заблокировано).

Формат записи на каждый handoff:

## {ISO-дата} — {название дизайна}
- **Источник:** путь к входящему пакету
- **Файлы:** список полученных артефактов
- **Дизайн-система:** ключевые токены (цвета, типографика, сетка)
- **Компоненты:** список с кратким описанием
- **Экраны/страницы:** структура и связи
- **План реализации:** упорядоченный список задач (номера HEALTH-N / UI-N и т.п.)
- **Исполнители:** кто берёт какую задачу (frontend-dev / backend-dev)
- **Статус:** в работе / готово / заблокировано

Пустой пока — handoff-ов ещё не было.

## 2026-04-18T16:28:32+00:00 — handoff detected at `ork-handoff`

- **Источник:** `ork-handoff`
- **Файлов обнаружено:** 175
- **Инвентарь:**
  - `ork-handoff/ork/README.md` (1586 B)
  - `ork-handoff/ork/project/ClaudeOrch Redesign (standalone).html` (2266868 B)
  - `ork-handoff/ork/project/ClaudeOrch Redesign.html` (15727 B)
  - `ork-handoff/ork/project/scraps/sketch-2026-04-18T10-53-42-o0mwiv.napkin` (118 B)
  - `ork-handoff/ork/project/screenshots/01-atelier-v2.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/01-atelier-v3.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-atelier.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/01-check-settings.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-cmdk.png` (28633 B)
  - `ork-handoff/ork/project/screenshots/01-cmdk2.png` (16850 B)
  - `ork-handoff/ork/project/screenshots/01-dark-test.png` (3718 B)
  - `ork-handoff/ork/project/screenshots/01-dark2.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dark3.png` (28664 B)
  - `ork-handoff/ork/project/screenshots/01-dbg.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg10.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg11.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg12.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg13.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg14.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg15.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg16.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-dbg18.png` (28686 B)
  - `ork-handoff/ork/project/screenshots/01-dbg2.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/01-dbg4.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg5.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg6.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg7.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg8.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-dbg9.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-drawer-final.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-drawer-fix.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-drawer.png` (30392 B)
  - `ork-handoff/ork/project/screenshots/01-drawer5.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-kbd.png` (14007 B)
  - `ork-handoff/ork/project/screenshots/01-rev-command.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-rev-layouts.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/01-rev-studio.png` (7404 B)
  - `ork-handoff/ork/project/screenshots/01-settings-agents.jpg` (14911 B)
  - `ork-handoff/ork/project/screenshots/01-settings-fix.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/01-settings-fix2.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-settings-fix3.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/01-settings-roles.jpg` (26316 B)
  - `ork-handoff/ork/project/screenshots/01-studio-v2.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/02-atelier-v2.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/02-atelier-v3.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/02-atelier.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/02-check-settings.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-cmdk.png` (16850 B)
  - `ork-handoff/ork/project/screenshots/02-cmdk2.png` (13573 B)
  - `ork-handoff/ork/project/screenshots/02-dark-test.png` (3717 B)
  - `ork-handoff/ork/project/screenshots/02-dark2.png` (31571 B)
  - `ork-handoff/ork/project/screenshots/02-dark3.png` (21256 B)
  - `ork-handoff/ork/project/screenshots/02-dbg.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg10.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg11.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg12.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg13.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg14.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg15.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg16.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg18.png` (28686 B)
  - `ork-handoff/ork/project/screenshots/02-dbg2.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-dbg4.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg5.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg6.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg7.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg8.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-dbg9.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-drawer-final.png` (30392 B)
  - `ork-handoff/ork/project/screenshots/02-drawer-fix.png` (30392 B)
  - `ork-handoff/ork/project/screenshots/02-drawer.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/02-drawer5.png` (30392 B)
  - `ork-handoff/ork/project/screenshots/02-kbd.png` (14357 B)
  - `ork-handoff/ork/project/screenshots/02-rev-command.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/02-rev-layouts.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/02-rev-studio.png` (7404 B)
  - `ork-handoff/ork/project/screenshots/02-settings-agents.jpg` (15012 B)
  - `ork-handoff/ork/project/screenshots/02-settings-fix.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/02-settings-fix2.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-settings-fix3.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/02-settings-roles.jpg` (26308 B)
  - `ork-handoff/ork/project/screenshots/02-studio-v2.png` (22140 B)
  - `ork-handoff/ork/project/screenshots/03-atelier-v3.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/03-atelier.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/03-cmdk.png` (16850 B)
  - `ork-handoff/ork/project/screenshots/03-dark-test.png` (3717 B)
  - `ork-handoff/ork/project/screenshots/03-dark2.png` (30243 B)
  - `ork-handoff/ork/project/screenshots/03-dark3.png` (25338 B)
  - `ork-handoff/ork/project/screenshots/03-dbg.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg10.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg11.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg12.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg13.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg14.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/03-dbg15.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/03-dbg16.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/03-dbg2.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg4.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg5.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg6.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg7.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg8.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-dbg9.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-drawer-final.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/03-drawer-fix.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/03-drawer5.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/03-kbd.png` (13701 B)
  - `ork-handoff/ork/project/screenshots/03-rev-command.png` (30392 B)
  - `ork-handoff/ork/project/screenshots/03-rev-layouts.png` (7297 B)
  - `ork-handoff/ork/project/screenshots/03-rev-studio.png` (7297 B)
  - `ork-handoff/ork/project/screenshots/03-settings-fix2.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/03-settings-fix3.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/03-studio-v2.png` (18367 B)
  - `ork-handoff/ork/project/screenshots/04-atelier-v3.png` (29003 B)
  - `ork-handoff/ork/project/screenshots/04-dark-test.png` (3717 B)
  - `ork-handoff/ork/project/screenshots/04-dbg10.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-dbg11.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-dbg12.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-dbg13.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-dbg14.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/04-dbg15.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/04-dbg16.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/04-dbg2.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-dbg9.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/04-rev-command.png` (27943 B)
  - `ork-handoff/ork/project/screenshots/04-studio-v2.png` (18367 B)
  - `ork-handoff/ork/project/screenshots/05-dark-test.png` (3717 B)
  - `ork-handoff/ork/project/screenshots/05-dbg16.png` (24115 B)
  - `ork-handoff/ork/project/screenshots/05-rev-command.png` (22140 B)
  - `ork-handoff/ork/project/screenshots/06-dark-test.png` (3717 B)
  - `ork-handoff/ork/project/screenshots/after1-8.png` (28575 B)
  - `ork-handoff/ork/project/screenshots/agents.png` (22863 B)
  - `ork-handoff/ork/project/screenshots/audit.png` (21591 B)
  - `ork-handoff/ork/project/screenshots/audit2.png` (27564 B)
  - `ork-handoff/ork/project/screenshots/backdrop.png` (28483 B)
  - `ork-handoff/ork/project/screenshots/backdrop2.png` (28686 B)
  - `ork-handoff/ork/project/screenshots/backdrop3.png` (28353 B)
  - `ork-handoff/ork/project/screenshots/backdrop4.png` (28897 B)
  - `ork-handoff/ork/project/screenshots/composer-modal.jpg` (15152 B)
  - `ork-handoff/ork/project/screenshots/composer.png` (21545 B)
  - `ork-handoff/ork/project/screenshots/composer2.png` (21493 B)
  - `ork-handoff/ork/project/screenshots/current.png` (21545 B)
  - `ork-handoff/ork/project/screenshots/dbg17.png` (28686 B)
  - `ork-handoff/ork/project/screenshots/dbg19.png` (28686 B)
  - `ork-handoff/ork/project/screenshots/diagnose.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/dom-inspect.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/drawer-check.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/drawer-check2.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/drawer-dom.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/drawer-hq.png` (36473 B)
  - `ork-handoff/ork/project/screenshots/drawer-verify.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/drawer-wait.png` (21601 B)
  - `ork-handoff/ork/project/screenshots/drawer2.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/drawer3.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/drawer4.png` (8833 B)
  - `ork-handoff/ork/project/screenshots/final-command.jpg` (30486 B)
  - `ork-handoff/ork/project/screenshots/froggly.png` (28428 B)
  - `ork-handoff/ork/project/screenshots/grid.png` (19658 B)
  - `ork-handoff/ork/project/screenshots/pulse.png` (20594 B)
  - `ork-handoff/ork/project/screenshots/pulse2.png` (21591 B)
  - `ork-handoff/ork/project/screenshots/settings-agents.png` (22984 B)
  - `ork-handoff/ork/project/screenshots/settings-agents2.png` (24068 B)
  - `ork-handoff/ork/project/screenshots/settings.png` (22903 B)
  - `ork-handoff/ork/project/screenshots/studio-term.png` (22485 B)
  - `ork-handoff/ork/project/screenshots/studio.png` (29003 B)
  - `ork-handoff/ork/project/src/app.jsx` (2525 B)
  - `ork-handoff/ork/project/src/cmdk.jsx` (8321 B)
  - `ork-handoff/ork/project/src/data.jsx` (10923 B)
  - `ork-handoff/ork/project/src/icons.jsx` (6964 B)
  - `ork-handoff/ork/project/src/layouts.jsx` (12308 B)
  - `ork-handoff/ork/project/src/primitives.jsx` (22399 B)
  - `ork-handoff/ork/project/src/terminal.jsx` (4940 B)
  - `ork-handoff/ork/project/src/views.jsx` (58478 B)
  - `ork-handoff/ork/project/uploads/pasted-1776512802740-0.png` (17815 B)
  - `ork-handoff/ork/project/uploads/pasted-1776515559020-0.png` (1799676 B)
- **Статус:** обнаружен, не проанализирован — Opus должен прочитать файлы и заполнить план.
<!-- handoff-fingerprint:
ork-handoff/ork/README.md
ork-handoff/ork/project/ClaudeOrch Redesign (standalone).html
ork-handoff/ork/project/ClaudeOrch Redesign.html
ork-handoff/ork/project/scraps/sketch-2026-04-18T10-53-42-o0mwiv.napkin
ork-handoff/ork/project/screenshots/01-atelier-v2.png
ork-handoff/ork/project/screenshots/01-atelier-v3.png
ork-handoff/ork/project/screenshots/01-atelier.png
ork-handoff/ork/project/screenshots/01-check-settings.png
ork-handoff/ork/project/screenshots/01-cmdk.png
ork-handoff/ork/project/screenshots/01-cmdk2.png
ork-handoff/ork/project/screenshots/01-dark-test.png
ork-handoff/ork/project/screenshots/01-dark2.png
ork-handoff/ork/project/screenshots/01-dark3.png
ork-handoff/ork/project/screenshots/01-dbg.png
ork-handoff/ork/project/screenshots/01-dbg10.png
ork-handoff/ork/project/screenshots/01-dbg11.png
ork-handoff/ork/project/screenshots/01-dbg12.png
ork-handoff/ork/project/screenshots/01-dbg13.png
ork-handoff/ork/project/screenshots/01-dbg14.png
ork-handoff/ork/project/screenshots/01-dbg15.png
ork-handoff/ork/project/screenshots/01-dbg16.png
ork-handoff/ork/project/screenshots/01-dbg18.png
ork-handoff/ork/project/screenshots/01-dbg2.png
ork-handoff/ork/project/screenshots/01-dbg4.png
ork-handoff/ork/project/screenshots/01-dbg5.png
ork-handoff/ork/project/screenshots/01-dbg6.png
ork-handoff/ork/project/screenshots/01-dbg7.png
ork-handoff/ork/project/screenshots/01-dbg8.png
ork-handoff/ork/project/screenshots/01-dbg9.png
ork-handoff/ork/project/screenshots/01-drawer-final.png
ork-handoff/ork/project/screenshots/01-drawer-fix.png
ork-handoff/ork/project/screenshots/01-drawer.png
ork-handoff/ork/project/screenshots/01-drawer5.png
ork-handoff/ork/project/screenshots/01-kbd.png
ork-handoff/ork/project/screenshots/01-rev-command.png
ork-handoff/ork/project/screenshots/01-rev-layouts.png
ork-handoff/ork/project/screenshots/01-rev-studio.png
ork-handoff/ork/project/screenshots/01-settings-agents.jpg
ork-handoff/ork/project/screenshots/01-settings-fix.png
ork-handoff/ork/project/screenshots/01-settings-fix2.png
ork-handoff/ork/project/screenshots/01-settings-fix3.png
ork-handoff/ork/project/screenshots/01-settings-roles.jpg
ork-handoff/ork/project/screenshots/01-studio-v2.png
ork-handoff/ork/project/screenshots/02-atelier-v2.png
ork-handoff/ork/project/screenshots/02-atelier-v3.png
ork-handoff/ork/project/screenshots/02-atelier.png
ork-handoff/ork/project/screenshots/02-check-settings.png
ork-handoff/ork/project/screenshots/02-cmdk.png
ork-handoff/ork/project/screenshots/02-cmdk2.png
ork-handoff/ork/project/screenshots/02-dark-test.png
ork-handoff/ork/project/screenshots/02-dark2.png
ork-handoff/ork/project/screenshots/02-dark3.png
ork-handoff/ork/project/screenshots/02-dbg.png
ork-handoff/ork/project/screenshots/02-dbg10.png
ork-handoff/ork/project/screenshots/02-dbg11.png
ork-handoff/ork/project/screenshots/02-dbg12.png
ork-handoff/ork/project/screenshots/02-dbg13.png
ork-handoff/ork/project/screenshots/02-dbg14.png
ork-handoff/ork/project/screenshots/02-dbg15.png
ork-handoff/ork/project/screenshots/02-dbg16.png
ork-handoff/ork/project/screenshots/02-dbg18.png
ork-handoff/ork/project/screenshots/02-dbg2.png
ork-handoff/ork/project/screenshots/02-dbg4.png
ork-handoff/ork/project/screenshots/02-dbg5.png
ork-handoff/ork/project/screenshots/02-dbg6.png
ork-handoff/ork/project/screenshots/02-dbg7.png
ork-handoff/ork/project/screenshots/02-dbg8.png
ork-handoff/ork/project/screenshots/02-dbg9.png
ork-handoff/ork/project/screenshots/02-drawer-final.png
ork-handoff/ork/project/screenshots/02-drawer-fix.png
ork-handoff/ork/project/screenshots/02-drawer.png
ork-handoff/ork/project/screenshots/02-drawer5.png
ork-handoff/ork/project/screenshots/02-kbd.png
ork-handoff/ork/project/screenshots/02-rev-command.png
ork-handoff/ork/project/screenshots/02-rev-layouts.png
ork-handoff/ork/project/screenshots/02-rev-studio.png
ork-handoff/ork/project/screenshots/02-settings-agents.jpg
ork-handoff/ork/project/screenshots/02-settings-fix.png
ork-handoff/ork/project/screenshots/02-settings-fix2.png
ork-handoff/ork/project/screenshots/02-settings-fix3.png
ork-handoff/ork/project/screenshots/02-settings-roles.jpg
ork-handoff/ork/project/screenshots/02-studio-v2.png
ork-handoff/ork/project/screenshots/03-atelier-v3.png
ork-handoff/ork/project/screenshots/03-atelier.png
ork-handoff/ork/project/screenshots/03-cmdk.png
ork-handoff/ork/project/screenshots/03-dark-test.png
ork-handoff/ork/project/screenshots/03-dark2.png
ork-handoff/ork/project/screenshots/03-dark3.png
ork-handoff/ork/project/screenshots/03-dbg.png
ork-handoff/ork/project/screenshots/03-dbg10.png
ork-handoff/ork/project/screenshots/03-dbg11.png
ork-handoff/ork/project/screenshots/03-dbg12.png
ork-handoff/ork/project/screenshots/03-dbg13.png
ork-handoff/ork/project/screenshots/03-dbg14.png
ork-handoff/ork/project/screenshots/03-dbg15.png
ork-handoff/ork/project/screenshots/03-dbg16.png
ork-handoff/ork/project/screenshots/03-dbg2.png
ork-handoff/ork/project/screenshots/03-dbg4.png
ork-handoff/ork/project/screenshots/03-dbg5.png
ork-handoff/ork/project/screenshots/03-dbg6.png
ork-handoff/ork/project/screenshots/03-dbg7.png
ork-handoff/ork/project/screenshots/03-dbg8.png
ork-handoff/ork/project/screenshots/03-dbg9.png
ork-handoff/ork/project/screenshots/03-drawer-final.png
ork-handoff/ork/project/screenshots/03-drawer-fix.png
ork-handoff/ork/project/screenshots/03-drawer5.png
ork-handoff/ork/project/screenshots/03-kbd.png
ork-handoff/ork/project/screenshots/03-rev-command.png
ork-handoff/ork/project/screenshots/03-rev-layouts.png
ork-handoff/ork/project/screenshots/03-rev-studio.png
ork-handoff/ork/project/screenshots/03-settings-fix2.png
ork-handoff/ork/project/screenshots/03-settings-fix3.png
ork-handoff/ork/project/screenshots/03-studio-v2.png
ork-handoff/ork/project/screenshots/04-atelier-v3.png
ork-handoff/ork/project/screenshots/04-dark-test.png
ork-handoff/ork/project/screenshots/04-dbg10.png
ork-handoff/ork/project/screenshots/04-dbg11.png
ork-handoff/ork/project/screenshots/04-dbg12.png
ork-handoff/ork/project/screenshots/04-dbg13.png
ork-handoff/ork/project/screenshots/04-dbg14.png
ork-handoff/ork/project/screenshots/04-dbg15.png
ork-handoff/ork/project/screenshots/04-dbg16.png
ork-handoff/ork/project/screenshots/04-dbg2.png
ork-handoff/ork/project/screenshots/04-dbg9.png
ork-handoff/ork/project/screenshots/04-rev-command.png
ork-handoff/ork/project/screenshots/04-studio-v2.png
ork-handoff/ork/project/screenshots/05-dark-test.png
ork-handoff/ork/project/screenshots/05-dbg16.png
ork-handoff/ork/project/screenshots/05-rev-command.png
ork-handoff/ork/project/screenshots/06-dark-test.png
ork-handoff/ork/project/screenshots/after1-8.png
ork-handoff/ork/project/screenshots/agents.png
ork-handoff/ork/project/screenshots/audit.png
ork-handoff/ork/project/screenshots/audit2.png
ork-handoff/ork/project/screenshots/backdrop.png
ork-handoff/ork/project/screenshots/backdrop2.png
ork-handoff/ork/project/screenshots/backdrop3.png
ork-handoff/ork/project/screenshots/backdrop4.png
ork-handoff/ork/project/screenshots/composer-modal.jpg
ork-handoff/ork/project/screenshots/composer.png
ork-handoff/ork/project/screenshots/composer2.png
ork-handoff/ork/project/screenshots/current.png
ork-handoff/ork/project/screenshots/dbg17.png
ork-handoff/ork/project/screenshots/dbg19.png
ork-handoff/ork/project/screenshots/diagnose.png
ork-handoff/ork/project/screenshots/dom-inspect.png
ork-handoff/ork/project/screenshots/drawer-check.png
ork-handoff/ork/project/screenshots/drawer-check2.png
ork-handoff/ork/project/screenshots/drawer-dom.png
ork-handoff/ork/project/screenshots/drawer-hq.png
ork-handoff/ork/project/screenshots/drawer-verify.png
ork-handoff/ork/project/screenshots/drawer-wait.png
ork-handoff/ork/project/screenshots/drawer2.png
ork-handoff/ork/project/screenshots/drawer3.png
ork-handoff/ork/project/screenshots/drawer4.png
ork-handoff/ork/project/screenshots/final-command.jpg
ork-handoff/ork/project/screenshots/froggly.png
ork-handoff/ork/project/screenshots/grid.png
ork-handoff/ork/project/screenshots/pulse.png
ork-handoff/ork/project/screenshots/pulse2.png
ork-handoff/ork/project/screenshots/settings-agents.png
ork-handoff/ork/project/screenshots/settings-agents2.png
ork-handoff/ork/project/screenshots/settings.png
ork-handoff/ork/project/screenshots/studio-term.png
ork-handoff/ork/project/screenshots/studio.png
ork-handoff/ork/project/src/app.jsx
ork-handoff/ork/project/src/cmdk.jsx
ork-handoff/ork/project/src/data.jsx
ork-handoff/ork/project/src/icons.jsx
ork-handoff/ork/project/src/layouts.jsx
ork-handoff/ork/project/src/primitives.jsx
ork-handoff/ork/project/src/terminal.jsx
ork-handoff/ork/project/src/views.jsx
ork-handoff/ork/project/uploads/pasted-1776512802740-0.png
ork-handoff/ork/project/uploads/pasted-1776515559020-0.png
-->
