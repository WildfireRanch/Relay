# File: tools/export_docs.py
# Purpose: Export GPT-structured headers into markdown files under /docs/

import json
from pathlib import Path

INPUT_PATH = Path("tools/metadata_with_reverse_downstream.json")
DOCS_DIR = Path("docs")
INDEX_PATH = DOCS_DIR / "index.md"

DOCS_DIR.mkdir(exist_ok=True)

def write_markdown(entry):
    filename = f"{entry['file'].replace('.py', '')}.md"
    doc_path = DOCS_DIR / filename

    lines = [
        f"# `{entry['file']}`",
        "",
        f"**Directory**: `{entry['directory']}`",
        f"**Purpose**: {entry['purpose']}",
        "",
        "## Upstream",
        f"- ENV: {', '.join(entry['env_vars']) if entry['env_vars'] else '—'}",
        f"- Imports: {', '.join(entry['imports']) if entry['imports'] else '—'}",
        "",
        "## Downstream",
    ]

    downstream = entry.get("downstream", [])
    if downstream:
        lines.extend([f"- {mod}" for mod in sorted(set(downstream))])
    else:
        lines.append("- —")

    lines.extend(["", "## Contents"])
    for fn in sorted(set(entry['contents'])):
        lines.append(f"- `{fn}()`")

    doc_path.write_text("\n".join(lines), encoding="utf-8")
    return filename

def build_index(pages):
    lines = ["# Codebase Index\n"]
    for page in sorted(pages):
        name = page.replace(".md", "")
        lines.append(f"- [{name}](./{page})")
    INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    with open(INPUT_PATH, "r") as f:
        metadata = json.load(f)

    pages = []
    for entry in metadata:
        page = write_markdown(entry)
        pages.append(page)

    build_index(pages)
    print("\n✅ Markdown files exported to /docs/ with real downstream data")
