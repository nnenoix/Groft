"""Tests for core/handoff_parser + handoff component section."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.handoff import scan_and_record_handoff, _last_fingerprints  # noqa: E402
from core.handoff_parser import extract_components  # noqa: E402


_SAMPLE_HTML = """<html><body>
  <header id="top">hello</header>
  <main class="hero landing">content</main>
  <footer>bye</footer>
</body></html>
"""


def test_extract_components_basic(tmp_path: Path) -> None:
    html_path = tmp_path / "sample.html"
    html_path.write_text(_SAMPLE_HTML, encoding="utf-8")

    comps = extract_components(html_path)
    assert len(comps) == 3

    assert comps[0] == {
        "name": "top",
        "tag": "header",
        "classes": [],
        "id": "top",
        "path": str(html_path),
    }
    assert comps[1] == {
        "name": "hero",
        "tag": "main",
        "classes": ["hero", "landing"],
        "id": None,
        "path": str(html_path),
    }
    # footer has no id/class → positional index 2 among scanned tags
    assert comps[2] == {
        "name": "footer-2",
        "tag": "footer",
        "classes": [],
        "id": None,
        "path": str(html_path),
    }


@pytest.mark.asyncio
async def test_scan_and_record_mixed_assets(tmp_path: Path) -> None:
    _last_fingerprints.pop(tmp_path, None)

    handoff_root = tmp_path / "ork-handoff"
    handoff_root.mkdir()
    html_path = handoff_root / "page.html"
    html_path.write_text(_SAMPLE_HTML, encoding="utf-8")
    png_path = handoff_root / "image.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    rels = await scan_and_record_handoff(tmp_path)
    assert set(rels) == {"ork-handoff/page.html", "ork-handoff/image.png"}

    md = (tmp_path / "architecture" / "design-handoff.md").read_text(encoding="utf-8")

    assert "- `ork-handoff/page.html`" in md
    assert "- `ork-handoff/image.png`" in md

    assert "## Обнаруженные компоненты" in md
    components_section = md.split("## Обнаруженные компоненты", 1)[1]
    assert "`ork-handoff/page.html` — `top`" in components_section
    assert "`ork-handoff/page.html` — `hero`" in components_section
    assert "`ork-handoff/page.html` — `footer-2`" in components_section
    assert "tag=header" in components_section
    assert "classes=hero, landing" in components_section
    assert "image.png" not in components_section
