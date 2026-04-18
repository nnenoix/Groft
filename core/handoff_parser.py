from __future__ import annotations

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_SCAN_TAGS = {"header", "nav", "main", "section", "article", "aside", "footer"}

_SLUG_RE = re.compile(r"[^a-z0-9-]")


def _slugify(raw: str) -> str:
    return _SLUG_RE.sub("-", raw.lower())


def extract_components(html_path: Path) -> list[dict]:
    """Return a list of component candidates found in ``html_path``.

    Each element: ``{name, tag, classes, id, path}`` where ``name`` is a slug
    derived from the id (preferred), first class, or a positional fallback.
    """
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")
    except Exception:
        log.warning("failed to parse %s", html_path, exc_info=True)
        return []

    results: list[dict] = []
    seen: set[str] = set()
    index = 0
    for tag in soup.find_all(True):
        tag_name = tag.name
        if not isinstance(tag_name, str) or tag_name not in _SCAN_TAGS:
            continue
        raw_classes = tag.get("class") or []
        if isinstance(raw_classes, str):
            raw_classes = raw_classes.split()
        classes = [c for c in raw_classes if isinstance(c, str)]
        raw_id = tag.get("id")
        tag_id = raw_id if isinstance(raw_id, str) and raw_id else None

        if tag_id:
            raw_name = tag_id
        elif classes:
            raw_name = classes[0]
        else:
            # positional index among ALL scanned tags in this file, including
            # duplicates skipped below — matches ТЗ "0-based position among scanned tags"
            raw_name = f"{tag_name}-{index}"

        slug = _slugify(raw_name)
        index += 1

        if slug in seen:
            continue
        seen.add(slug)

        results.append({
            "name": slug,
            "tag": tag_name,
            "classes": classes,
            "id": tag_id,
            "path": str(html_path),
        })
    return results
