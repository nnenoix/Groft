"""PyInstaller bundle smoke test.

Builds the orchestrator spec into a temp distpath, runs the resulting exe with
``--smoke``, and asserts an exit-zero plus "smoke ok" in the output.

Skipped by default — PyInstaller takes ~30-60s and pulls in the whole import
graph, so we don't want it on every `pytest` invocation. Opt in via:

    GROFT_RUN_BUNDLE_TESTS=1 pytest tests/integration/test_frozen_boot.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "packaging" / "orchestrator.spec"


pytestmark = pytest.mark.skipif(
    os.environ.get("GROFT_RUN_BUNDLE_TESTS") != "1",
    reason="set GROFT_RUN_BUNDLE_TESTS=1 to run",
)


def test_spec_builds_and_smoke_runs(tmp_path: Path) -> None:
    distpath = tmp_path / "dist"
    workpath = tmp_path / "build"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC_PATH),
            "--clean",
            "--noconfirm",
            "--distpath",
            str(distpath),
            "--workpath",
            str(workpath),
        ],
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        timeout=300,
    )

    exe_name = "orchestrator.exe" if sys.platform == "win32" else "orchestrator"
    exe = distpath / "orchestrator" / exe_name
    assert exe.is_file(), f"exe missing: {exe}"

    result = subprocess.run(
        [str(exe), "--smoke"],
        timeout=60,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"smoke exit={result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert b"smoke ok" in result.stdout + result.stderr, (
        f"'smoke ok' missing\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
