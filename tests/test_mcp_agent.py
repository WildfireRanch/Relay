# ──────────────────────────────────────────────────────────────────────────────
# File: tests/test_mcp_agent.py
# Purpose:
#   Unit tests for agents/mcp_agent.py with full behavior coverage:
#     - planner happy path
#     - metaplanner override
#     - explicit role dispatch
#     - unknown role fallback to echo
#     - context builder failure → echo fallback
#     - handler failure → echo fallback
#     - critics failure is non-fatal
#     - auto queue_action when handler returns {"action": {...}}
#
# Usage:
#   pip install pytest pytest-asyncio
#   pytest -q tests/test_mcp_agent.py
#
# Notes:
#   - We patch symbols *as imported inside* agents.mcp_agent
#     (i.e., "agents.mcp_agent.<name>") so the monkeypatch affects the module
#     under test rather than the original sources.
# ──────────────────────────────────────────────────────────────────────────────

import pytest

# All tests are async because run_mcp is async.
pytestmark = pytest.mark.asyncio


async def _fake_context_ok(query, files, topics, debug=False):
    # Simulate the dict-shaped debug context to exercise both shapes.
    return {
        "context": f"[CTX for {query}]",
        "files_used": [{"type": "summary", "source": "docs/PROJECT_SUMMARY.md"}],
    }


async def _fake_echo(query, context, user_id, **kwargs):
    return {"route": "echo", "message": f"echo: {query}", "context_len": len(context)}


class _FakePlanner:
    def __init__(self, route="echo", plan_id="plan-123", objective="do a thing"):
        self._route = route
        self._plan_id = plan_id
        self._objective = objective

    async def ask(self, query, context):
        return {
            "objective": self._objective,
            "steps": [{"type": "analysis", "summary": "analyze"}],
            "recommendation": "",
            "route": self._route,
            "plan_id": self._plan_id,
        }


async def _fake_critics_pass(artifact, context):
    return [{"name": "ClarityCritic", "passes": True}]


async def _fake_critics_fail(artifact, context):
    raise RuntimeError("critics boom")


async def _fake_trainer_ingest(**kwargs):
    return {"ok": True}


async def _fake_handler_ok(*, query, context, user_id, **kwargs):
    # Generic handler that returns a simple result
    return {"handled": True, "route_used": "codex", "query": query}


async def _fake_handler_action(*, query, context, user_id, **kwargs):
    # Handler that proposes an action to exercise queue_action()
    return {"handled": True, "action": {"type": "control", "summary": "toggle relay"}}


async def _fake_handler_boom(*, query, context, user_id, **kwargs):
    raise RuntimeError("handler exploded")


# ------------------------------------------------------------------------------
# Planner happy path → Meta suggests same route → handler ok → critics pass
# ------------------------------------------------------------------------------
async def test_planner_happy_path(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"))
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex")
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass)
    monkeypatch.setattr(mcp.trainer_agent, "ingest_results", _fake_trainer_ingest)

    # Patch dispatch table entry: codex handler
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)

    result = await mcp.run_mcp("hello", role="planner", user_id="u1", debug=False)

    assert "plan" in result and result["plan"]["route"] == "codex"
    assert result["routed_result"]["handled"] is True
    assert isinstance(result["critics"], list) and result["critics"][0]["passes"] is True
    assert result["context"].startswith("[CTX for hello]")

# ------------------------------------------------------------------------------
# MetaPlanner override route (planner says echo, meta says docs) → docs handler
# ------------------------------------------------------------------------------
async def test_metaplanner_override(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="echo"))
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "docs")
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass)
    monkeypatch.setattr(mcp.trainer_agent, "ingest_results", _fake_trainer_ingest)

    # Patch handlers
    monkeypatch.setitem(mcp.ROUTING_TABLE, "docs", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)

    result = await mcp.run_mcp("deep dive", role="planner", user_id="u2")

    assert result["plan"]["meta_override"] == "docs"
    assert result["routed_result"]["handled"] is True

# ------------------------------------------------------------------------------
# Explicit role dispatch (simulate) → handler ok
# ------------------------------------------------------------------------------
async def test_explicit_role_dispatch(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "simulate", lambda **kw: _fake_handler_ok(**kw))

    result = await mcp.run_mcp("what if?", role="simulate", user_id="u3")
    assert result["plan"] is None
    assert result["routed_result"]["handled"] is True

# ------------------------------------------------------------------------------
# Unknown role → echo fallback
# ------------------------------------------------------------------------------
async def test_unknown_role_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)

    result = await mcp.run_mcp("?", role="nonexistent", user_id="u4")
    assert result["routed_result"]["route"] == "echo"
    assert "error" in result and "Unknown role" in result["error"]

# ------------------------------------------------------------------------------
# Context builder failure → echo fallback with error
# ------------------------------------------------------------------------------
async def test_context_failure_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    async def _boom(*args, **kwargs):
        raise RuntimeError("ctx down")

    monkeypatch.setattr(mcp, "build_context", _boom)
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)

    result = await mcp.run_mcp("x", role="planner", user_id="u5")
    assert result["plan"] is None
    assert "error" in result and "Failed to build context" in result["error"]
    assert result["routed_result"]["route"] == "echo"

# ------------------------------------------------------------------------------
# Handler throws → echo fallback (kept non-fatal)
# ------------------------------------------------------------------------------
async def test_handler_failure_fallback(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"))
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex")
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_boom(**kw))
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass)
    monkeypatch.setattr(mcp.trainer_agent, "ingest_results", _fake_trainer_ingest)

    result = await mcp.run_mcp("robust please", role="planner", user_id="u6")
    assert result["routed_result"]["route"] == "echo"

# ------------------------------------------------------------------------------
# Critics crash → non-fatal (critics=None)
# ------------------------------------------------------------------------------
async def test_critics_failure_nonfatal(monkeypatch):
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="codex"))
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "codex")
    monkeypatch.setitem(mcp.ROUTING_TABLE, "codex", lambda **kw: _fake_handler_ok(**kw))
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_fail)
    monkeypatch.setattr(mcp.trainer_agent, "ingest_results", _fake_trainer_ingest)

    result = await mcp.run_mcp("review this", role="planner", user_id="u7")
    assert result["routed_result"]["handled"] is True
    assert result["critics"] is None  # dropped but non-fatal

# ------------------------------------------------------------------------------
# Auto-queue: handler returns {"action": {...}} → queue_action called
# ------------------------------------------------------------------------------
async def test_auto_queue_action(monkeypatch):
    import agents.mcp_agent as mcp

    called = {"count": 0}

    def _queue_action_spy(action):
        called["count"] += 1
        called["last"] = action

    monkeypatch.setattr(mcp, "build_context", _fake_context_ok)
    monkeypatch.setattr(mcp, "planner_agent", _FakePlanner(route="control"))
    monkeypatch.setattr(mcp, "suggest_route", lambda **kw: "control")
    monkeypatch.setitem(mcp.ROUTING_TABLE, "control", lambda **kw: _fake_handler_action(**kw))
    monkeypatch.setitem(mcp.ROUTING_TABLE, "echo", _fake_echo)
    monkeypatch.setattr(mcp, "run_critics", _fake_critics_pass)
    monkeypatch.setattr(mcp.trainer_agent, "ingest_results", _fake_trainer_ingest)
    monkeypatch.setattr(mcp, "queue_action", _queue_action_spy)

    result = await mcp.run_mcp("toggle relay", role="planner", user_id="u8")

    assert called["count"] == 1
    assert called["last"]["type"] == "control"
    assert result["routed_result"]["handled"] is True
