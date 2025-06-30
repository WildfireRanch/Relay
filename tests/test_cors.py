import importlib
import pytest
from httpx import AsyncClient
import os

@pytest.mark.asyncio
async def test_cors_regex(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN_REGEX", r"http://localhost:\d+")
    import main
    importlib.reload(main)
    async with AsyncClient(app=main.app, base_url="http://test") as client:
        resp = await client.options(
            "/test-cors",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    monkeypatch.delenv("FRONTEND_ORIGIN_REGEX", raising=False)
    importlib.reload(main)
