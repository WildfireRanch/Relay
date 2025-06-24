import types
import sys
from pathlib import Path

import pytest

# Stub services.kb before importing context_engine
kb_stub = types.ModuleType("services.kb")
kb_stub.search = lambda query, user_id=None, k=4: [
    {
        "path": "doc.md",
        "snippet": "snippet",
        "tier": "global",
        "title": "doc.md",
    }
]
kb_stub.get_recent_summaries = lambda user_id: "summary"
kb_stub.api_reindex = lambda: {"status": "ok"}
sys.modules.setdefault("services.kb", kb_stub)

from services import context_engine as ce_module


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(ce_module, "kb", kb_stub)
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
