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
