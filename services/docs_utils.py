# ──────────────────────────────────────────────────────────────────────────────
# File: docs_utils.py
# Directory: services/
# Purpose : Support utilities for Relay doc tiering
#           • Extract doc_id from file
#           • Build registry of all docs grouped by ID
#           • Determine which file version is canonical
#
# Upstream:
#   - ENV: —
#   - Imports: collections, pathlib, re, typing
#
# Downstream:
#   - routes.docs
#
# Contents:
#   - build_doc_registry()
#   - choose_canonical_path()
#   - extract_doc_id()
#   - write_doc_metadata()

# ──────────────────────────────────────────────────────────────────────────────


import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

# ─── Constants ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = PROJECT_ROOT / "docs"
DOC_FOLDERS = ["", "imported", "generated"]  # relative to /docs/

# ─── Extract doc_id from YAML frontmatter or filename ─────────────────────

def extract_doc_id(path: Path) -> str:
    """
    Extract doc_id from a file's frontmatter or fallback to filename stem.
    Assumes optional comment-style frontmatter: `doc_id: foo`
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[:10]:
            if "doc_id:" in line:
                match = re.search(r"doc_id:\s*(\S+)", line)
                if match:
                    return match.group(1).strip()
    except Exception:
        pass

    return path.stem  # fallback to filename without extension


# ─── Build registry of doc_id → [all versions] ────────────────────────────

def build_doc_registry() -> Dict[str, List[Path]]:
    """
    Scans /docs folders and groups files by doc_id.
    Returns dict of doc_id -> list of Path objects.
    """
    registry: Dict[str, List[Path]] = defaultdict(list)

    for folder in DOC_FOLDERS:
        base = BASE_DIR / folder if folder else BASE_DIR
        if not base.exists():
            continue
        for f in base.rglob("*.md"):
            try:
                doc_id = extract_doc_id(f)
                registry[doc_id].append(f)
            except Exception:
                continue

    return registry


# ─── Choose best version of a doc ─────────────────────────────────────────

def choose_canonical_path(paths: List[Path]) -> Path:
    """
    Select the canonical version of a doc from multiple paths.
    Prefers root-level /docs/ files, else chooses most recently modified.
    """
    for p in paths:
        if p.parent == BASE_DIR:  # root /docs/
            return p
    return max(paths, key=lambda p: p.stat().st_mtime)

def write_doc_metadata(path: Path, updates: dict):
    """
    Updates or inserts a metadata block (as comment) at the top of the markdown file.

    Example block:
    <!--
    doc_id: foo
    tier: global
    pinned: true
    -->
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = None, None

    # Detect existing block
    for i, line in enumerate(lines[:20]):
        if line.strip() == "<!--":
            start = i
        elif line.strip() == "-->":
            end = i
            break

    # Build updated block
    metadata = {**updates}
    if "doc_id" not in metadata:
        metadata["doc_id"] = extract_doc_id(path)

    block = ["<!--"]
    for key, val in metadata.items():
        if val is not None:
            block.append(f"{key}: {str(val).lower() if isinstance(val, bool) else val}")
    block.append("-->")

    # Inject or replace block
    if start is not None and end is not None:
        new_lines = lines[:start] + block + lines[end + 1:]
    else:
        new_lines = block + [""] + lines

    path.write_text("\n".join(new_lines), encoding="utf-8")
