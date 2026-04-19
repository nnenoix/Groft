# Packaging — Groft Orchestrator Bundle

PyInstaller onedir build of the Python orchestrator. Produces a standalone
binary that runs without a system Python install.

## Build

```
pip install -r requirements-dev.txt
python packaging/build_windows.py --smoke
```

`--smoke` runs the freshly built binary with `--smoke` (early-exit, logs
"smoke ok", exit code 0) to verify imports/native deps load. Drop the flag
for a plain build.

Optional: `--distpath PATH` to redirect output (default `./dist`).

## Output

- Linux:   `dist/orchestrator/orchestrator`
- Windows: `dist/orchestrator/orchestrator.exe`

The bundle is **onedir**: the exe sits next to its DLLs, Python runtime, and
data files (`config.yml`, `.claude/agents/`). Move the whole `orchestrator/`
folder, not just the exe.

## Run

```
./dist/orchestrator/orchestrator        # full run
./dist/orchestrator/orchestrator --smoke  # boot-check
```

Writable runtime state (`.claudeorch/`, `memory/`) lands in CWD by default;
override via `CLAUDEORCH_USER_DATA=<path>`.

## Install from release

1. Download `Groft_<version>_x64_en-US.msi` (или NSIS `.exe`) from
   [GitHub Releases](https://github.com/nnenoix/Groft/releases).
2. Double-click the file. Windows SmartScreen может показать warning
   (приложение не подписано) — More info → Run anyway.
3. Launch "Groft" from the Start menu.
4. On first launch, the app seeds `%APPDATA%\com.groft.app\` with default
   config + agent definitions, then spawns the bundled orchestrator sidecar.

**Prerequisites:** Claude CLI (`claude`) must be on PATH. Install from
https://docs.anthropic.com/en/docs/claude-code/.

## Uninstall

Windows → Settings → Apps → Groft → Uninstall. User data in
`%APPDATA%\com.groft.app\` не удаляется автоматически (сотрите руками
если нужно полностью чистое состояние).

## Notes

- Windows hosts need the Visual C++ Redistributable (usually pre-installed).
- `start.ps1` / `stop.ps1` keep working for dev mode with system Python.
- MSI `upgradeCode` зафиксирован в `ui/src-tauri/tauri.conf.json` — не
  регенерируйте его, иначе обновления установятся рядом со старой копией.
