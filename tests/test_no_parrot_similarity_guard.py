# File: tests/test_no_parrot_similarity_guard.py
import pytest
from agents.echo_agent import run as echo_run

@pytest.mark.asyncio
async def test_similarity_guard_forces_resynthesis(monkeypatch):
    query = "What is Relay Command Center?"
    context = "Relay Command Center is a production system that orchestrates agents for control and docs."
    # Simulate planner-provided final_answer that just parrots the prompt
    plan = {"final_answer": "What is Relay Command Center?"}

    # Disable KB so we expect context-origin
    from agents import echo_agent as module
    monkeypatch.setattr(module, "definition_from_kb", None, raising=False)

    res = await echo_run(query=query, context=context, user_id="u3", plan=plan)
    assert "response" in res
    meta = res.get("meta", {})
    assert meta.get("origin") == "context"
    assert meta.get("antiparrot", {}).get("detected") is True
    # Ensure it's not just the prompt
    assert res["response"].strip().lower() != query.strip().lower()
