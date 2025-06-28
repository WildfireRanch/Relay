# File: services/context_injector.py
# Purpose: Inject rich, multi-domain context into GPT agent prompts (code + external projects + Google-synced global context)

import os
from pathlib import Path
# Lightweight helpers for reading code files and KB search
from services.indexer import collect_code_context
from services.kb import query_index

# -- Extract function/class names from files --
def extract_functions(files, base_dir="./"):
    result = []
    for file in files:
        full_path = Path(base_dir) / file
        if full_path.exists():
            with open(full_path, "r") as f:
                lines = f.readlines()
            for line in lines:
                line_strip = line.strip()
                if line_strip.startswith("def ") or line_strip.startswith("class "):
                    result.append(f"{file}: {line_strip}")
    return "\n".join(result)

# -- Load general project summaries from /context/*.md --
def load_context(topics, base_dir="./context/"):
    chunks = []
    for topic in topics:
        path = Path(base_dir) / f"{topic}.md"
        if path.exists():
            with open(path, "r") as f:
                chunks.append(f"\n# {topic.title()}\n" + f.read())
    return "\n".join(chunks) if chunks else "No external context available."

# -- Load summary file for Relay core project --
def load_summary(summary_file="./docs/PROJECT_SUMMARY.md"):
    if os.path.exists(summary_file):
        with open(summary_file, "r") as f:
            return f.read()
    return "Project summary not available."

# -- Load global, synced context file (from Google Docs) --
def load_global_context(path="./docs/generated/global_context.md"):
    if Path(path).exists():
        with open(path, "r") as f:
            return f.read()
    return "Global project context not available."

# -- Main context builder --
def build_context(query: str, files: list[str], topics: list[str] = [], debug: bool = False):
    """
    Generates a multi-layered context block to inject into GPT queries.
    Returns:
      - full string prompt (always)
      - optional debug output: files_used metadata
    """
    files_used = []

    # --- Load static blocks ---
    project_summary = load_summary()
    if "Project summary not available." not in project_summary:
        files_used.append({"type": "summary", "source": "docs/PROJECT_SUMMARY.md"})

    code_context = collect_code_context(files)
    if code_context.strip():
        for f in files:
            files_used.append({"type": "code", "source": f})

    function_signatures = extract_functions(files)
    if function_signatures.strip():
        for f in files:
            files_used.append({"type": "functions", "source": f})

    external_context = load_context(topics)
    if external_context.strip():
        for topic in topics:
            files_used.append({"type": "external", "source": f"context/{topic}.md"})

    global_context = load_global_context()
    if "not available" not in global_context:
        files_used.append({"type": "global", "source": "docs/generated/global_context.md"})

    # --- Semantic search chunks ---
    semantic_docs = query_index(query)
    semantic_sources = []
    for line in semantic_docs.splitlines():
        if line.startswith("# "):
            # Try to extract source titles from chunk headers
            semantic_sources.append(line.lstrip("# ").strip())

    for title in set(semantic_sources):
        files_used.append({"type": "semantic", "title": title})

    # --- Assemble final context ---
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
""".strip()

    if debug:
        return {
            "context": full_context,
            "files_used": files_used,
        }

    return full_context
