from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import (  # noqa: E402
    claudeorch_dir,
    handoff_dir,
    install_root,
    user_data_root,
)


@pytest.fixture(autouse=True)
def _reset_path_cache():
    install_root.cache_clear()
    user_data_root.cache_clear()
    yield
    install_root.cache_clear()
    user_data_root.cache_clear()


def test_dev_mode_uses_install_root(monkeypatch) -> None:
    install_root.cache_clear()
    user_data_root.cache_clear()
    monkeypatch.delenv("CLAUDEORCH_USER_DATA", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert user_data_root() == install_root()


def test_env_override(monkeypatch, tmp_path: Path) -> None:
    install_root.cache_clear()
    user_data_root.cache_clear()
    monkeypatch.setenv("CLAUDEORCH_USER_DATA", str(tmp_path))
    assert user_data_root() == tmp_path.resolve()
    co = claudeorch_dir()
    assert co == tmp_path.resolve() / ".claudeorch"
    assert co.is_dir()


def test_handoff_override(monkeypatch, tmp_path: Path) -> None:
    install_root.cache_clear()
    user_data_root.cache_clear()
    override = tmp_path / "h"
    monkeypatch.setenv("CLAUDEORCH_HANDOFF_DIR", str(override))
    result = handoff_dir()
    assert result == override.resolve()
    assert result.is_dir()


def test_frozen_mode(monkeypatch, tmp_path: Path) -> None:
    install_root.cache_clear()
    user_data_root.cache_clear()
    mei = tmp_path / "mei"
    mei.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert install_root() == mei
