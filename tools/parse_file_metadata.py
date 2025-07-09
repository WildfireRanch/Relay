# File: parse_file_metadata.py
# Directory: tools
# Purpose: Extract and format metadata from files for further processing.
#
# Upstream:
#   - ENV: —
#   - Imports: ast, os, pathlib, sys
#
# Downstream:
#   - —
#
# Contents:
#   - extract_metadata()
#   - format_header()

#----- parse_file_metadata.py-----

import ast
import os
import sys
from pathlib import Path

def extract_metadata(file_path: str) -> dict:
    metadata = {
        "file": os.path.basename(file_path),
        "directory": str(Path(file_path).parent),
        "contents": [],
        "imports": [],
        "env_vars": []
    }

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        tree = ast.parse(f.read(), filename=file_path)

    for node in ast.walk(tree):
        # Get function and class names
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            metadata["contents"].append(node.name)

        # Get import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                metadata["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                metadata["imports"].append(node.module)

        # Get os.getenv or os.environ[...] usage
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            ):
                if node.args and isinstance(node.args[0], ast.Str):
                    metadata["env_vars"].append(node.args[0].s)

        elif isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
                and node.value.attr == "environ"
            ):
                if isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Str):
                    metadata["env_vars"].append(node.slice.value.s)

    return metadata


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/parse_file_metadata.py <path_to_file.py>")
        sys.exit(1)

    file_path = sys.argv[1]
    result = extract_metadata(file_path)

    print(f"\n📄 Metadata for: {file_path}\n")
    print("▶ Contents:")
    for item in result["contents"]:
        print(f"  - {item}")

    print("\n▶ Imports:")
    for imp in result["imports"]:
        print(f"  - {imp}")

    print("\n▶ ENV Vars:")
    for env in result["env_vars"]:
        print(f"  - {env}")
def format_header(meta: dict) -> str:
    imports = sorted(set(meta["imports"]))
    env_vars = sorted(set(meta["env_vars"]))
    contents = sorted(set(meta["contents"]))

    lines = [
        f"# File: {meta['file']}",
        f"# Directory: {meta['directory']}",
        f"# Purpose: <ADD PURPOSE>",
        "#",
        "# Upstream:",
        f"#   - ENV: {', '.join(env_vars) if env_vars else '—'}",
        f"#   - Imports: {', '.join(imports) if imports else '—'}",
        "#",
        "# Downstream:",
        "#   - <ADD downstream effects or modules called>",
        "#",
        "# Contents:"
    ]
    for item in contents:
        lines.append(f"#   - {item}()")
    return "\n".join(lines) + "\n\n"
