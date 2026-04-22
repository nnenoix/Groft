# Packaging — Groft Desktop (Tauri)

Groft ships as a Tauri desktop app. The Python side (MCP server) is **not**
bundled — Claude Code starts it automatically from `.mcp.json`, so the MSI
only contains the UI and the seed `.claude/agents/` templates.

## Build

```
cd ui
npm install
npm run tauri build
```

Output:

- Windows: `ui/src-tauri/target/release/bundle/msi/Groft_<version>_x64_en-US.msi`
- Linux:   `ui/src-tauri/target/release/bundle/{deb,appimage}/`
- macOS:   `ui/src-tauri/target/release/bundle/{dmg,macos}/`

## Install from release

1. Download `Groft_<version>_x64_en-US.msi` from
   [GitHub Releases](https://github.com/nnenoix/Groft/releases).
2. Double-click. Windows SmartScreen может показать warning (приложение не
   подписано) — More info → Run anyway.
3. Launch "Groft" from the Start menu.
4. On first launch the app seeds `%APPDATA%\com.groft.app\.claude\agents\`
   with the bundled subagent templates.

**Prerequisites:** Claude CLI (`claude`) must be on PATH. Install from
https://docs.anthropic.com/en/docs/claude-code/.

## Uninstall

Windows → Settings → Apps → Groft → Uninstall. User data in
`%APPDATA%\com.groft.app\` не удаляется автоматически (сотрите руками
если нужно полностью чистое состояние).

## Notes

- Windows hosts need the Visual C++ Redistributable (usually pre-installed).
- MSI `upgradeCode` зафиксирован в `ui/src-tauri/tauri.conf.json` — не
  регенерируйте его, иначе обновления установятся рядом со старой копией.
- No orchestrator sidecar is spawned anymore. The MCP server runs as a
  short-lived subprocess launched by Claude Code when the user attaches
  to a project with `.mcp.json`.
