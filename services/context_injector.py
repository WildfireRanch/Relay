# File: services/context_injector.py
# Purpose: Build rich, multi-source context blocks for agent prompts (code, docs, external topics, global context, knowledge base, and graph memory).

import os
from pathlib import Path
from typing import List, Dict, Any, Union

from services.indexer import collect_code_context
from services.kb import query_index
from services.graph import summarize_recent_context  # For graph-based memory

# --- Extract function/class names from selected files for structure ---
def extract_functions(files: List[str], base_dir: str = "./") -> str:
    """
    Scans files and extracts all function/class signatures.
    Returns a newline-separated string of 'file: signature' lines.
    """
    result = []
    for file in files:
        full_path = Path(base_dir) / file
        if full_path.exists():
            with open(full_path, "r") as f:
                for line in f:
                    line_strip = line.strip()
                    if line_strip.startswith("def ") or line_strip.startswith("class "):
                        result.append(f"{file}: {line_strip}")
    return "\n".join(result)

# --- Load Markdown snippets from /context/<topic>.md files ---
def load_context(topics: List[str], base_dir: str = "./context/") -> str:
    """
    Loads external context markdown by topic name.
    """
    chunks = []
    for topic in topics:
        path = Path(base_dir) / f"{topic}.md"
        if path.exists():
            with open(path, "r") as f:
                chunks.append(f"\n# {topic.title()}\n" + f.read())
    return "\n".join(chunks) if chunks else "No external context available."

# --- Load a high-level project summary ---
def load_summary(summary_file: str = "./docs/PROJECT_SUMMARY.md") -> str:
    """
    Loads project summary file, if available.
    """
    if os.path.exists(summary_file):
        with open(summary_file, "r") as f:
            return f.read()
    return "Project summary not available."

# --- Load Google-synced global context ---
def load_global_context(path: str = "./docs/generated/global_context.md") -> str:
    """
    Loads global project context file, if available.
    """
    if Path(path).exists():
        with open(path, "r") as f:
            return f.read()
    return "Global project context not available."

# --- MAIN CONTEXT BUILDER ---
async def build_context(
    query: str,
    files: List[str],
    topics: List[str] = [],
    debug: bool = False
) -> Union[str, Dict[str, Any]]:
    """
    Builds a multi-layered markdown context block for agent prompts.
    Returns:
        - Full string prompt (always)
        - Optionally, dict with 'context' and 'files_used' (if debug=True)
    """
    files_used: List[Dict[str, Any]] = []

    # --- Static project summary ---
    project_summary = load_summary()
    if "Project summary not available." not in project_summary:
        files_used.append({"type": "summary", "source": "docs/PROJECT_SUMMARY.md"})

    # --- Code context (raw file text) ---
    code_context = collect_code_context(files)
    if code_context.strip():
        for f in files:
            files_used.append({"type": "code", "source": f})

    # --- Function/class signatures for structure ---
    function_signatures = extract_functions(files)
    if function_signatures.strip():
        for f in files:
            files_used.append({"type": "functions", "source": f})

    # --- External topic context ---
    external_context = load_context(topics)
    if external_context.strip() and external_context != "No external context available.":
        for topic in topics:
            files_used.append({"type": "external", "source": f"context/{topic}.md"})

    # --- Global project context (Google-synced) ---
    global_context = load_global_context()
    if "not available" not in global_context:
        files_used.append({"type": "global", "source": "docs/generated/global_context.md"})

    # --- Knowledge base: semantic search results ---
    semantic_docs = query_index(query)
    semantic_sources = []
    for line in semantic_docs.splitlines():
        if line.startswith("# "):
            semantic_sources.append(line.lstrip("# ").strip())
    for title in set(semantic_sources):
        files_used.append({"type": "semantic", "title": title})

    # --- Graph memory context ---
    graph_context = await summarize_recent_context(query)
    if graph_context.strip():
        files_used.append({"type": "graph", "source": "neo4j"})
    else:
        graph_context = "No graph memory matches found."

    # --- Assemble final context block (markdown, with clear sections) ---
    full_context = f"""
## 🧠 Project Summary:
{project_summary}

## 📁 Code Context (Selected Files):
{code_context}

## 🛠️ Key Functions & Classes:
{function_signatures}

## 🌍 External Project Context:
{external_context}

## 🌐 Global Project Context:
{global_context}

## 🔍 Relevant Knowledge Base Excerpts:
{semantic_docs}

## 🧠 Graph Memory Summary:
{graph_context}
""".strip()

    if debug:
        return {
            "context": full_context,
            "files_used": files_used,
        }

    return full_context
