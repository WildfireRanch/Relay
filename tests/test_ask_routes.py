# File: test_ask_routes.py
# Directory: tests
# Purpose: Route-level tests for /ask and legacy/stream shims.

import pytest
from httpx import AsyncClient
from main import app  # your FastAPI app entry point

@pytest.mark.asyncio
async def test_ask_get_legacy():
    # Requires the optional GET /ask alias
    async with AsyncClient(app=app, base_url="http://test") as client:
        res = await client.get("/ask", params={"question": "Hello?"})
        assert res.status_code == 200
        j = res.json()
        assert "routed_result" in j
        assert isinstance(j["routed_result"], dict)

@pytest.mark.asyncio
async def test_ask_post_legacy_key_question():
    # POST using legacy "question" key; accepted via alias on AskRequest.query
    async with AsyncClient(app=app, base_url="http://test") as client:
        res = await client.post("/ask", json={"question": "Tell me a joke"})
        assert res.status_code == 200
        j = res.json()
        assert "routed_result" in j
        # answer-first path should produce an answer or response string
        ans = j["routed_result"].get("answer") or j["routed_result"].get("response")
        assert isinstance(ans, str) and len(ans) > 0

@pytest.mark.asyncio
async def test_ask_post_new_key_query():
    # POST using new "query" key (preferred)
    async with AsyncClient(app=app, base_url="http://test") as client:
        res = await client.post("/ask", json={"query": "What is Relay Command Center?"})
        assert res.status_code == 200
        j = res.json()
        ans = j["routed_result"].get("answer") or j["routed_result"].get("response")
        assert isinstance(ans, str) and len(ans) > 0

@pytest.mark.asyncio
async def test_ask_stream_rejects_bad_input():
    # Only keep if your app defines /ask/stream; otherwise remove this test.
    async with AsyncClient(app=app, base_url="http://test") as client:
        res = await client.post("/ask/stream", json={})
        # 422 if FastAPI validation runs; adjust to your actual behavior
        assert res.status_code in (400, 422)

@pytest.mark.asyncio
async def test_codex_stream_endpoint(monkeypatch):
    # Only keep if your app defines /ask/codex_stream; otherwise remove.
    try:
        from agents import codex_agent
    except Exception:
        pytest.skip("codex_agent not available")

    async def dummy_stream(query: str, context: str, user_id=None):
        yield "patch1"
        yield "patch2"

    monkeypatch.setattr(codex_agent, "stream", dummy_stream, raising=True)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/ask/codex_stream", json={"question": "fix", "context": "ctx"})
        assert resp.status_code == 200
        assert resp.text == "patch1patch2"
