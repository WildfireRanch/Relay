# File: test_semantic_retriever.py
# Directory: tests
# Purpose: Validate semantic retriever wrapper (k vs. top_k) and markdown rendering.
#
# Upstream:
#   - ENV: SEMANTIC_DEFAULT_K (optional)
#   - Imports: importlib, pytest
#
# Downstream:
#   - services.context_injector, agents.echo_agent
#
# Contents:
#   - test_semantic_wrapper_k_vs_topk()
#   - test_semantic_markdown_render()

import importlib
import pytest

def test_semantic_wrapper_k_vs_topk(monkeypatch):
    sem = importlib.import_module("services.semantic_retriever")

    called = {"k": None}
    def fake_kb_search(q, k=6, **kw):
        called["k"] = k
        return [{"title": "A", "path": "a.md", "tier": "t1", "score": 0.9, "snippet": "sample"}]

    kb = importlib.import_module("services.kb")
    monkeypatch.setattr(kb, "search", fake_kb_search, raising=True)

    # Case 1: explicit k
    _ = sem.search("query", k=3)
    assert called["k"] == 3

    # Case 2: top_k overrides
    _ = sem.search("query", top_k=7)
    assert called["k"] == 7

    # Case 3: default
    _ = sem.search("query")
    assert called["k"] == sem.DEFAULT_K

def test_semantic_markdown_render():
    sem = importlib.import_module("services.semantic_retriever")
    results = [{
        "title": "Relay Overview",
        "path": "docs/relay.md",
        "tier": "global",
        "score": 0.87,
        "snippet": "Relay Command Center overview..."
    }]
    md = sem.render_markdown(results)
    # Should contain bold title, italic path, and snippet
    assert "**Relay Overview**" in md
    assert "_docs/relay.md_" in md
    assert "overview" in md.lower()
