# File: test_mcp_agent.py
# Directory: tests
# Purpose:
#   Full behavior coverage for agents/mcp_agent.run_mcp:
#     - planner happy path (route → handler ok, critics pass)
#     - metaplanner override (planner says X, meta switches to Y)
#     - explicit role dispatch
#     - unknown role → echo fallback (non-fatal)
#     - context builder failure → echo fallback (non-fatal)
#     - handler failure → echo fallback (non-fatal)
#     - critics failure → non-fatal (critics=None)
#     - auto queue_action when handler returns {"action": {...}}
#
# Notes:
#   - Patch symbols *as imported inside* agents.mcp_agent
#     (i.e., monkeypatch "agents.mcp_agent.<name>").
#   - Echo returns {"answer": "...", "route": "echo"} in the hardened pipeline.

import pytest

pytestmark = pytest.mark.asyncio


# ----------------------------- Fakes & helpers --------------------------------

async def _fake_context_ok(query, files=None, topics=None, debug=False):
    # Return dict-shaped debug-like result so both shapes are exercised in MCP
    return {"context": f"[CTX for {query}]", "files_used": [{"type": "summary", "source": "docs/PROJECT_SUMMARY.md"}]}

async def _fake_echo(query, context, user_id, **kwargs):
    # Echo shape used by new pipeline
    return {"route": "echo", "answer": f"echo: {query}", "context_len": len(context)}

class _FakePlanner:
    def __init__(self, route="echo", plan_id="plan-123", objective="do a thing", final_answer=None):
        self._route = route
        self._plan_id = plan_id
        self._objective = objective
        self._final = final_answer

    async def ask(self, query, context):
        plan = {
            "objective": self._objective,
            "steps": [{"type": "analysis", "summary": "analyze"}],
            "recommendation": "",
            "route": self._route,
            "plan_id": self._plan_id,
        }
        if self._final:
            plan["final_answer"] = self._final
        return plan

async def _fake_critics_pass(artifact, context):
    return [{"name": "ClarityCritic", "passes": True}]

async def _fake_critics_fail(artifact, context):
    raise RuntimeError("critics boom")

async def _fake_handler_ok(*, query, context, user_id, **kwargs):
    return {"handled": True, "route_used": "codex", "query": query}

async def _fake_handler_action(*, query, context, user_id, **kwargs):
    return {"handled": True, "action": {"type": "control", "summary": "toggle relay"}}

async def _fake_handler_boom(*, query, context, user_id, **kwargs):
    raise RuntimeError("handler exploded")


# ----------------------------- Tests ------------------------------------------

async def test_planner_happy_path(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"), raising=True)
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex", raising=True)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass, raising=True)

    # Dispatch table entries
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)

    result = await mcp.run_mcp("hello", role="planner", user_id="u1", debug=False)

    assert "plan" in result and result["plan"]["route"] == "codex"
    assert result["routed_result"]["handled"] is True
    assert isinstance(result["critics"], list) and result["critics"][0]["passes"] is True
    assert result["context"].startswith("[CTX for hello]")


async def test_metaplanner_override(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="echo"), raising=True)
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "docs", raising=True)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass, raising=True)

    monkeypatch.setitem(mcp.ROUTING_TABLE, "docs", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)

    result = await mcp.run_mcp("deep dive", role="planner", user_id="u2")

    assert result["plan"].get("meta_override") == "docs"
    assert result["routed_result"]["handled"] is True


async def test_explicit_role_dispatch(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "simulate", lambda **kw: _fake_handler_ok(**kw))

    result = await mcp.run_mcp("what if?", role="simulate", user_id="u3")
    assert result["plan"] is None
    assert result["routed_result"]["handled"] is True


async def test_unknown_role_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)

    result = await mcp.run_mcp("?", role="nonexistent", user_id="u4")
    assert result["routed_result"]["route"] == "echo"
    assert "error" in result and "Unknown role" in result["error"]


async def test_context_failure_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    async def _boom(*args, **kwargs):
        raise RuntimeError("ctx down")

    monkeypatch.setattr(mcp, "build_context", _boom, raising=True)
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)

    result = await mcp.run_mcp("x", role="planner", user_id="u5")
    assert result["plan"] is None
    assert "error" in result and "Failed to build context" in result["error"]
    assert result["routed_result"]["route"] == "echo"


async def test_handler_failure_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"), raising=True)
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex", raising=True)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_boom(**kw))
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass, raising=True)

    result = await mcp.run_mcp("robust please", role="planner", user_id="u6")
    assert result["routed_result"]["route"] == "echo"


async def test_critics_failure_nonfatal(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"), raising=True)
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex", raising=True)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_fail, raising=True)

    result = await mcp.run_mcp("review this", role="planner", user_id="u7")
    assert result["routed_result"]["handled"] is True
    assert result["critics"] is None  # dropped but non-fatal


async def test_auto_queue_action(monkeypatch):
    import agents.mcp_agent as mcp

    called = {"count": 0, "last": None}

    def _queue_action_spy(action):
        called["count"] += 1
        called["last"] = action

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok, raising=True)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="control"), raising=True)
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "control", raising=True)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "control", lambda **kw: _fake_handler_action(**kw))
    monkeypatch.setattr(mcp, "echo_agent_run", _fake_echo, raising=True)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass, raising=True)
    monkeypatch.setattr(mcp, "queue_action", _queue_action_spy, raising=True)

    result = await mcp.run_mcp("toggle relay", role="planner", user_id="u8")

    assert called["count"] == 1
    assert called["last"]["type"] == "control"
    assert result["routed_result"]["handled"] is True
