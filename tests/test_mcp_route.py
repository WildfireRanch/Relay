import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_mcp_run_invokes_agent(monkeypatch):
    called = {}

    async def fake_run_mcp(query, files=None, topics=None, role="planner", user_id="anonymous", debug=False):
        called['args'] = {
            'query': query,
            'files': files,
            'topics': topics,
            'role': role,
            'user_id': user_id,
            'debug': debug,
        }
        return {"ok": True}

    monkeypatch.setattr("routes.mcp.run_mcp", fake_run_mcp)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/mcp/run", json={"query": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert called['args']['query'] == "hi"

