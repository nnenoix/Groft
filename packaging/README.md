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

## Notes

- Windows hosts need the Visual C++ Redistributable (usually pre-installed).
- `start.ps1` / `stop.ps1` keep working for dev mode with system Python.
- Tauri sidecar wiring and MSI packaging land in later PRs.
