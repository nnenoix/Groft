import os
from PyInstaller.utils.hooks import collect_all

# spec lives in packaging/, sources live one level up; anchor everything to
# the project root so paths inside the spec stay short.
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

datas, binaries, hiddenimports = [], [], []
for pkg in ("watchfiles",):
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
    (os.path.join(PROJECT_ROOT, "config.yml"), "."),
    (os.path.join(PROJECT_ROOT, ".claude", "agents"), ".claude/agents"),
]

a = Analysis([os.path.join(PROJECT_ROOT, "core", "main.py")],
             pathex=[PROJECT_ROOT],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "pytest", "pytest_asyncio"])
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="orchestrator", console=True, debug=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="orchestrator")
