# File: scripts/generate_code_map.py
# Purpose: Create a human-readable project snapshot at /docs/generated/relay_code_map.md

from pathlib import Path
from datetime import datetime
import ast

FILES = [
    ("services/context_injector.py", "core"),
    ("services/indexer.py", "core"),
    ("routes/ask.py", "core"),
    ("routes/admin_routes.py", "core"),
    ("routes/status.py", "support"),
    ("scripts/sync_context_docs.py", "support"),
    ("scripts/generate_global_context_auto.py", "support"),
    ("main.py", "entrypoint")
]

output = ["# Relay Code Map (Auto-Generated)", ""]
output.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")

for file_path, tag in FILES:
    path = Path(file_path)
    if not path.exists():
        output.append(f"## {file_path}\n- ❌ Missing\n")
        continue

    try:
        tree = ast.parse(path.read_text())
        functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except Exception:
        functions = []

    modified = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z"

    output.append(f"## {file_path}")
    output.append(f"- ✅ {tag.title()} file")
    output.append(f"- Last modified: `{modified}`")
    if functions:
        output.append("- Functions:")
        output.extend([f"  - `{f}`" for f in sorted(functions)])
    else:
        output.append("- No functions found")
    output.append("")

Path("docs/generated").mkdir(parents=True, exist_ok=True)
Path("docs/generated/relay_code_map.md").write_text("\n".join(output))
print("✅ Code map written to /docs/generated/relay_code_map.md")
