# ──────────────────────────────────────────────────────────────────────────────
# File: tests/test_context_injector.py
# Purpose:
#   Unit tests for services/context_injector.py
#   - Verify build_context assembles all sections
#   - Ensure truncation works
#   - Ensure robust fallback behavior on errors
#
# Dependencies:
#   pip install pytest pytest-asyncio
#
# Notes:
#   - Uses unittest.mock to patch external services.
#   - Tests both normal and debug modes.
# ──────────────────────────────────────────────────────────────────────────────

import pytest
import asyncio
from unittest.mock import patch

import services.context_injector as ci


@pytest.mark.asyncio
async def test_build_context_happy_path(tmp_path):
    """Context builder should return all sections populated in normal operation."""

    # Patch dependencies to return predictable strings
    with patch("services.context_injector.get_semantic_context", return_value="semantic match 1\nsemantic match 2"), \
         patch("services.context_injector.summarize_recent_context", return_value="graph memory summary"), \
         patch("services.context_injector.summarize_memory_entry", return_value="summarized entry"):

        context = await ci.build_context(
            query="test query",
            topics=["alpha", "beta"],
            memory_entries=[{"question": "Q?", "response": "R!", "context": "C"}]
        )

        assert "🧠 Project Summary" in context
        assert "🦙 Semantic Retrieval" in context
        assert "🌍 External Project Context" in context
        assert "🌐 Global Project Context" in context
        assert "🧠 Graph Memory Summary" in context
        assert "📝 Recent Memory Summaries" in context


@pytest.mark.asyncio
async def test_build_context_debug_mode():
    """Debug mode should return dict with metadata and section breakdown."""

    with patch("services.context_injector.get_semantic_context", return_value="debug semantic"), \
         patch("services.context_injector.summarize_recent_context", return_value="debug graph"), \
         patch("services.context_injector.summarize_memory_entry", return_value="debug memory"):

        result = await ci.build_context(
            query="debug query",
            debug=True,
            memory_entries=[{"question": "Q?", "response": "R!", "context": "C"}]
        )

        assert isinstance(result, dict)
        assert "context" in result
        assert "files_used" in result
        assert "sections" in result
        assert "semantic" in result["sections"]
        assert "graph" in result["sections"]
        assert "memory_summaries" in result["sections"]


@pytest.mark.asyncio
async def test_semantic_failure_fallback():
    """If get_semantic_context raises, fallback should insert placeholder."""

    with patch("services.context_injector.get_semantic_context", side_effect=Exception("boom")), \
         patch("services.context_injector.summarize_recent_context", return_value="graph OK"), \
         patch("services.context_injector.summarize_memory_entry", return_value="memory OK"):

        context = await ci.build_context(query="fail semantic")

        assert "[Semantic retrieval unavailable]" in context


@pytest.mark.asyncio
async def test_graph_failure_fallback():
    """If graph summarization fails, fallback should insert error marker."""

    with patch("services.context_injector.get_semantic_context", return_value="semantic OK"), \
         patch("services.context_injector.summarize_recent_context", side_effect=Exception("graph boom")), \
         patch("services.context_injector.summarize_memory_entry", return_value="memory OK"):

        context = await ci.build_context(query="fail graph")

        assert "[Graph memory error" in context


@pytest.mark.asyncio
async def test_memory_failure_fallback():
    """If memory summarization fails, fallback should insert error marker."""

    with patch("services.context_injector.get_semantic_context", return_value="semantic OK"), \
         patch("services.context_injector.summarize_recent_context", return_value="graph OK"), \
         patch("services.context_injector.summarize_memory_entry", side_effect=Exception("mem boom")):

        context = await ci.build_context(
            query="fail memory",
            memory_entries=[{"question": "Q?", "response": "R!", "context": "C"}]
        )

        assert "[Memory summary error" in context


def test_safe_truncate():
    """safe_truncate should truncate long text and append ellipsis marker."""
    text = "x" * 100
    truncated = ci.safe_truncate(text, 20)
    assert len(truncated) <= 24  # includes ellipsis
    assert truncated.endswith("...[truncated]")
