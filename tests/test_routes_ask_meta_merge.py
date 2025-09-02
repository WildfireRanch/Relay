# File: tests/test_routes_ask_meta_merge.py
import pytest

@pytest.mark.asyncio
async def test_routes_ask_merges_upstream_meta(monkeypatch):
    # Skip if your project structure differs; adapt imports accordingly.
    try:
        import routes.ask as ask_route
        import agents.mcp_agent as mcp
    except Exception:
        pytest.skip("Route or MCP import failed")

    # Stub MCP to return upstream meta
    async def fake_run_mcp(**kwargs):
        return {
            "plan": {"plan_id": "PX"},
            "routed_result": {"response": "OK", "meta": {"origin": "kb", "antiparrot": {"detected": True}}},
            "critics": [],
            "context": "CTX",
            "files_used": [],
            "meta": {"route": "echo", "timings_ms": {"context_ms": 1}},
        }
    monkeypatch.setattr(ask_route.mcp_agent, "run_mcp", fake_run_mcp)

    # Minimal FastAPI handler call (bypass actual web stack)
    # If your ask route expects a Pydantic model, call the function directly with kwargs.
    out = await ask_route.ask(query="Define Relay", role="planner", files=None, topics=None, debug=True)
    assert out.meta.get("origin") == "kb"
    assert out.meta.get("route") == "echo"
    assert out.meta.get("timings_ms", {}).get("context_ms") == 1
