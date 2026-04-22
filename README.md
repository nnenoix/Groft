# Groft

Claude-Code orchestration — desktop app + MCP server for a solo-opus session.

## Install

Download the latest MSI from
[Releases](https://github.com/nnenoix/Groft/releases) and run it.

See [packaging/README.md](packaging/README.md) for build details.

**Prerequisites:** Claude CLI (`claude`) must be on PATH.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The MCP server (`communication/mcp_server.py`) is started automatically
by Claude Code from `.mcp.json` — no separate process to run.

UI dev loop:

```bash
cd ui && npm install && npm run tauri dev
```

See [CLAUDE.md](CLAUDE.md) for architecture and the seven-rule constitution
(enforced via Claude Code hooks in `.claude/settings.json`).
