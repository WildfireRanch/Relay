from __future__ import annotations

import asyncio

import pytest


def _context_payload():
    return {
        "context": "• **README.md** — score: 0.95",
        "files_used": [{"path": "README.md"}],
        "kb": {"hits": 1, "max_score": 0.95, "sources": ["README.md"]},
        "grounding": [{"path": "README.md", "score": 0.95}],
    }


def test_ask_post_success(monkeypatch, test_app):
    async def fake_context(query: str, corr_id: str):
        return _context_payload()

    async def fake_run_mcp(**_: object):
        return {
            "plan": {"route": "echo"},
            "routed_result": {"response": "Hello from MCP", "route": "echo"},
            "critics": [],
            "context": "",
            "files_used": [],
            "meta": {},
            "final_text": "Hello from MCP",
        }

    monkeypatch.setattr("routes.ask._build_context_safe", fake_context)
    import agents.mcp_agent as mcp

    monkeypatch.setattr(mcp, "run_mcp", fake_run_mcp, raising=True)

    resp = test_app.post("/ask", json={"question": "What is Relay?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_text"] == "Hello from MCP"
    assert body["meta"]["no_answer"] is False


def test_ask_post_invalid_files(test_app):
    resp = test_app.post("/ask", json={"question": "What is Relay?", "files": ["", "notes.md"]})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_files"
    assert detail["corr_id"]


def test_ask_post_timeout_returns_408(monkeypatch, test_app):
    async def fake_context(query: str, corr_id: str):
        return _context_payload()

    async def fake_wait(*args: object, **kwargs: object):
        raise asyncio.TimeoutError

    monkeypatch.setattr("routes.ask._build_context_safe", fake_context)
    monkeypatch.setattr("routes.ask._maybe_await", fake_wait)

    resp = test_app.post("/ask", json={"question": "What is Relay?"})
    assert resp.status_code == 408
    detail = resp.json()["detail"]
    assert detail["code"] == "ask_timeout"
    assert detail["corr_id"]


def test_ask_post_agent_exception_returns_500(monkeypatch, test_app):
    async def fake_context(query: str, corr_id: str):
        return _context_payload()

    async def fake_wait(*args: object, **kwargs: object):
        raise RuntimeError("boom")

    monkeypatch.setattr("routes.ask._build_context_safe", fake_context)
    monkeypatch.setattr("routes.ask._maybe_await", fake_wait)

    resp = test_app.post("/ask", json={"question": "What is Relay?"})
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail["code"] == "mcp_failed"
    assert detail["corr_id"]
