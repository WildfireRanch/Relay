# File: tests/test_echo_agent_antiparrot_kb.py
import pytest
from agents.echo_agent import run as echo_run

@pytest.mark.asyncio
async def test_echo_antiparrot_uses_kb_when_context_empty(monkeypatch):
    query = "Describe Relay Command Center"

    # Stub KB helper to guarantee a deterministic 2–4 sentence definition
    def fake_def_from_kb(q: str) -> str:
        return ("Relay Command Center is a modular AI-enabled control plane for solar and miners. "
                "It provides GPT-driven agents for /ask routing, context injection, and doc sync. "
                "It exposes secure APIs and a frontend to automate operations.")

    from agents import echo_agent as module
    monkeypatch.setattr(module, "definition_from_kb", fake_def_from_kb, raising=False)

    res = await echo_run(query=query, context="", user_id="u2", plan={"final_answer": "Describe Relay Command Center."})
    assert "response" in res
    meta = res.get("meta", {})
    assert meta.get("origin") == "kb"
    assert meta.get("antiparrot", {}).get("detected") is True
    # Ensure the KB text actually made it through
    assert "control plane" in res["response"].lower()
