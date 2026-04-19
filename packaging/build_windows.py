from __future__ import annotations

"""Cross-platform PyInstaller build helper for Groft orchestrator.

Runs PyInstaller against ``packaging/orchestrator.spec`` and optionally
smoke-tests the resulting binary. Works on Linux (ELF, useful for CI) and
Windows (PE) — the only difference is the exe filename.
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT / "packaging" / "orchestrator.spec"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Groft orchestrator standalone bundle."
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run the built binary with --smoke after building.",
    )
    parser.add_argument(
        "--distpath",
        default=None,
        help="Override PyInstaller distpath (default: ./dist).",
    )
    return parser.parse_args(argv)


def _exe_name() -> str:
    return "orchestrator.exe" if sys.platform == "win32" else "orchestrator"


def _bundle_size_mb(dist_dir: Path) -> float:
    total = 0
    for p in dist_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                # missing/dangling entries during rglob are non-fatal for size
                continue
    return total / (1024 * 1024)


def build(distpath: str | None) -> Path:
    """Run PyInstaller; return path to the built exe."""
    extra: list[str] = []
    if distpath:
        extra += ["--distpath", distpath]
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_PATH),
        "--clean",
        "--noconfirm",
    ] + extra
    print(f"[build] {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)

    dist_root = Path(distpath) if distpath else PROJECT_ROOT / "dist"
    bundle_dir = dist_root / "orchestrator"
    exe = bundle_dir / _exe_name()
    if not exe.is_file():
        raise SystemExit(f"build failed: {exe} not found")
    size_mb = _bundle_size_mb(bundle_dir)
    print(f"[build] bundle: {bundle_dir} ({size_mb:.1f} MB)", flush=True)
    return exe


def smoke(exe: Path) -> None:
    """Invoke `<exe> --smoke`; raise on failure."""
    print(f"[smoke] {exe} --smoke", flush=True)
    result = subprocess.run(
        [str(exe), "--smoke"],
        timeout=60,
        check=True,
        capture_output=True,
    )
    blob = result.stdout + result.stderr
    if b"smoke ok" not in blob:
        raise SystemExit(
            f"smoke failed: 'smoke ok' missing in output\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    print("[smoke] ok", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    exe = build(args.distpath)
    if args.smoke:
        smoke(exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
