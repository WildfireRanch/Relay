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
#   - No placeholder leakage (empty sections are omitted)
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

# Gate graph usage until Neo4j is fully wired
ENABLE_GRAPH = os.getenv("CTX_ENABLE_GRAPH", "1").strip().lower() in {"1", "true", "yes"}

# === Helpers ==================================================================================

def safe_truncate(text: str, max_chars: int) -> str:
    """Safely truncate text to max_chars, appending an explicit truncation notice with count."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    return f"{cut}\n…[truncated {len(text) - max_chars} chars]"

def _read_text_if_exists(path: str, max_chars: int) -> str:
    """Read a UTF-8 file if it exists; return truncated content, else empty string."""
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            return safe_truncate(p.read_text(encoding="utf-8"), max_chars)
    except Exception as e:
        log.error("Failed to read %s: %s", path, e)
    return ""

def load_summary(summary_file: str = PROJECT_SUMMARY_PATH) -> str:
    """Load project summary from disk, truncated to safe length. Empty string if missing."""
    text = _read_text_if_exists(summary_file, MAX_PROJECT_SUMMARY_CHARS)
    if not text:
        # Log once for observability; do not leak placeholders into prompts.
        log_event("ctx_summary_missing", {"path": summary_file})
    return text

def load_global_context(path: str = GLOBAL_CONTEXT_PATH) -> str:
    """Load global project context from disk, truncated to safe length. Empty string if missing."""
    text = _read_text_if_exists(path, MAX_GLOBAL_CONTEXT_CHARS)
    if not text:
        log_event("ctx_global_missing", {"path": path})
    return text

def load_context(topics: List[str], base_dir: str = TOPIC_BASE_DIR) -> str:
    """Load per-topic external markdown context files, truncated per file. Empty if none found."""
    chunks: List[str] = []
    for topic in topics:
        try:
            path = Path(base_dir) / f"{topic}.md"
            if path.exists() and path.is_file():
                content = safe_truncate(path.read_text(encoding="utf-8"), MAX_EXTERNAL_CONTEXT_CHARS)
                if content.strip():
                    # Keep headings minimal; avoid markdown noise if empty.
                    chunks.append(f"# {topic.title()}\n{content}")
            else:
                log_event("ctx_topic_missing", {"topic": topic, "path": str(path)})
        except Exception as e:
            log.warning("Failed to load topic %s: %s", topic, e)
            log_event("ctx_topic_error", {"topic": topic, "error": str(e)})
    return "\n\n".join(chunks).strip()

async def build_recent_memory_summaries(entries: List[Dict[str, str]], max_entries: int = 5) -> str:
    """Summarize recent memory entries into concise bullets. Empty string if none."""
    if not entries:
        return ""
    summaries: List[str] = []
    for e in entries[-max_entries:]:
        try:
            summary = await summarize_memory_entry(
                e.get("question", ""),
                e.get("response", ""),
                e.get("context", "")
            )
            if summary:
                summaries.append(f"- {summary}")
        except Exception as ex:
            summaries.append(f"- [Summary failed: {str(ex)}]")
            log_event("ctx_memory_summary_error", {"error": str(ex)})
    return "\n".join(summaries).strip()

def _section_block(title: str, body: str) -> str:
    """Render a section only if body is non-empty."""
    body = (body or "").strip()
    if not body:
        return ""
    return f"## {title}\n{body}"

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
      - Project summary (no placeholder leakage)
      - Semantic retrieval (via services.semantic_retriever → kb.search)
      - External context (topic .md files)
      - Global context
      - Graph memory (guarded by CTX_ENABLE_GRAPH)
      - Recent memory summaries

    Returns:
      - Full markdown string (default)
      - Dict with metadata if debug=True
    """
    files = files or []
    topics = topics or []
    files_used: List[Dict[str, Any]] = []

    # 1) Project Summary (omit if missing)
    project_summary = load_summary()
    if project_summary.strip():
        files_used.append({"type": "summary", "source": PROJECT_SUMMARY_PATH})

    # 2) Semantic Retrieval (primary)
    semantic_context = ""
    try:
        sc = get_semantic_context(query, top_k=top_k_semantic)  # returns markdown bullets
        semantic_context = safe_truncate(sc, MAX_SEMANTIC_CONTEXT_CHARS)
        if semantic_context.strip():
            files_used.append({
                "type": "semantic",
                "desc": f"Semantic retrieval (top-{top_k_semantic}) via kb.search",
            })
    except Exception as e:
        # Don’t inject “[Semantic unavailable]” into prompts; just log + try legacy best-effort.
        log.exception("Semantic retrieval failed; attempting legacy fallback: %s", e)
        log_event("ctx_semantic_error", {"error": str(e), "q_head": query[:180]})
        try:
            legacy = query_index(query, k=min(top_k_semantic, 5))  # optional hybrid
            if legacy:
                semantic_context = safe_truncate(legacy, MAX_SEMANTIC_CONTEXT_CHARS)
                files_used.append({"type": "semantic_legacy", "desc": "services.kb.query_index"})
        except Exception as le:
            log_event("ctx_legacy_search_error", {"error": str(le)})

    # 3) External Topic Context (omit if none)
    external_context = load_context(topics)
    if external_context:
        for topic in topics:
            path = f"{TOPIC_BASE_DIR.rstrip('/')}/{topic}.md"
            if Path(path).exists():
                files_used.append({"type": "external", "source": path})

    # 4) Global Context (omit if missing)
    global_context = load_global_context()
    if global_context.strip():
        files_used.append({"type": "global", "source": GLOBAL_CONTEXT_PATH})

    # 5) Graph Memory Context (guarded + omit if empty)
    graph_context = ""
    if ENABLE_GRAPH:
        try:
            gc = await summarize_recent_context(query)
            graph_context = safe_truncate(gc, MAX_GRAPH_MEMORY_CHARS).strip()
            if graph_context and "No graph memory matches" not in graph_context:
                files_used.append({"type": "graph", "source": "neo4j"})
            else:
                graph_context = ""
        except Exception as ex:
            # Silent in prompt; log for ops
            log.error("Graph memory retrieval failed: %s", ex)
            log_event("ctx_graph_error", {"error": str(ex)})
            graph_context = ""
    else:
        # Don’t inject “[disabled]”; keep prompt clean.
        log_event("ctx_graph_disabled", {})

    # 6) Recent Memory Summaries (optional; omit if empty)
    memory_summaries = ""
    if memory_entries:
        try:
            memory_summaries = await build_recent_memory_summaries(memory_entries)
            if memory_summaries:
                files_used.append({"type": "memory", "source": "logs/sessions"})
        except Exception as ex:
            log.error("Memory summarization failed: %s", ex)
            log_event("ctx_memory_error", {"error": str(ex)})
            memory_summaries = ""

    # Assemble sections only when non-empty
    sections_rendered: List[str] = []
    sec_summary = _section_block("🧠 Project Summary:", project_summary)
    if sec_summary: sections_rendered.append(sec_summary)

    sec_semantic = _section_block("🦙 Semantic Retrieval (Top Matches):", semantic_context)
    if sec_semantic: sections_rendered.append(sec_semantic)

    sec_external = _section_block("🌍 External Project Context:", external_context)
    if sec_external: sections_rendered.append(sec_external)

    sec_global = _section_block("🌐 Global Project Context:", global_context)
    if sec_global: sections_rendered.append(sec_global)

    sec_graph = _section_block("🧠 Graph Memory Summary:", graph_context)
    if sec_graph: sections_rendered.append(sec_graph)

    sec_memory = _section_block("📝 Recent Memory Summaries:", memory_summaries)
    if sec_memory: sections_rendered.append(sec_memory)

    full_context = "\n\n".join(sections_rendered).strip()

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
