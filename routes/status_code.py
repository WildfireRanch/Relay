# ──────────────────────────────────────────────────────────────────────────────
# File: status_code.py
# Directory: routes
# Purpose: # Purpose: Provides utilities to extract and interpret status codes from FastAPI responses.
#
# Upstream:
#   - ENV: —
#   - Imports: ast, datetime, fastapi, os, pathlib
#
# Downstream:
#   - —
#
# Contents:
#   - extract_functions()
#   - get_code_status()

# ──────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter
from pathlib import Path
import os, ast
from datetime import datetime

router = APIRouter(prefix="/status", tags=["status"])

CODE_PATHS = [
    ("services/context_injector.py", "core"),
    ("services/indexer.py", "core"),
    ("routes/ask.py", "core"),
    ("routes/admin_routes.py", "core"),
    ("routes/status.py", "support"),
    ("scripts/sync_context_docs.py", "support"),
    ("scripts/generate_global_context.auto.py", "support"),
    ("main.py", "entrypoint")
]

# Extract function names from a file using AST
def extract_functions(path: Path) -> list:
    try:
        tree = ast.parse(path.read_text())
        return [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except Exception:
        return []

@router.get("/code")
def get_code_status():
    results = []
    for rel_path, tag in CODE_PATHS:
        path = Path(rel_path)
        if not path.exists():
            results.append({"file": rel_path, "status": "❌ Missing", "tag": tag})
            continue

        functions = extract_functions(path)
        modified = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z"
        results.append({
            "file": rel_path,
            "status": "✅ OK",
            "tag": tag,
            "functions": functions,
            "last_modified": modified
        })

    return {"files": results}
