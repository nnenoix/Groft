from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# kept small on purpose — we inventory files, not parse design semantics
_MAX_FILES_LISTED = 200


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


async def scan_and_record_handoff(project_root: Path) -> bool:
    """Detect Claude Design handoff payload and append inventory to architecture/design-handoff.md.

    Non-destructive: appends a new dated section. Returns True if anything was appended.
    """
    handoff_root = project_root / "ork-handoff"
    if not handoff_root.exists():
        return False

    files = _collect_files(handoff_root)
    if not files:
        return False

    inventory = _format_inventory(project_root, handoff_root, files)

    target = project_root / "architecture" / "design-handoff.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""

    # dedupe: skip if the same file list was already inventoried in the last section
    file_fingerprint = "\n".join(str(f) for f in files)
    if file_fingerprint and file_fingerprint in existing:
        return False

    # stash the fingerprint as an HTML comment so it's hidden from humans but findable by us
    fingerprint_comment = f"<!-- handoff-fingerprint:\n{file_fingerprint}\n-->\n"

    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(inventory)
        fh.write(fingerprint_comment)
    print(f"[handoff] recorded {len(files)} files under {handoff_root}")
    return True
