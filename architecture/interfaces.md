# Интерфейсы и контракты

## PROCESS-BACKEND-1: Cross-platform ProcessBackend (PR 1/2 — refactor)

### Protocol (новый модуль `core/process/backend.py`)

```python
from typing import Protocol, Mapping
Target = str  # opaque; tmux: "claudeorch:<agent>", windows: "pid:<pid>"

class ProcessBackend(Protocol):
    async def spawn(
        self, name: str, cmd: list[str], env: Mapping[str, str] | None = None
    ) -> Target | None: ...
    async def send_text(
        self, target: Target, text: str, *, press_enter: bool = True
    ) -> bool: ...
    async def kill(self, target: Target) -> bool: ...
    async def capture_output(self, target: Target, lines: int = 50) -> str: ...
    async def is_alive(self, target: Target) -> bool: ...
    def list_targets(self) -> dict[str, Target]: ...  # agent_name → Target
```

**Семантика:**
- `spawn`: создать изолированный процесс/окно, вернуть Target или None при провале. `env` мержится с наследуемым окружением.
- `send_text`: отправить multi-line текст в stdin/pane. Backend обязан защититься от shell-инъекций (tmux: `send-keys -l --`, windows: `stdin.write` как есть). `press_enter=False` — не добавлять финальный Enter (редко нужно).
- `kill`: атомарный kill процесса + детей. True если target существовал.
- `capture_output`: вернуть последние N строк вывода (контракт как у `tmux capture-pane -p -S -<lines>`). Не блокирует.
- `is_alive`: O(1) проверка без I/O где возможно.
- `list_targets`: snapshot — для checkpoints и UI.

### Backends
- `TmuxBackend` (`core/process/tmux_backend.py`) — полное поведение нынешнего `spawner._run_tmux` + `server._tmux_send/_forward_to_tmux` + `watchdog._capture`. Линейка `send-keys -l -- <line>` + bare `send-keys Enter` инкапсулирована внутри `send_text` (инвариант безопасности — ответственность backend'а, не caller'а).
- `InMemoryBackend` (`tests/support/in_memory_backend.py`) — записывает список `(op, target, args)` для assert'ов. Платформенно-нейтральный.
- `WindowsBackend` (`core/process/windows_backend.py`) — `subprocess.Popen(creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP)`, stdout/stderr → `.claudeorch/panes/<agent>.log`. Target = `pid:<pid>`. `send_text` пишет в `proc.stdin` напрямую (CRLF нормализация). `kill` = `proc.terminate()` → `wait(timeout=5)` → `proc.kill()` + `taskkill /T /F /PID`. `capture_output` — tail хвоста лог-файла. Import-safe на Linux: `CREATE_NEW_CONSOLE` берётся через `getattr(subprocess, "CREATE_NEW_CONSOLE", 0)`.

### Factory
`core/process/__init__.py::select_backend(config) -> ProcessBackend`. `platform.system()` → tmux/windows. `config.yml` с `process.backend: tmux|windows|auto` — override.

### Checkpoint совместимость
`agent_states[*]["tmux_target"]` → `"target"`. Read-alias: если нет `target` — читать `tmux_target`. Write — только новое имя.

## PATHS-1: Centralised path resolution (`core/paths.py`)

### Goal
`Path(__file__).resolve().parent.parent` сейчас разбросано по 10+ модулям. Под PyInstaller `__file__` указывает на временную распаковку, поэтому writable state (`.claudeorch/`, `memory/`, …) уезжает в TEMP вместо `%APPDATA%`. PR A вводит единый helper, который различает:
- **install_root** — read-only ресурсы (бандл templates / config defaults).
- **user_data_root** — writable runtime data (DBs, logs, agent memory, чекпойнты).

В dev-режиме оба указывают на корень проекта — поведение бит-идентично текущему.

### API (`core/paths.py`)

```python
import os, sys
from functools import cache
from pathlib import Path

@cache
def install_root() -> Path:
    """Read-only resource root.
    Frozen (PyInstaller): sys._MEIPASS.
    Dev: ascend from this file to repo root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

@cache
def user_data_root() -> Path:
    """Writable runtime data root.
    Honours CLAUDEORCH_USER_DATA env (set by Tauri shell to %APPDATA%\\Groft).
    Falls back to install_root() so dev mode keeps writing into the repo.
    """
    env = os.environ.get("CLAUDEORCH_USER_DATA")
    if env:
        return Path(env).resolve()
    return install_root()

def claudeorch_dir() -> Path: ...   # user_data_root() / ".claudeorch", auto-mkdir
def logs_dir() -> Path: ...         # claudeorch_dir() / "logs"
def panes_dir() -> Path: ...        # claudeorch_dir() / "panes"
def architecture_dir() -> Path: ... # user_data_root() / "architecture"
def memory_dir() -> Path: ...       # user_data_root() / "memory"
def memory_archive_dir() -> Path: ...
def tasks_dir() -> Path: ...        # user_data_root() / "tasks"
def agents_dir() -> Path: ...       # user_data_root() / ".claude" / "agents"
def handoff_dir() -> Path: ...      # CLAUDEORCH_HANDOFF_DIR override; else user_data_root() / "ork-handoff"
def config_path() -> Path: ...      # user_data_root() / "config.yml"
def default_config_path() -> Path:  # install_root() / "config.yml" — bundled template
    ...
```

