# File: inject_header.py
# Directory: tools
# Purpose: # Purpose: Manipulate and inject headers into files based on extracted metadata.
#
# Upstream:
#   - ENV: —
#   - Imports: ast, pathlib, sys
#
# Downstream:
#   - —
#
# Contents:
#   - extract_metadata()
#   - format_header()
#   - inject_header()









import ast
import sys
from pathlib import Path

def extract_metadata(file_path: str) -> dict:
    metadata = {
        "file": Path(file_path).name,
        "directory": str(Path(file_path).parent),
        "contents": [],
        "imports": [],
        "env_vars": []
    }

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        tree = ast.parse(f.read(), filename=file_path)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            metadata["contents"].append(node.name)

        if isinstance(node, ast.Import):
            for alias in node.names:
                metadata["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            metadata["imports"].append(node.module)

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            ):
                if node.args and isinstance(node.args[0], (ast.Str, ast.Constant)):
                    key = node.args[0].s if isinstance(node.args[0], ast.Str) else node.args[0].value
                    metadata["env_vars"].append(key)

        elif isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
                and node.value.attr == "environ"
            ):
                try:
                    key = node.slice.value.s if isinstance(node.slice.value, ast.Str) else node.slice.value.value
                    metadata["env_vars"].append(key)
                except Exception:
                    pass

    return metadata

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

def inject_header(file_path: str, write=False):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        original = f.read()

    meta = extract_metadata(file_path)
    header = format_header(meta)

    # Strip any existing metadata header (heuristic: lines starting with # File:)
    stripped = original.split("\n")
    if stripped and stripped[0].startswith("# File:"):
        while stripped and stripped[0].startswith("#"):
            stripped.pop(0)
        stripped = [""] + stripped  # add spacing
        original = "\n".join(stripped)

    new_content = header + original

    if write:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✅ Injected header into {file_path}")
    else:
        print(header)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/inject_header.py <file.py> [--write]")
        sys.exit(1)

    path = sys.argv[1]
    write_mode = "--write" in sys.argv
    inject_header(path, write=write_mode)
