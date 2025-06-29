# File: tests/test_ask_routes.py

import pytest
from httpx import AsyncClient
from main import app  # Your FastAPI app entry point

@pytest.mark.asyncio
async def test_ask_get():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ask", params={"question": "Hello?"})
        assert response.status_code == 200
        assert "response" in response.json()

@pytest.mark.asyncio
async def test_ask_post():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/ask", json={"question": "Tell me a joke"})
        assert response.status_code == 200
        assert "response" in response.json()

@pytest.mark.asyncio
async def test_ask_stream_rejects_bad_input():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/ask/stream", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_codex_stream_endpoint(monkeypatch):
    async def dummy_stream(message: str, context: str, user_id=None):
        yield "patch1"
        yield "patch2"

    from agents import codex_agent
    monkeypatch.setattr(codex_agent, "stream", dummy_stream)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/ask/codex_stream",
            json={"question": "fix", "context": "ctx"}
        )
        assert resp.status_code == 200
        assert resp.text == "patch1patch2"