**Семантика:**
- Все `*_dir()` возвращают существующую директорию (создают при первом обращении). `_path()` — без mkdir.
- `@cache` — install_root / user_data_root резолвятся один раз за процесс. Тесты, которым нужно подменить root, используют `cache_clear()` через fixture.
- Никаких глобальных переменных модуля; любой импорт `from core.paths import logs_dir` безопасен из любой точки.
- В dev (`CLAUDEORCH_USER_DATA` unset, `sys.frozen` false): `user_data_root() == install_root() == repo_root` → пути 1:1 как раньше.
- Под PyInstaller с Tauri-обёрткой: install_root = MEIPASS (R/O), user_data_root = `%APPDATA%\Groft` (R/W).

### Refactor scope (call-sites which must lose `Path(__file__).resolve().parent.parent`)

- `core/main.py` — `BASE_DIR`, agents dir, config path, log файлы.
- `core/agents_watcher.py` — наблюдаемая папка `.claude/agents`.
- `core/handoff.py` — `_default_root()`, `architecture/design-handoff.md`.
- `core/logging_setup.py` — log dir.
- `core/recovery/recovery_manager.py` — checkpoint paths.
- `core/error/error_handler.py` — error DB.
- `core/session/checkpoint.py` — checkpoint DB path default.
- `core/process/windows_backend.py` — log_dir default = `panes_dir()`.
- `core/spawner.py` — pane logs / agent workdir.
- `git_manager/manager.py` — git history DB, worktree base.
- `memory/manager.py` — memory dir + archive.
- `communication/mcp_server.py` — inbox/state.

**Инвариант:** конструкторы продолжают принимать explicit `Path` override (для тестов). Helper только меняет default.

### Acceptance
- `pytest -q` остаётся 7+ green в dev (CLAUDEORCH_USER_DATA unset).
- `grep -rn "Path(__file__).resolve().parent.parent" --include="*.py" .` → только `core/paths.py`.
- `grep -rn 'Path("\.claudeorch' --include="*.py" .` → пусто (всё через `claudeorch_dir()` / `logs_dir()` / `panes_dir()`).
- `python -c "import os; os.environ['CLAUDEORCH_USER_DATA']='/tmp/groft-test'; from core.paths import claudeorch_dir, memory_dir; print(claudeorch_dir(), memory_dir())"` печатает пути под `/tmp/groft-test`.

## BUNDLE-1: PyInstaller orchestrator bundle (`packaging/orchestrator.spec`)

### Goal
Превратить Python-оркестратор в standalone `orchestrator.exe` (onedir), чтобы пользователь запускал Groft без установленного Python. Бандл содержит нативные зависимости (duckdb DLL, watchfiles `_rust_notify.pyd`) и lazy-импорты uvicorn/mcp.

### Entry point
`core/main.py` → `asyncio.run(main())`. Добавляется `--smoke` флаг: импортирует heavy deps через top-level `from`-импорты, логирует `smoke ok` и выходит code=0 ДО старта серверов. Используется build-time верификацией.

### Spec file (`packaging/orchestrator.spec`)
```python
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("duckdb", "watchfiles"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += [
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "mcp.server.fastmcp",
    "mcp.server.stdio",
    "websockets.server",
    "websockets.client",
    "websockets.legacy.server",
    "websockets.legacy.client",
]

datas += [
    ("config.yml", "."),
    (".claude/agents", ".claude/agents"),
]

a = Analysis(["core/main.py"], pathex=["."],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "pytest", "pytest_asyncio"])
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="orchestrator", console=True, debug=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="orchestrator")
```

### Build script (`packaging/build_windows.py`)
- `python -m PyInstaller packaging/orchestrator.spec --clean --noconfirm`.
- Проверка `dist/orchestrator/orchestrator{.exe}` существует.
- Опциональный `--smoke` запуск построенного бинаря.
- Кросс-платформенно: на Linux строит ELF (для CI), на Windows — PE.

### Smoke mode (в `core/main.py`)
В `main()` сразу после `configure_logging`:
```python
if "--smoke" in sys.argv:
    log.info("smoke ok")
    return
```

