# ──────────────────────────────────────────────────────────────────────────────
# File: context_injector.py
# Directory: services
# Purpose:
#   Aggregate and inject multi-source context for agent queries:
#     - Project summary (docs/PROJECT_SUMMARY.md)
#     - Semantic search (services.semantic_retriever → kb.search), with legacy hybrid hook
#     - External topic files (./context/<topic>.md)
#     - Global context (docs/generated/global_context.md)
#     - Graph-based memory (services.graph.summarize_recent_context)
#     - Recent memory summaries (services.summarize_memory.summarize_memory_entry)
#
# Robustness:
#   - Per-section caps and a hard total ceiling (env tunable)
#   - Safe fallbacks; never raise (callers keep answering)
#   - Debug mode returns full breakdown (sections, files_used, lengths)
#
# Upstream:
#   - services.semantic_retriever.get_semantic_context (canonical path)
#   - services.kb.query_index (optional hybrid path)
#   - services.graph.summarize_recent_context
#   - services.summarize_memory.summarize_memory_entry
#
# Downstream:
#   - agents.mcp_agent (planner/echo consume the composed CONTEXT)
#
# Contents:
#   - build_context(query, files=None, topics=None, debug=False, top_k_semantic=6, memory_entries=None)
#   - helpers: safe_truncate, load_summary, load_global_context, load_context, build_recent_memory_summaries
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from core.logging import log_event
from services.semantic_retriever import get_semantic_context  # canonical semantic search (kb.search → fallback)
from services.kb import query_index                           # legacy search (optional hybrid)
from services.graph import summarize_recent_context           # graph-based memory summaries
from services.summarize_memory import summarize_memory_entry  # memory summarizer

log = logging.getLogger("context_injector")

# === Section limits/config (env-tunable with safe defaults) ===================================

MAX_CONTEXT_TOTAL_CHARS = int(os.getenv("CTX_MAX_TOTAL_CHARS", "12000"))  # hard ceiling

MAX_PROJECT_SUMMARY_CHARS = int(os.getenv("CTX_MAX_PROJECT_SUMMARY", "2000"))
MAX_SEMANTIC_CONTEXT_CHARS = int(os.getenv("CTX_MAX_SEMANTIC", "6000"))
MAX_GRAPH_MEMORY_CHARS = int(os.getenv("CTX_MAX_GRAPH", "1500"))
MAX_EXTERNAL_CONTEXT_CHARS = int(os.getenv("CTX_MAX_EXTERNAL", "1500"))
MAX_GLOBAL_CONTEXT_CHARS = int(os.getenv("CTX_MAX_GLOBAL", "2000"))

PROJECT_SUMMARY_PATH = os.getenv("CTX_PROJECT_SUMMARY_PATH", "./docs/PROJECT_SUMMARY.md")
GLOBAL_CONTEXT_PATH = os.getenv("CTX_GLOBAL_CONTEXT_PATH", "./docs/generated/global_context.md")
TOPIC_BASE_DIR = os.getenv("CTX_TOPIC_BASE_DIR", "./context/")

# === Helpers ==================================================================================

