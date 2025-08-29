# File: conftest.py
# Directory: tests
# Purpose: Shared test fixtures: fake OpenAI client, KB stubs, and a minimal FastAPI app.
#
# Notes:
# - We monkeypatch the module-level `_openai` singletons in agents/*.
# - FakeOpenAI returns simple shaped responses compatible with our code.

import asyncio
import json
import types
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Fake OpenAI ------------------------------------------------------------------------------

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
        # If caller asked for JSON, return JSON text; else plain text
        content = self._payload
        return _Resp(content)

class FakeOpenAI:
    def __init__(self, payload: str):
        self.chat = types.SimpleNamespace(completions=FakeChatCompletions(payload))

@pytest.fixture
def fake_openai_json_ok():
    """Planner-style valid JSON result with final_answer for definition fast-path."""
    payload = json.dumps({
        "objective": "Answer the definition.",
        "steps": [{"type": "analysis", "summary": "Use provided context."}],
        "recommendation": "Answer directly.",
        "route": "echo",
        "final_answer": "Relay Command Center is the AI-assisted control plane for your solar and miner ops."
    })
    return FakeOpenAI(payload)

@pytest.fixture
def fake_openai_coercible():
    """Planner returns text-wrapped JSON that requires coercion."""
    payload = "Here is the plan:\n```json\n" + json.dumps({
        "objective": "Coercible JSON",
        "steps": [],
        "recommendation": "",
        "route": "echo"
    }) + "\n```"
    return FakeOpenAI(payload)

@pytest.fixture
def fake_openai_text_reply():
    return FakeOpenAI("This is a concise, direct answer based on context.")

# --- Minimal FastAPI app with /ask ------------------------------------------------------------

@pytest.fixture
def test_app(monkeypatch, fake_openai_json_ok):
    # Patch planner/echo singletons before import of router
    import importlib
    planner = importlib.import_module("agents.planner_agent")
    echo = importlib.import_module("agents.echo_agent")
    monkeypatch.setattr(planner, "_openai", fake_openai_json_ok, raising=True)
    monkeypatch.setattr(echo, "_openai", fake_openai_json_ok, raising=True)

    # Patch semantic search to return deterministic hits
    sem = importlib.import_module("services.semantic_retriever")
    monkeypatch.setattr(sem, "search", lambda q, **kw: [
        {"title":"Relay Overview","path":"README.md","tier":"global","score":0.91,"snippet":"Relay Command Center overview..."}
    ], raising=True)

    # Build app and mount /ask router
    from fastapi import APIRouter
    app = FastAPI()
    ask_router = importlib.import_module("routes.ask").router
    app.include_router(ask_router)
    return TestClient(app)
