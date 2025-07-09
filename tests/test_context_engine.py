# File: test_context_engine.py
# Directory: tests
# Purpose: # Purpose: Provides unit tests for the context engine functionality, ensuring it integrates correctly with search components and handles environmental changes.
#
# Upstream:
#   - ENV: —
#   - Imports: pathlib, pytest, services, sys, types
#
# Downstream:
#   - —
#
# Contents:
#   - ctx()
#   - fake_search()
#   - stub_search()
#   - test_build_context_passes_threshold()
#   - test_context_build_includes_search_snippet()
#   - test_env_root_change_clears_cache()







import types
import sys
from pathlib import Path

import pytest

# Stub services.kb before importing context_engine
kb_stub = types.ModuleType("services.kb")
def stub_search(query, user_id=None, k=4, score_threshold=None):
    return [
        {
            "path": "doc.md",
            "snippet": "snippet",
            "tier": "global",
            "title": "doc.md",
        }
    ]

kb_stub.search = stub_search
kb_stub.get_recent_summaries = lambda user_id: "summary"
kb_stub.api_reindex = lambda: {"status": "ok"}
sys.modules.setdefault("services.kb", kb_stub)

from services import context_engine as ce_module


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(ce_module, "kb", kb_stub)
    ce_module.ContextEngine.clear_cache()
    # create global context file
    gen = tmp_path / "docs" / "generated"
    gen.mkdir(parents=True)
    (gen / "global_context.md").write_text("GLOBAL CONTEXT")
    # also create generic logs summary
    (gen / "relay_context.md").write_text("LOGS")
    return ce_module.ContextEngine(user_id="u", base=tmp_path)


def test_context_build_includes_search_snippet(ctx):
    result = ctx.build_context("tell me something")
    assert "snippet" in result


def test_build_context_passes_threshold(ctx, monkeypatch):
    called = {}

    def fake_search(query, user_id=None, k=4, score_threshold=None):
        called["threshold"] = score_threshold
        return [
            {
                "path": "doc.md",
                "snippet": "snippet",
                "tier": "global",
                "title": "doc.md",
            }
        ]

    monkeypatch.setattr(kb_stub, "search", fake_search)
    ctx.build_context("test", score_threshold=0.5)
    assert called["threshold"] == 0.5


def test_env_root_change_clears_cache(tmp_path, monkeypatch):
    ce_module.ContextEngine.clear_cache()
    monkeypatch.setattr(ce_module, "kb", kb_stub)

    base1 = tmp_path / "p1"
    (base1 / "docs").mkdir(parents=True)
    (base1 / "docs" / "a.md").write_text("A")

    ctx1 = ce_module.ContextEngine(user_id="u", base=base1)
    assert "A" in ctx1.read_docs()
    # Modify file but cached result should remain the same
    (base1 / "docs" / "a.md").write_text("A2")
    assert "A" in ctx1.read_docs()

    base2 = tmp_path / "p2"
    (base2 / "docs").mkdir(parents=True)
    (base2 / "docs" / "b.md").write_text("B")
    monkeypatch.setenv("RELAY_PROJECT_ROOT", str(base2))

    ctx2 = ce_module.ContextEngine(user_id="u")
    content = ctx2.read_docs()
    assert "B" in content
    assert "A" not in content
