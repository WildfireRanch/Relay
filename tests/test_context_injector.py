# File: test_context_injector.py
# Directory: tests
# Purpose: Validate context builder caps, resilience, and debug metadata.

import importlib
import pytest

@pytest.mark.asyncio
async def test_build_context_debug_includes_sections_and_caps(monkeypatch):
    ctx = importlib.import_module("services.context_injector")

    # Stub loaders to return oversized content so caps are exercised
    monkeypatch.setattr(ctx, "load_summary", lambda *a, **k: "S" * (ctx.MAX_PROJECT_SUMMARY_CHARS + 500))
    monkeypatch.setattr(ctx, "load_global_context", lambda *a, **k: "G" * (ctx.MAX_GLOBAL_CONTEXT_CHARS + 500))
    monkeypatch.setattr(ctx, "load_context", lambda topics, **k: "T" * (ctx.MAX_EXTERNAL_CONTEXT_CHARS + 500))

    # Stub semantic + graph/memory
    monkeypatch.setattr(ctx, "get_semantic_context", lambda q, top_k=6: "SEM" * (ctx.MAX_SEMANTIC_CONTEXT_CHARS // 3 + 1000))
    async def fake_graph(q): return "GRAPH" * (ctx.MAX_GRAPH_MEMORY_CHARS // 5 + 500)
    monkeypatch.setattr(ctx, "summarize_recent_context", fake_graph)
    async def fake_sum(q, r, c): return "MSUM"
    monkeypatch.setattr(ctx, "summarize_memory_entry", fake_sum)

    # Call with debug=True to get full metadata
    out = await ctx.build_context(
        query="what is relay?",
        topics=["alpha", "beta"],
        debug=True,
        memory_entries=[{"question": "q", "response": "r", "context": "c"}],
    )

    # Shape checks
    assert isinstance(out, dict)
    assert "context" in out and isinstance(out["context"], str)
    assert "sections" in out and isinstance(out["sections"], dict)
    sections = out["sections"]

    # Cap checks per section (should not exceed configured limits)
    assert len(sections["summary"]) <= ctx.MAX_PROJECT_SUMMARY_CHARS
    assert len(sections["semantic"]) <= ctx.MAX_SEMANTIC_CONTEXT_CHARS
    assert len(sections["external"]) <= ctx.MAX_EXTERNAL_CONTEXT_CHARS
    assert len(sections["global"]) <= ctx.MAX_GLOBAL_CONTEXT_CHARS
    assert len(sections["graph"]) <= ctx.MAX_GRAPH_MEMORY_CHARS

    # Total cap check
    assert len(out["context"]) <= ctx.MAX_CONTEXT_TOTAL_CHARS

    # files_used present only when debug=True in this implementation
    assert "files_used" in out