def safe_truncate(text: str, max_chars: int) -> str:
    """Safely truncate text to max_chars, appending an explicit truncation notice with count."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    return f"{cut}\n…[truncated {len(text) - max_chars} chars]"

def load_summary(summary_file: str = PROJECT_SUMMARY_PATH) -> str:
    """Load project summary from disk, truncated to safe length."""
    try:
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                return safe_truncate(f.read(), MAX_PROJECT_SUMMARY_CHARS)
    except Exception as e:
        log.error("Failed to load project summary: %s", e)
        log_event("ctx_summary_error", {"error": str(e), "path": summary_file})
    return "Project summary not available."

def load_global_context(path: str = GLOBAL_CONTEXT_PATH) -> str:
    """Load global project context from disk, truncated to safe length."""
    try:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return safe_truncate(f.read(), MAX_GLOBAL_CONTEXT_CHARS)
    except Exception as e:
        log.error("Failed to load global context: %s", e)
        log_event("ctx_global_error", {"error": str(e), "path": path})
    return "Global project context not available."

def load_context(topics: List[str], base_dir: str = TOPIC_BASE_DIR) -> str:
    """Load per-topic external markdown context files, truncated per file."""
    chunks = []
    for topic in topics:
        try:
            path = Path(base_dir) / f"{topic}.md"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    chunks.append(f"\n# {topic.title()}\n{safe_truncate(content, MAX_EXTERNAL_CONTEXT_CHARS)}")
        except Exception as e:
            log.warning("Failed to load topic %s: %s", topic, e)
            log_event("ctx_topic_error", {"topic": topic, "error": str(e)})
    return "\n".join(chunks) if chunks else "No external context available."

async def build_recent_memory_summaries(entries: List[Dict[str, str]], max_entries: int = 5) -> str:
    """Summarize recent memory entries into concise bullets."""
    if not entries:
        return "No recent memory summaries."
    summaries = []
    for e in entries[-max_entries:]:
        try:
            summary = await summarize_memory_entry(
                e.get("question", ""),
                e.get("response", ""),
                e.get("context", "")
            )
            summaries.append(f"- {summary}")
        except Exception as ex:
            summaries.append(f"- [Summary failed: {str(ex)}]")
            log_event("ctx_memory_summary_error", {"error": str(ex)})
    return "\n".join(summaries)

# === Main Context Builder =====================================================================

async def build_context(
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    debug: bool = False,
    top_k_semantic: int = 6,
    memory_entries: Optional[List[Dict[str, str]]] = None,
) -> Union[str, Dict[str, Any]]:
    """
    Build a multi-layered markdown context block for agent prompts.

    Includes:
      - Project summary
      - Semantic retrieval (via services.semantic_retriever → kb.search)
      - External context (topic .md files)
      - Global context
      - Graph memory (summarized via Neo4j)
      - Recent memory summaries

    Returns:
      - Full markdown string (default)
      - Dict with metadata if debug=True
    """
    files = files or []
    topics = topics or []
    files_used: List[Dict[str, Any]] = []

    # 1) Project Summary
    project_summary = load_summary()
    if "not available" not in project_summary:
        files_used.append({"type": "summary", "source": PROJECT_SUMMARY_PATH})

    # 2) Semantic Retrieval (primary)
    try:
        semantic_context = get_semantic_context(query, top_k=top_k_semantic)
        semantic_context = safe_truncate(semantic_context, MAX_SEMANTIC_CONTEXT_CHARS)
        files_used.append({
            "type": "semantic",
            "desc": f"Semantic retrieval (top-{top_k_semantic}) via kb.search"
        })
    except Exception as e:
        log.exception("Semantic retrieval failed, using fallback: %s", e)
        log_event("ctx_semantic_error", {"error": str(e), "q_head": query[:180]})
        semantic_context = "[Semantic retrieval unavailable]"
        # 2b) Optional legacy hybrid probe — non-fatal, best-effort
        try:
            legacy = query_index(query, k=min(top_k_semantic, 5))  # pragma: no cover (legacy path)
            if legacy:
                semantic_context += "\n\n[Legacy results available]"
                files_used.append({"type": "semantic_legacy", "desc": "services.kb.query_index"})
        except Exception as le:
            log_event("ctx_legacy_search_error", {"error": str(le)})

    # 3) External Topic Context
    external_context = load_context(topics)
    if external_context.strip() and external_context != "No external context available.":
        for topic in topics:
            files_used.append({"type": "external", "source": f"{TOPIC_BASE_DIR.rstrip('/')}/{topic}.md"})

    # 4) Global Context
    global_context = load_global_context()
    if "not available" not in global_context:
        files_used.append({"type": "global", "source": GLOBAL_CONTEXT_PATH})

    # 5) Graph Memory Context
    try:
        graph_context = await summarize_recent_context(query)
        graph_context = safe_truncate(graph_context, MAX_GRAPH_MEMORY_CHARS)
        if graph_context.strip() and "No graph memory matches" not in graph_context:
            files_used.append({"type": "graph", "source": "neo4j"})
    except Exception as ex:
        graph_context = f"[Graph memory error: {str(ex)}]"
        log.error("Graph memory retrieval failed: %s", ex)
        log_event("ctx_graph_error", {"error": str(ex)})

    # 6) Recent Memory Summaries (optional)
    memory_summaries = ""
    if memory_entries:
        try:
            memory_summaries = await build_recent_memory_summaries(memory_entries)
            files_used.append({"type": "memory", "source": "logs/sessions"})
        except Exception as ex:
            memory_summaries = f"[Memory summary error: {str(ex)}]"
            log.error("Memory summarization failed: %s", ex)
            log_event("ctx_memory_error", {"error": str(ex)})

    # Assemble sections in a predictable order
    full_context = f"""
## 🧠 Project Summary:
{project_summary}

## 🦙 Semantic Retrieval (Top Matches):
{semantic_context}

## 🌍 External Project Context:
{external_context}

## 🌐 Global Project Context:
{global_context}

## 🧠 Graph Memory Summary:
{graph_context}

## 📝 Recent Memory Summaries:
{memory_summaries}
""".strip()

    # Enforce total length ceiling (with explicit count)
    if len(full_context) > MAX_CONTEXT_TOTAL_CHARS:
        over = len(full_context) - MAX_CONTEXT_TOTAL_CHARS
        log.warning("[CTX] Full context exceeded %d chars by %d → truncated", MAX_CONTEXT_TOTAL_CHARS, over)
        log_event("ctx_truncated_total", {"limit": MAX_CONTEXT_TOTAL_CHARS, "over_by": over})
        full_context = safe_truncate(full_context, MAX_CONTEXT_TOTAL_CHARS)

    # Structured log for observability
    log_event(
        "ctx_built",
        {
            "len": len(full_context),
            "files_used": len(files_used),
            "sections": {
                "summary": min(len(project_summary), MAX_PROJECT_SUMMARY_CHARS),
                "semantic": min(len(semantic_context), MAX_SEMANTIC_CONTEXT_CHARS),
                "external": min(len(external_context), MAX_EXTERNAL_CONTEXT_CHARS),
                "global": min(len(global_context), MAX_GLOBAL_CONTEXT_CHARS),
                "graph": min(len(graph_context), MAX_GRAPH_MEMORY_CHARS),
                "memory": len(memory_summaries),
            },
        },
    )

    if debug:
        return {
            "context": full_context,
            "length": len(full_context),
            "files_used": files_used,
            "sections": {
                "summary": project_summary,
                "semantic": semantic_context,
                "external": external_context,
                "global": global_context,
                "graph": graph_context,
                "memory_summaries": memory_summaries,
            },
        }

    return full_context