### Tests (`tests/integration/test_frozen_boot.py`)
- skip если `os.environ.get("GROFT_RUN_BUNDLE_TESTS") != "1"` — иначе `pytest -q` остаётся быстрым.
- `test_spec_builds`: PyInstaller запускается с `--distpath=tmp_path`, exit 0, bundle dir существует.
- `test_frozen_smoke_exits_ok`: запуск бандла с `--smoke`, timeout 60s, exit 0, лог содержит `smoke ok`.

### requirements-dev.txt
Добавить `pyinstaller>=6.0`.

## TAURI-SIDECAR-1: Productization wiring

### Identifier
`com.yegor.ui` → `com.groft.app`. Меняет путь `app_data_dir()` на все ОС (`%APPDATA%\com.groft.app` на Windows).

### Rust state
```rust
struct OrchestratorChild(std::sync::Mutex<Option<std::process::Child>>);
```
Держится через `app.manage(...)`, вынимается в `on_window_event(CloseRequested)` для kill-on-fallback.

### First-run init
1. `app.path().app_data_dir()` → `user_data_dir`, `create_dir_all`.
2. Если `user_data_dir/config.yml` отсутствует — копия из `resource_dir/orchestrator/_internal/config.yml` (fallback `resource_dir/orchestrator/config.yml`).
3. Рекурсивный `.claude/agents/` seed — аналогично.
4. Spawn `resource_dir/orchestrator/orchestrator[.exe]` с `CLAUDEORCH_USER_DATA=user_data_dir`.

### Graceful shutdown
`WindowEvent::CloseRequested` → `api.prevent_close()` → POST `http://localhost:8766/shutdown` (timeout 2s) → wait 1s → child.kill() → `app.exit(0)`. Работа идёт в std thread, не async — blocking reqwest без tokio.

### Python POST /shutdown
`CommunicationServer.set_shutdown_callback(fn: Callable[[], Awaitable[None]])`. REST `POST /shutdown` создаёт `asyncio.create_task(cb())` и возвращает `{"ok": true}` немедленно.

### ProcessGuard.request_shutdown()
Public async-метод, тонкая обёртка над приватным `_shutdown()`. Нужен чтобы REST-endpoint мог дёрнуть тот же path что SIGTERM.

## RELEASE-1: WiX MSI bundle + GitHub Actions release (PR D)

### Trigger
Push git tag `v*` (e.g. `v0.1.0`) → GitHub Actions workflow `.github/workflows/release.yml` → бандл MSI прикрепляется к GitHub Release автоматически.

### Workflow shape
- `on: push: tags: ['v*']` + `workflow_dispatch` (manual re-run).
- `runs-on: windows-latest` (единственная job; нативный build без cross-compile).
- Steps: checkout → setup-python 3.12 → setup-node 20 → `pip install -r requirements-dev.txt` → `python packaging/build_windows.py` (PyInstaller onedir) → rust via `dtolnay/rust-toolchain@stable` → `npm ci` in `ui/` → `npm run tauri build --bundles msi nsis` → upload artifacts + `softprops/action-gh-release@v2` с файлами `ui/src-tauri/target/release/bundle/msi/*.msi`, `ui/src-tauri/target/release/bundle/nsis/*.exe`.

### tauri.conf.json → bundle.windows.wix
```jsonc
"bundle": {
  ...
  "windows": {
    "wix": {
      "language": "en-US",
      "upgradeCode": "a1b2c3d4-0000-0000-0000-000000000000"  // статичный GUID, не менять между релизами
    }
  }
}
```
`upgradeCode` статичный (фиксированный GUID) — иначе обновления установятся параллельно старыми копиями. Сгенерировать один раз через `uuidgen` (или Python `uuid.uuid4()`), закоммитить. НЕ генерить в CI.

### packaging/README.md расширение
Добавить секцию "Install from release":
- Ссылка на GitHub Releases.
- Два target'а: MSI (silent install) + NSIS (interactive).
- Post-install: `%APPDATA%\com.groft.app` создаётся при первом запуске.
- Uninstall: через Add/Remove Programs.

### Acceptance (Linux-side)
Из соображений невозможности кросс-билда валидация идёт по артефактам:
1. `yamllint .github/workflows/release.yml` — пройдено (или стандартный action-lint если доступен).
2. `python3 -c "import json; json.load(open('ui/src-tauri/tauri.conf.json'))"` — парсится без ошибок; поле `bundle.windows.wix.upgradeCode` — валидный GUID.
3. `pytest` зелёный (no regression).
4. Нет новых pytest-зависимостей.

### Out of scope
- Code signing (требует cert).
- Auto-updater (tauri-plugin-updater — отдельный PR).
- macOS/Linux бандлы в этом же workflow (можно добавить позже как matrix).
