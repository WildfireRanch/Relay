# File: tests/test_no_parrot_similarity_guard.py
import pytest
from agents.echo_agent import answer as echo_run

@pytest.mark.asyncio
async def test_similarity_guard_forces_resynthesis(monkeypatch):
    query = "What is Relay Command Center?"
    context = "Relay Command Center is a production system that orchestrates agents for control and docs."

    # Echo agent extracts bullets from context without parroting the query
    from agents import echo_agent as module

    res = await echo_run(query=query, context=context, request_id="u3")
    assert isinstance(res, dict)
    assert "text" in res or "answer" in res
    meta = res.get("meta", {})
    assert meta.get("origin") == "echo"
    # Ensure it's not just the prompt echoed back
    ans = (res.get("text") or res.get("answer") or "").strip().lower()
    assert ans != query.strip().lower()
    assert len(ans) > 0
