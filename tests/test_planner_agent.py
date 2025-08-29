# File: test_planner_agent.py
# Directory: tests
# Purpose: Validate Planner JSON-mode behavior and coercion fallback.
#
# Upstream:
#   - ENV: (none; OpenAI calls are monkeypatched)
#   - Imports: pytest, importlib
#
# Downstream:
#   - agents.planner_agent (ask → JSON parse/coerce, route selection)
#
# Contents:
#   - fixtures: FakeOpenAI helpers (inline)
#   - test_planner_json_ok()
#   - test_planner_coercion()

import json
import types
import importlib
import pytest

# ---- Minimal fake OpenAI client --------------------------------------------------------------

class _Msg:
    def __init__(self, content: str):
        self.content = content

class _Choice:
    def __init__(self, content: str):
        self.message = _Msg(content)

class _Resp:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]

class FakeChatCompletions:
    def __init__(self, payload: str):
        self._payload = payload
    async def create(self, **kwargs):
        return _Resp(self._payload)

class FakeOpenAI:
    def __init__(self, payload: str):
        self.chat = types.SimpleNamespace(completions=FakeChatCompletions(payload))


@pytest.mark.asyncio
async def test_planner_json_ok(monkeypatch):
    """Planner returns strict JSON (response_format json_object), parsed without coercion."""
    payload = json.dumps({
        "objective": "Answer the definition.",
        "steps": [{"type": "analysis", "summary": "Use provided context."}],
        "recommendation": "Answer directly.",
        "route": "echo",
        "final_answer": "Relay Command Center is the AI-assisted control plane for solar + miner ops."
    })
    fake = FakeOpenAI(payload)

    planner_mod = importlib.import_module("agents.planner_agent")
    monkeypatch.setattr(planner_mod, "_openai", fake, raising=True)

    plan = await planner_mod.planner_agent.ask("What is Relay?", "CTX")
    assert isinstance(plan, dict)
    assert plan.get("route") == "echo"
    assert isinstance(plan.get("plan_id"), str) and len(plan["plan_id"]) > 0
    assert isinstance(plan.get("final_answer"), str) and len(plan["final_answer"]) > 0


@pytest.mark.asyncio
async def test_planner_coercion(monkeypatch):
    """Planner returns text-wrapped JSON; parser should coerce the first JSON object."""
    wrapped = "Here is the plan:\n```json\n" + json.dumps({
        "objective": "Coercible JSON",
        "steps": [],
        "recommendation": "",
        "route": "echo"
    }) + "\n```"
    fake = FakeOpenAI(wrapped)

    planner_mod = importlib.import_module("agents.planner_agent")
    monkeypatch.setattr(planner_mod, "_openai", fake, raising=True)

    plan = await planner_mod.planner_agent.ask("Explain something", "CTX")
    assert isinstance(plan, dict)
    assert plan.get("route") == "echo"
    assert "objective" in plan
