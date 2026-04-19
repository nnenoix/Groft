# Current Task Specification

## RELEASE-1 — WiX MSI bundle + GitHub Actions release (PR D of 4)

**Цель:** При пуше тега `v*` автоматически собрать `Groft_<version>_x64_en-US.msi` (WiX) и `Groft_<version>_x64-setup.exe` (NSIS) на Windows runner'е GitHub Actions и приложить к GitHub Release. После этого пользователь скачивает один файл, ставит, запускает иконку "Groft" из меню "Пуск" — всё работает (при условии что `claude` CLI в PATH).

**Ветка:** `feature/wix-release-ci` (от master, уже checked out, push сделан).

### Что сделать

1. **`.github/workflows/release.yml`** — новый workflow:
   ```yaml
   name: release
   on:
     push:
       tags: ["v*"]
     workflow_dispatch:
   permissions:
     contents: write  # нужно для softprops/action-gh-release
   jobs:
     build-windows:
       runs-on: windows-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - uses: actions/setup-node@v4
           with:
             node-version: "20"
             cache: npm
             cache-dependency-path: ui/package-lock.json
         - uses: dtolnay/rust-toolchain@stable
         - name: Install Python deps
           run: pip install -r requirements-dev.txt
         - name: Build orchestrator (PyInstaller)
           run: python packaging/build_windows.py --smoke
         - name: Install npm deps
           working-directory: ui
           run: npm ci
         - name: Build Tauri MSI + NSIS
           working-directory: ui
           run: npx tauri build --bundles msi nsis
         - name: Upload MSI artifact
           uses: actions/upload-artifact@v4
           with:
             name: groft-msi
             path: ui/src-tauri/target/release/bundle/msi/*.msi
         - name: Upload NSIS artifact
           uses: actions/upload-artifact@v4
           with:
             name: groft-nsis
             path: ui/src-tauri/target/release/bundle/nsis/*.exe
         - name: Attach to GitHub Release
           if: startsWith(github.ref, 'refs/tags/v')
           uses: softprops/action-gh-release@v2
           with:
             files: |
               ui/src-tauri/target/release/bundle/msi/*.msi
               ui/src-tauri/target/release/bundle/nsis/*.exe
             generate_release_notes: true
   ```
   - НЕ добавляй signing steps — сертификата ещё нет.
   - НЕ добавляй matrix для macOS/Linux — это отдельный PR.

2. **`ui/src-tauri/tauri.conf.json`** — расширить `bundle`:
   - Добавить `bundle.windows.wix.language = "en-US"`.
   - Добавить `bundle.windows.wix.upgradeCode = "3be766d6-a9e9-4d6d-a623-6139519fdaa2"`. Этот GUID уже сгенерирован — используй точно его, не генерируй свой.
   - Также добавь `bundle.windows.wix.template = null` (явный дефолт) — не обязательно, но читаемо.
   - Не ломай существующие `bundle.active`, `bundle.targets`, `bundle.icon`, `bundle.resources`.
   - Проверь `python3 -c "import json; json.load(open('ui/src-tauri/tauri.conf.json'))"` после правок.

3. **`packaging/README.md`** — добавить секцию после существующего build-howto:
   ```markdown
   ## Install from release

   1. Download `Groft_<version>_x64_en-US.msi` (или NSIS .exe) from [GitHub Releases](https://github.com/nnenoix/Groft/releases).
   2. Double-click the file. Windows SmartScreen может показать warning (приложение не подписано) — More info → Run anyway.
   3. Launch "Groft" from Start menu.
   4. On first launch, the app seeds `%APPDATA%\com.groft.app\` with default config + agent definitions, then spawns the bundled orchestrator sidecar.

   **Prerequisites:** Claude CLI (`claude`) must be on PATH. Install from https://docs.anthropic.com/en/docs/claude-code/.

   ## Uninstall

   Windows → Settings → Apps → Groft → Uninstall. User data in `%APPDATA%\com.groft.app\` не удаляется автоматически (делайте руками если нужно).
   ```

4. **README.md в корне репо** — минимальный (≤30 строк), ссылка на `packaging/README.md`:
   ```markdown
   # Groft

   Claude-Code agent orchestration — Windows desktop app.

   ## Install

   Download the latest MSI from [Releases](https://github.com/nnenoix/Groft/releases) and run it.

   See [packaging/README.md](packaging/README.md) for build/install details.

   ## Development

   ```bash
   python -m venv .venv && source .venv/bin/activate  # Linux/macOS
   # .venv\Scripts\activate                           # Windows
   pip install -r requirements-dev.txt
   pytest -v
   ```

   See [CLAUDE.md](CLAUDE.md) for architecture.
   ```

5. **`.gitignore`** — если ещё нет: `ui/src-tauri/target/` и `ui/dist/`. Проверь.

### Acceptance criteria

1. `python3 -m pytest tests/ -q` → 13 passed, 4 skipped (никакой регрессии).
2. `python3 -c "import json, sys; d=json.load(open('ui/src-tauri/tauri.conf.json')); assert d['bundle']['windows']['wix']['upgradeCode'] == '3be766d6-a9e9-4d6d-a623-6139519fdaa2'; print('ok')"` → `ok`.
3. `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` → no exception.
4. Визуальная проверка workflow: нет typo в action names (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `dtolnay/rust-toolchain@stable`, `actions/upload-artifact@v4`, `softprops/action-gh-release@v2`). Все версии стабильные, без `@main`.
5. `grep -n "upgradeCode" ui/src-tauri/tauri.conf.json` — одно вхождение, точно этот GUID.

### Один коммит
`feat: WiX MSI + GitHub Actions release workflow (PR D/4)`. Push на `origin/feature/wix-release-ci`.

### Out of scope
- Code signing (cert отсутствует).
- Auto-updater.
- macOS/Linux bundles (отдельный PR).
- Триггер реального CI — сделаем первый релиз вручную после merge'а.

### Важно
- GitHub Actions YAML синтаксис строгий — проверь `yaml.safe_load` локально.
- JSON в `tauri.conf.json` с комментариями НЕ работает — не добавляй `//` (я привёл фрагмент с комментом для понимания, но в файле — только чистый JSON).
- upgradeCode GUID зафиксирован — если сгенерируешь свой, обновления будут ломать установку.
- Не коммить `ui/src-tauri/target/`, `ui/dist/`, `ui/node_modules/` — они должны быть в `.gitignore`.
