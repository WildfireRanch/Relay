# File: tests/test_echo_agent_antiparrot_context.py
import re
import pytest

# Import echo_agent from your real module path
from agents.echo_agent import run as echo_run


@pytest.mark.asyncio
async def test_echo_antiparrot_uses_context_synthesis(monkeypatch):
    query = "What is the Relay Command Center?"
    context = """
    Relay Command Center is a modular AI-enabled backend and frontend that orchestrates solar,
    miner operations, and document sync via GPT-based agents and automation.
    """

    # Force internal LLM to produce a parrot-ish reply if your code normally calls one
    # Here, we monkeypatch an internal helper if present; otherwise, rely on heuristic in echo.
    # Keep this test black-box: provide context and expect synthesis.

    # Provide a stub definition_from_kb that won't be used (context should win)
    monkeypatch.setenv("DISABLE_NETWORK", "1")
    try:
        from agents import echo_agent as module
    except Exception:
        pytest.skip("echo_agent import failed")

    # Ensure the module's optional kb hook is None so context path is chosen first
    if hasattr(module, "definition_from_kb"):
        monkeypatch.setattr(module, "definition_from_kb", None, raising=False)

    res = await echo_run(query=query, context=context, user_id="u1", plan={"final_answer": "Define Relay Command Center."})
    assert isinstance(res, dict)
    assert "response" in res
    meta = res.get("meta", {})
    # Should claim context origin after anti-parrot synth
    assert meta.get("origin") == "context"
    ap = meta.get("antiparrot") or {}
    assert ap.get("detected") is True
    # Ensure answer is not a restatement
    ans = res["response"].lower()
    assert not ans.startswith("define")
    assert "relay command center" in ans
