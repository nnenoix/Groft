from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from core.handoff_parser import extract_components

log = logging.getLogger(__name__)

# kept small on purpose — we inventory files, not parse design semantics
_MAX_FILES_LISTED = 200

# fingerprint of the last successful scan, keyed by project_root. Lets the
# periodic poll cheaply skip repeat calls without re-reading the markdown.
_last_fingerprints: dict[Path, str] = {}


def _collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.exists() or not root.is_dir():
        return files
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            files.append(entry)
        if len(files) >= _MAX_FILES_LISTED:
            break
    return files


def _format_inventory(project_root: Path, handoff_root: Path, files: list[Path]) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel_root = handoff_root.relative_to(project_root) if handoff_root.is_relative_to(project_root) else handoff_root
    lines: list[str] = []
    lines.append(f"## {ts} — handoff detected at `{rel_root}`")
    lines.append("")
    lines.append(f"- **Источник:** `{rel_root}`")
    lines.append(f"- **Файлов обнаружено:** {len(files)}")
    lines.append("- **Инвентарь:**")
    if not files:
        lines.append("  - _пусто_")
    else:
        for f in files:
            rel = f.relative_to(project_root) if f.is_relative_to(project_root) else f
            try:
                size = f.stat().st_size
            except OSError:
                size = -1
            lines.append(f"  - `{rel}` ({size} B)")
    lines.append("- **Статус:** обнаружен, не проанализирован — Opus должен прочитать файлы и заполнить план.")
    lines.append("")
    return "\n".join(lines)


def _rel_path(project_root: Path, path: Path) -> str:
    return str(path.relative_to(project_root)) if path.is_relative_to(project_root) else str(path)


async def scan_and_record_handoff(project_root: Path) -> list[str]:
    """Detect Claude Design handoff payload and append inventory to architecture/design-handoff.md.

    Non-destructive: appends a new dated section. Returns the list of relative
    file paths in the current inventory when something new was recorded; an
    empty list if the fingerprint matches the previous scan or there is
    nothing to inventory.
    """
    handoff_root = project_root / "ork-handoff"
    if not handoff_root.exists():
        return []

    files = _collect_files(handoff_root)
    if not files:
        return []

    components: list[dict] = []
    for f in files:
        if f.suffix.lower() == ".html":
            components.extend(extract_components(f))

    fingerprint_parts = ["\n".join(str(f) for f in files)]
    if components:
        component_names = sorted(c["name"] for c in components)
        fingerprint_parts.append("components:" + ",".join(component_names))
    file_fingerprint = "\n".join(fingerprint_parts)

    # cheap module-level dedupe — periodic poll runs every 30s, no need to
    # touch the markdown file when the file set hasn't shifted
    if _last_fingerprints.get(project_root) == file_fingerprint:
        return []

    target = project_root / "architecture" / "design-handoff.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""

    # cross-process dedupe: same fingerprint already inventoried by a prior run
    if file_fingerprint and file_fingerprint in existing:
        _last_fingerprints[project_root] = file_fingerprint
        return []

    inventory = _format_inventory(project_root, handoff_root, files)
    # stash the fingerprint as an HTML comment so it's hidden from humans but findable by us
    fingerprint_comment = f"<!-- handoff-fingerprint:\n{file_fingerprint}\n-->\n"

    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(inventory)
        fh.write(fingerprint_comment)
        if components:
            fh.write("\n## Обнаруженные компоненты\n\n")
            for comp in components:
                rel = _rel_path(project_root, Path(comp["path"]))
                classes_str = ", ".join(comp["classes"])
                fh.write(f"- `{rel}` — `{comp['name']}` (tag={comp['tag']}, classes={classes_str})\n")
            fh.write("\n")
    _last_fingerprints[project_root] = file_fingerprint
    log.info("recorded %d files under %s", len(files), handoff_root)

    rels: list[str] = []
    for f in files:
        rels.append(_rel_path(project_root, f))
    return rels
