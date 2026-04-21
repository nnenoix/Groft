"""Smoke test for ingest_subagent_report MCP tool."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_ingest_tool_writes_session_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import communication.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "AGENT_NAME", "opus")
    mem = tmp_path / "memory"
    mem.mkdir()

    from core import subagent_ingest as ingest_mod
    real_ingest = ingest_mod.ingest_report

    async def patched_ingest(**kwargs):
        kwargs["memory_root"] = mem
        return await real_ingest(**kwargs)

    monkeypatch.setattr(ingest_mod, "ingest_report", patched_ingest)

    result = await mcp_mod.ingest_subagent_report(
        did="add login flow",
        changed_files=["core/login.py"],
        decisions=[
            {"category": "arch", "chosen": "cookie", "reason": "simple"}
        ],
        questions=["CSRF strategy?"],
        memory_notes=["Login uses session cookie"],
    )
    assert result.startswith("✓ ingested at ")
    assert "1 decisions" in result

    log_content = (mem / "session-log.md").read_text(encoding="utf-8")
    assert "add login flow" in log_content
    assert "core/login.py" in log_content
    assert "CSRF strategy?" in log_content
    assert "[arch] cookie" in log_content
    assert "simple" in log_content
