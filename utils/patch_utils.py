# File: patch_utils.py
# Directory: utils
# Purpose: Provides utilities for handling and manipulating software patches, including validation, diff generation, and rendering previews.
#
# Upstream:
#   - ENV: —
#   - Imports: difflib, typing
#
# Downstream:
#   - agents.codex_agent
#   - routes.codex
#
# Contents:
#   - generate_diff()
#   - render_patch_preview()
#   - summarize_patch()
#   - validate_patch_format()

#-----patch_utils.py-----

import difflib
from typing import List, Dict

def validate_patch_format(action: dict) -> bool:
    """
    Validates the structure of a Codex patch dictionary.

    Expected keys:
    - type: should be 'patch'
    - target_file: relative path to the file being patched
    - patch: the code changes
    - reason: explanation of the change
    """
    required_keys = {"type", "target_file", "patch", "reason"}
    return isinstance(action, dict) and required_keys.issubset(action.keys())

def generate_diff(original: str, updated: str, filename: str = "file.py") -> str:
    """
    Generate a unified diff string between original and updated content.
    Useful for previewing changes, validation, or downstream tooling.
    """
    original_lines = original.strip().splitlines(keepends=True)
    updated_lines = updated.strip().splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )
    return "".join(diff)

def summarize_patch(action: Dict[str, str]) -> str:
    """
    Summarize a patch action into a single-line description for logs or notifications.
    """
    file = action.get("target_file", "unknown")
    reason = action.get("reason", "no reason")
    return f"Patch for {file} — {reason}"

def render_patch_preview(action: Dict[str, str]) -> str:
    """
    Returns a formatted preview block from patch data.
    Can be used in web UIs or CLI tools to preview patch contents.
    """
    patch = action.get("patch", "")
    file = action.get("target_file", "unknown")
    return f"# Patch preview for {file}\n\n{patch}"

# === TODOs ===
# - Add AST-based patch validator
# - Add inline diff syntax highlighter
# - Support patch metadata (language, risk level, source)
# - Export patch format schema
