"""Smoke test for ingest_subagent_report MCP tool."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.mark.asyncio
async def test_ingest_tool_writes_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.decision_log import DecisionLog

    dl = DecisionLog(db_path=tmp_path / "dec.duckdb")
    await dl.initialize()

    import communication.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "AGENT_NAME", "opus")
    # Redirect the tool's memory_root to tmp_path via monkeypatching the module
    mem = tmp_path / "memory"
    mem.mkdir()

    # Inject DecisionLog directly
    original = mcp_mod._decision_log
    mcp_mod._decision_log = dl

    # Patch the ingest_subagent_report's hardcoded memory_root by wrapping
    # the function — simpler: patch Path(__file__).resolve().parents[1]
    # by overriding subagent_ingest.ingest_report call via the tool.
    from core import subagent_ingest as ingest_mod
    real_ingest = ingest_mod.ingest_report

    async def patched_ingest(**kwargs):
        kwargs["memory_root"] = mem
        return await real_ingest(**kwargs)

    monkeypatch.setattr(ingest_mod, "ingest_report", patched_ingest)

    try:
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
        assert "1 decisions #" in result

        log_content = (mem / "session-log.md").read_text(encoding="utf-8")
        assert "add login flow" in log_content
        assert "core/login.py" in log_content
        assert "CSRF strategy?" in log_content

        rows = await dl.list_recent()
        assert len(rows) == 1
        assert rows[0]["agent"] == "opus"
        assert rows[0]["chosen"] == "cookie"
    finally:
        mcp_mod._decision_log = original
        await dl.close()
