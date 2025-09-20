import pytest


def test_planner_plan_tolerates_unknown_kwargs(monkeypatch):
    from agents import planner_agent

    captured = {}

    def record(event, data=None):
        captured.setdefault(event, []).append(data or {})

    monkeypatch.setattr(planner_agent, "log_event", record, raising=True)

    result = planner_agent.plan(query="What is Relay?", corr_id="cid-1", extra_flag=True)

    assert result["route"] == "echo"
    assert any(entry.get("corr_id") == "cid-1" for entry in captured.get("planner_error", [])) is False


def test_planner_logs_corr_id_on_exception(monkeypatch):
    from agents import planner_agent

    logs = []

    def record(event, data=None):
        logs.append((event, data or {}))

    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(planner_agent, "log_event", record, raising=True)
    monkeypatch.setattr(planner_agent, "_looks_definitional", boom, raising=True)

    fallback = planner_agent.plan(query="broken", corr_id="cid-err")

    assert fallback["route"] == "echo"
    assert any(data.get("corr_id") == "cid-err" for _, data in logs)


@pytest.mark.asyncio
async def test_run_mcp_handles_extras_and_non_dict_plan(monkeypatch):
    from agents import mcp_agent

    events = []

    def record(event, data=None):
        events.append((event, data or {}))

    def fake_plan(*, query, files, topics, debug, corr_id):
        assert query == "hello"
        assert isinstance(files, list)
        assert isinstance(topics, list)
        assert isinstance(debug, bool)
        assert isinstance(corr_id, str)
        return "not-a-dict"

    def fake_context(*, query, debug, corr_id):
        assert query == "hello"
        return {"context": "", "files_used": [], "matches": []}

    def fake_dispatch(*, route, query, context, user_id, debug, corr_id):
        assert route == "echo"
        assert query == "hello"
        assert user_id == "tester"
        return "ok"

    monkeypatch.setattr(mcp_agent, "log_event", record, raising=True)
    monkeypatch.setattr(mcp_agent, "_plan", fake_plan, raising=True)
    monkeypatch.setattr(mcp_agent, "_build_context", fake_context, raising=True)
    monkeypatch.setattr(mcp_agent, "_dispatch", fake_dispatch, raising=True)

    result = await mcp_agent.run_mcp(
        query="hello",
        role="planner",
        user_id="tester",
        corr_id="cid-123",
        unexpected_kw="ignored",
    )

    assert result["plan"] == {}
    assert result["routed_result"]["response"] == "ok"
    assert result["routed_result"]["route"] == "echo"

    assert all(data.get("corr_id") == "cid-123" for _, data in events if data)
