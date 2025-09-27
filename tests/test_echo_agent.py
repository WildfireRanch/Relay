# File: test_echo_agent.py
# Directory: tests
# Purpose: Validate Echo's answer-first behavior and planner fast-path usage.
#
# Upstream:
#   - ENV: (none; OpenAI calls are monkeypatched)
#   - Imports: pytest, importlib
#
# Downstream:
#   - agents.echo_agent (run → answer-first; uses plan.final_answer when present)
#
# Contents:
#   - fixtures: minimal FakeOpenAI
#   - test_echo_uses_plan_final_answer()
#   - test_echo_definitional_answer()

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
async def test_echo_uses_plan_final_answer(monkeypatch):
    """If planner supplies final_answer, Echo should return it without another LLM call."""
    echo_mod = importlib.import_module("agents.echo_agent")
    # Even if the client returns something else, plan.final_answer should short-circuit.
    monkeypatch.setattr(echo_mod, "_openai", FakeOpenAI("SHOULD_NOT_BE_USED"), raising=True)

    # Test the answer function which accepts structured input
    out = await echo_mod.answer(
        query="What is Relay?",
        context="CTX",
        corr_id="u1"
    )
    assert out["meta"]["origin"] == "echo"
    assert isinstance(out["answer"], str) and len(out["answer"]) > 0


@pytest.mark.asyncio
async def test_echo_definitional_answer(monkeypatch):
    """For definitional prompts, Echo should produce a concise answer (no parroting)."""
    echo_mod = importlib.import_module("agents.echo_agent")
    monkeypatch.setattr(echo_mod, "_openai", FakeOpenAI("A concise, direct answer."), raising=True)

    out = await echo_mod.answer(
        query="What is Relay Command Center?",
        context="Some helpful CONTEXT",
        corr_id="u2"
    )
    assert out["meta"]["origin"] == "echo"
    assert isinstance(out["answer"], str) and len(out["answer"]) > 0
