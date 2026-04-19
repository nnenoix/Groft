# Groft

Claude-Code agent orchestration — Windows desktop app.

## Install

Download the latest MSI from
[Releases](https://github.com/nnenoix/Groft/releases) and run it.

See [packaging/README.md](packaging/README.md) for build/install details.

## Development

```bash
python -m venv .venv && source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate                           # Windows
pip install -r requirements-dev.txt
pytest -v
```

UI dev loop:

```bash
cd ui && npm install && npm run tauri dev
```

See [CLAUDE.md](CLAUDE.md) for architecture.
