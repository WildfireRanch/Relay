# ──────────────────────────────────────────────────────────────────────────────
# File: context_injector.py
# Directory: services
# Purpose: # Purpose: Manages the aggregation and injection of contextual data from various services into the application's processing flow.
#
# Upstream:
#   - ENV: —
#   - Imports: os, pathlib, services.graph, services.kb, services.semantic_retriever, services.summarize_memory, typing
#
# Downstream:
#   - agents.mcp_agent
#   - services.context_engine
#
# Contents:
#   - build_context()
#   - build_recent_memory_summaries()
#   - load_context()
#   - load_global_context()
#   - load_summary()
#   - safe_truncate()
# ──────────────────────────────────────────────────────────────────────────────


import os
from pathlib import Path
from typing import List, Dict, Any, Union

from services.semantic_retriever import get_semantic_context      # LlamaIndex semantic search
from services.kb import query_index                              # Legacy KB (for optional hybrid)
from services.graph import summarize_recent_context              # Graph-based memory (optional)
from services.summarize_memory import summarize_memory_entry     # For summarizing recent memory, optional

# === Section limits/config ===
MAX_PROJECT_SUMMARY_CHARS = 2000
MAX_SEMANTIC_CONTEXT_CHARS = 6000
MAX_GRAPH_MEMORY_CHARS = 1500
MAX_EXTERNAL_CONTEXT_CHARS = 1500
MAX_GLOBAL_CONTEXT_CHARS = 2000

def safe_truncate(text: str, max_chars: int) -> str:
    """Truncates text safely, appends ellipsis if needed."""
    if not text: return ""
    if len(text) <= max_chars: return text
    return text[:max_chars] + "\n...[truncated]"

# === Load Project Summary ===
def load_summary(summary_file: str = "./docs/PROJECT_SUMMARY.md") -> str:
    """Loads and safely truncates the project summary file."""
    if os.path.exists(summary_file):
        with open(summary_file, "r", encoding="utf-8") as f:
            return safe_truncate(f.read(), MAX_PROJECT_SUMMARY_CHARS)
    return "Project summary not available."

# === Load Global Context ===
def load_global_context(path: str = "./docs/generated/global_context.md") -> str:
    """Loads and safely truncates global project context file."""
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            return safe_truncate(f.read(), MAX_GLOBAL_CONTEXT_CHARS)
    return "Global project context not available."

# === Load Markdown snippets from /context/<topic>.md files ===
def load_context(topics: List[str], base_dir: str = "./context/") -> str:
    """Loads and concatenates markdown for each requested topic."""
    chunks = []
    for topic in topics:
        path = Path(base_dir) / f"{topic}.md"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                chunks.append(f"\n# {topic.title()}\n{safe_truncate(content, MAX_EXTERNAL_CONTEXT_CHARS)}")
    return "\n".join(chunks) if chunks else "No external context available."

# === Recent Memory Summaries (optional, using your summarizer) ===
async def build_recent_memory_summaries(entries: List[Dict[str, str]], max_entries: int = 5) -> str:
    """Summarizes recent user/agent memory entries."""
    if not entries: return "No recent memory summaries."
    summaries = []
    for e in entries[-max_entries:]:
        try:
            summary = await summarize_memory_entry(e.get("question", ""), e.get("response", ""), e.get("context", ""))
            summaries.append(f"- {summary}")
        except Exception as ex:
            summaries.append(f"- [Summary failed: {str(ex)}]")
    return "\n".join(summaries)

# === MAIN CONTEXT BUILDER ===
async def build_context(
    query: str,
    files: List[str] = [],
    topics: List[str] = [],
    debug: bool = False,
    top_k_semantic: int = 6,
    memory_entries: List[Dict[str, str]] = None,  # Optionally pass recent memory
) -> Union[str, Dict[str, Any]]:
    """
    Builds a multi-layered markdown context block for agent prompts:
      - Project summary
      - LlamaIndex-powered semantic retrieval (best chunks from code/docs)
      - External project context (topics)
      - Global context
      - (Optionally) summarized graph memory
      - (Optionally) recent memory summaries

    Returns full context string, or dict with metadata if debug=True.
    """
    files_used: List[Dict[str, Any]] = []

    # === 1. Project Summary ===
    project_summary = load_summary()
    if "not available" not in project_summary:
        files_used.append({"type": "summary", "source": "docs/PROJECT_SUMMARY.md"})

    # === 2. Semantic Retrieval (LlamaIndex) ===
    semantic_context = get_semantic_context(query, top_k=top_k_semantic)
    semantic_context = safe_truncate(semantic_context, MAX_SEMANTIC_CONTEXT_CHARS)
    files_used.append({"type": "semantic", "desc": f"LlamaIndex top-{top_k_semantic} semantic retrieval"})

    # === 3. External Topic Context ===
    external_context = load_context(topics)
    if external_context.strip() and external_context != "No external context available.":
        for topic in topics:
            files_used.append({"type": "external", "source": f"context/{topic}.md"})

    # === 4. Global Project Context ===
    global_context = load_global_context()
    if "not available" not in global_context:
        files_used.append({"type": "global", "source": "docs/generated/global_context.md"})

    # === 5. Graph Memory Context (summarized) ===
    try:
        graph_context = await summarize_recent_context(query)
        graph_context = safe_truncate(graph_context, MAX_GRAPH_MEMORY_CHARS)
        if graph_context.strip() and "No graph memory matches" not in graph_context:
            files_used.append({"type": "graph", "source": "neo4j"})
    except Exception as ex:
        graph_context = f"[Graph memory error: {str(ex)}]"

    # === 6. Recent Memory Summaries (optional) ===
    memory_summaries = ""
    if memory_entries:
        try:
            memory_summaries = await build_recent_memory_summaries(memory_entries)
        except Exception as ex:
            memory_summaries = f"[Memory summary error: {str(ex)}]"

    # === Assemble final context block ===
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

    # === Logging for debugging ===
    print(f"[CTX] Length: {len(full_context)} chars | Files used: {files_used}")
    if len(full_context) > 12000:
        print("[CTX] WARNING: Full context exceeds 12k chars, consider increasing truncation/aggressive filtering.")

    if debug:
        return {
            "context": full_context,
            "files_used": files_used,
            "sections": {
                "summary": project_summary,
                "semantic": semantic_context,
                "external": external_context,
                "global": global_context,
                "graph": graph_context,
                "memory_summaries": memory_summaries
            }
        }

    return full_context
