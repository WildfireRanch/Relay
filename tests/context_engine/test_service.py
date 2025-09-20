# ──────────────────────────────────────────────────────────────────────────────
# File: tests/context_engine/test_service.py
# Purpose: Unit coverage for the pure context engine service.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import pytest

from core.context_engine import (
    ContextRequest,
    EngineConfig,
    RetrievalTier,
    TierConfig,
    build_context,
)
from core.context_engine import ContextEngine
from core.context_engine import Retriever as BaseRetriever


class StubRetriever(BaseRetriever):
    """Minimal retriever used in tests; returns canned tuples."""

    def __init__(self, results, *, raises: bool = False):
        self._results = results
        self._raises = raises

    def search(self, query: str, k: int):  # type: ignore[override]
        if self._raises:
            raise RuntimeError("boom")
        return list(self._results)[:k]


def test_build_context_minimal_round_trip():
    retriever = StubRetriever([("alpha.md", 0.2, "Alpha snippet")])
    cfg = EngineConfig(
        retrievers={RetrievalTier.GLOBAL: retriever},
        max_context_tokens=256,
    )
    result = build_context(ContextRequest(query="hello"), cfg)

    assert result["files_used"] == ["alpha.md"]
    assert result["meta"]["kb"]["hits"] == 1
    assert pytest.approx(1.0) == result["matches"][0]["score"]
    assert "Alpha snippet" in result["context"]


def test_build_context_merges_tiers_and_prefers_best_score():
    global_retriever = StubRetriever([
        ("alpha.md", 0.1, "Global alpha"),
        ("shared.md", 0.2, "Global shared"),
    ])
    project_retriever = StubRetriever([
        ("shared.md", 0.9, "Project shared"),
        ("beta.md", 0.4, "Project beta"),
    ])
    cfg = EngineConfig(
        retrievers={
            RetrievalTier.GLOBAL: global_retriever,
            RetrievalTier.PROJECT_DOCS: project_retriever,
        },
        tier_overrides={
            RetrievalTier.GLOBAL: TierConfig(top_k=2, min_score=0.0),
            RetrievalTier.PROJECT_DOCS: TierConfig(top_k=2, min_score=0.0),
        },
        default_tier=TierConfig(top_k=1, min_score=0.0),
        max_context_tokens=512,
    )

    result = ContextEngine(config=cfg).build(ContextRequest(query="test"))
    paths = [m["path"] for m in result["matches"]]

    assert paths[0] == "shared.md"  # highest score survives dedupe
    assert "alpha.md" in paths and "beta.md" in paths
    assert result["meta"]["kb"]["hits"] == len(result["matches"])
    assert result["files_used"] and all(path in paths for path in result["files_used"])


def test_invalid_configuration_raises():
    with pytest.raises(ValueError):
        EngineConfig(retrievers={}, max_context_tokens=0)
    with pytest.raises(ValueError):
        TierConfig(top_k=0)
    with pytest.raises(ValueError):
        ContextRequest(query="x", max_tokens=0)


def test_token_budget_limits_context():
    snippets = [
        ("first.md", 1.0, "First" + " x" * 40),
        ("second.md", 0.5, "Second"),
    ]
    retriever = StubRetriever(snippets)

    def char_counter(text: str) -> int:
        return len(text)

    cfg = EngineConfig(
        retrievers={RetrievalTier.GLOBAL: retriever},
        tier_overrides={RetrievalTier.GLOBAL: TierConfig(top_k=2, min_score=0.0)},
        default_tier=TierConfig(top_k=1, min_score=0.0),
        max_context_tokens=20,
        token_counter=char_counter,
    )

    result = build_context(ContextRequest(query="q"), cfg)

    assert result["files_used"] == ["first.md"]  # budget excludes second
    assert "Second" not in result["context"]


def test_sanitizes_invalid_results_gracefully():
    retriever = StubRetriever([
        ("   ", 0.3, "bad path"),
        ("valid.md", "not-a-float", "bad score"),
    ])
    cfg = EngineConfig(
        retrievers={RetrievalTier.GLOBAL: retriever},
        tier_overrides={RetrievalTier.GLOBAL: TierConfig(top_k=2, min_score=0.0)},
        default_tier=TierConfig(top_k=1, min_score=0.0),
        max_context_tokens=50,
    )

    result = build_context(ContextRequest(query="q"), cfg)

    assert result["matches"] == []
    assert result["context"] == ""
    assert result["meta"]["kb"] == {"hits": 0, "max_score": 0.0, "sources": []}
