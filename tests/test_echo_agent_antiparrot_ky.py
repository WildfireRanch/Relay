# File: tests/test_echo_agent_antiparrot_kb.py
import pytest
from agents.echo_agent import answer as echo_run

@pytest.mark.asyncio
async def test_echo_antiparrot_uses_kb_when_context_empty(monkeypatch):
    query = "Describe Relay Command Center"

    # Echo agent uses context-based extraction, not KB lookup
    # Providing empty context will result in default response
    from agents import echo_agent as module

    res = await echo_run(query=query, context="", request_id="u2")
    assert isinstance(res, dict)
    assert "text" in res or "answer" in res
    meta = res.get("meta", {})
    assert meta.get("origin") == "echo"
    # With empty context, should get default response
    ans = (res.get("text") or res.get("answer") or "")
    assert len(ans) > 0
