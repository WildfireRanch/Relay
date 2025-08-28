# ──────────────────────────────────────────────────────────────────────────────
# File: services/context_injector.py
# Purpose:
#   Aggregate and inject multi-source context for agent queries:
#     - Project summary
#     - Semantic search (via services.semantic_retriever → kb.search)
#     - External topic files
#     - Global context
#     - Graph-based memory
#     - Recent memory summaries
#
# Robustness features:
#   - Always truncates sections to prevent prompt blow-up
#   - Safe fallbacks when files or services are missing
#   - Debug mode returns full metadata for auditing
#
# Upstream:
#   - services.semantic_retriever.get_semantic_context (canonical search path)
#   - services.kb.query_index (optional hybrid)
#   - services.graph.summarize_recent_context
#   - services.summarize_memory.summarize_memory_entry
#
# Downstream:
#   - agents.mcp_agent
#   - services.context_engine
# ──────────────────────────────────────────────────────────────────────────────

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Union

from services.semantic_retriever import get_semantic_context  # canonical search (kb.search → fallback)
from services.kb import query_index                           # legacy search (optional hybrid)
from services.graph import summarize_recent_context           # graph-based memory summaries
from services.summarize_memory import summarize_memory_entry  # memory summarizer

log = logging.getLogger("context_injector")

# === Section limits/config ===
MAX_PROJECT_SUMMARY_CHARS = 2000
MAX_SEMANTIC_CONTEXT_CHARS = 6000
MAX_GRAPH_MEMORY_CHARS = 1500
MAX_EXTERNAL_CONTEXT_CHARS = 1500
MAX_GLOBAL_CONTEXT_CHARS = 2000
MAX_CONTEXT_TOTAL_CHARS = 12000  # hard ceiling for assembled context

# ─── Helpers ────────────────────────────────────────────────────────────────

def safe_truncate(text: str, max_chars: int) -> str:
    """Safely truncate text to max_chars, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"

# ─── Loaders ────────────────────────────────────────────────────────────────

def load_summary(summary_file: str = "./docs/PROJECT_SUMMARY.md") -> str:
    """Load project summary from disk, truncated to safe length."""
    try:
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                return safe_truncate(f.read(), MAX_PROJECT_SUMMARY_CHARS)
    except Exception as e:
        log.error("Failed to load project summary: %s", e)
    return "Project summary not available."

def load_global_context(path: str = "./docs/generated/global_context.md") -> str:
    """Load global project context from disk, truncated to safe length."""
    try:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return safe_truncate(f.read(), MAX_GLOBAL_CONTEXT_CHARS)
    except Exception as e:
        log.error("Failed to load global context: %s", e)
    return "Global project context not available."

def load_context(topics: List[str], base_dir: str = "./context/") -> str:
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
    return "\n".join(chunks) if chunks else "No external context available."

# ─── Memory Summaries ───────────────────────────────────────────────────────

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
    return "\n".join(summaries)

# ─── Main Context Builder ───────────────────────────────────────────────────

async def build_context(
    query: str,
    files: List[str] = None,
    topics: List[str] = None,
    debug: bool = False,
    top_k_semantic: int = 6,
    memory_entries: List[Dict[str, str]] = None,
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
    files_used: List[Dict[str, Any]] = []
    topics = topics or []

    # === 1. Project Summary ===
    project_summary = load_summary()
    if "not available" not in project_summary:
        files_used.append({"type": "summary", "source": "docs/PROJECT_SUMMARY.md"})

    # === 2. Semantic Retrieval ===
    try:
        semantic_context = get_semantic_context(query, top_k=top_k_semantic)
        semantic_context = safe_truncate(semantic_context, MAX_SEMANTIC_CONTEXT_CHARS)
        files_used.append({
            "type": "semantic",
            "desc": f"Semantic retrieval (top-{top_k_semantic}) via kb.search"
        })
    except Exception as e:
        log.exception("Semantic retrieval failed, using fallback: %s", e)
        semantic_context = "[Semantic retrieval unavailable]"

    # === 3. External Topic Context ===
    external_context = load_context(topics)
    if external_context.strip() and external_context != "No external context available.":
        for topic in topics:
            files_used.append({"type": "external", "source": f"context/{topic}.md"})

    # === 4. Global Context ===
    global_context = load_global_context()
    if "not available" not in global_context:
        files_used.append({"type": "global", "source": "docs/generated/global_context.md"})

    # === 5. Graph Memory Context ===
    try:
        graph_context = await summarize_recent_context(query)
        graph_context = safe_truncate(graph_context, MAX_GRAPH_MEMORY_CHARS)
        if graph_context.strip() and "No graph memory matches" not in graph_context:
            files_used.append({"type": "graph", "source": "neo4j"})
    except Exception as ex:
        graph_context = f"[Graph memory error: {str(ex)}]"
        log.error("Graph memory retrieval failed: %s", ex)

    # === 6. Recent Memory Summaries ===
    memory_summaries = ""
    if memory_entries:
        try:
            memory_summaries = await build_recent_memory_summaries(memory_entries)
            files_used.append({"type": "memory", "source": "logs/sessions"})
        except Exception as ex:
            memory_summaries = f"[Memory summary error: {str(ex)}]"
            log.error("Memory summarization failed: %s", ex)

    # === Assemble context ===
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

    # === Enforce total length ceiling ===
    if len(full_context) > MAX_CONTEXT_TOTAL_CHARS:
        log.warning("[CTX] Full context exceeded %d chars → truncated", MAX_CONTEXT_TOTAL_CHARS)
        full_context = safe_truncate(full_context, MAX_CONTEXT_TOTAL_CHARS)

    log.info("[CTX] Built context | len=%d chars | files_used=%d", len(full_context), len(files_used))

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
            }
        }

    return full_context
