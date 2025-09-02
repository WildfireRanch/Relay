# File: tests/test_mcp_critics_invocation.py
import asyncio
import types
import pytest

import agents.mcp_agent as mcp


@pytest.mark.asyncio
async def test_critics_invoked_with_correct_signature(monkeypatch):
    # 1) Fake context builder
    async def fake_build_context(query, files, topics, debug=False):
        return {"context": "CTX", "files_used": []}
    monkeypatch.setattr(mcp, "build_context", fake_build_context)

    # 2) Fake planner -> chooses echo route
    class FakePlanner:
        async def ask(self, query, context):
            return {"plan_id": "P1", "route": "echo", "_diag": {"final_answer_origin": "model"}}
    monkeypatch.setattr(mcp, "planner_agent", FakePlanner())

    # 3) Fake echo result (include meta to bubble up later)
    async def fake_echo_agent_run(query, context, user_id, plan=None):
        return {"response": "OK", "meta": {"origin": "planner"}}
    monkeypatch.setattr(mcp, "echo_agent_run", fake_echo_agent_run)

    # 4) Capture critics invocation
    seen = {"called": False, "plan": None, "query": None}

    async def fake_run_critics(*, plan, query, prior_plans=None):
        seen["called"] = True
        seen["plan"] = plan
        seen["query"] = query
        return [{"critic": "StructureCritic", "ok": True}]
    monkeypatch.setattr(mcp, "run_critics", fake_run_critics)

    # Execute
    out = await mcp.run_mcp("What is Relay?", role="planner", files=[], topics=[], user_id="u1", debug=True)

    # Assert critics were called with the correct named params
    assert seen["called"] is True
    assert seen["query"] == "What is Relay?"
    # Critics should get an artifact dict
    assert isinstance(seen["plan"], dict)
    # MCP returns critics and meta
    assert isinstance(out.get("critics"), list)
    assert out.get("meta", {}).get("route") == "echo"
    assert out.get("meta", {}).get("plan_id") == "P1"
