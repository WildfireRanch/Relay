# File: batch_generate_headers.py
# Directory: tools
# Purpose: # Purpose: Automate the generation and injection of header blocks into files across the codebase based on metadata.
#
# Upstream:
#   - ENV: —
#   - Imports: index_codebase, json, os, parse_file_metadata, pathlib
#
# Downstream:
#   - —
#
# Contents:
#   - inject_header_block()
#   - main()



import os
import json
from pathlib import Path

WRITE_TO_FILES = True  # ✅ Flip this to False if you want dry-run
METADATA_PATH = "tools/metadata_with_reverse_downstream.json"

def format_header(meta: dict) -> str:
    imports = sorted(set(meta["imports"]))
    env_vars = sorted(set(meta["env_vars"]))
    contents = sorted(set(meta["contents"]))
    downstream = sorted(set(meta.get("downstream", [])))
    purpose = meta.get("purpose", "<ADD PURPOSE>").strip()

    lines = [
        f"# File: {meta['file']}",
        f"# Directory: {meta['directory']}",
        f"# Purpose: {purpose}",
        "#",
        "# Upstream:",
        f"#   - ENV: {', '.join(env_vars) if env_vars else '—'}",
        f"#   - Imports: {', '.join(imports) if imports else '—'}",
        "#",
        "# Downstream:",
    ]
    if downstream:
        for d in downstream:
            lines.append(f"#   - {d}")
    else:
        lines.append("#   - —")

    lines.append("#")
    lines.append("# Contents:")
    for item in contents:
        lines.append(f"#   - {item}()")
    return "\n".join(lines) + "\n\n"

def inject_header_block(file_path: str, header: str):
    with open(file_path, "r", encoding="utf-8") as f:
        original = f.read()

    lines = original.split("\n")
    if lines and lines[0].startswith("# File:"):
        while lines and lines[0].startswith("#"):
            lines.pop(0)
        lines = [""] + lines
    new_content = header + "\n".join(lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

def main():
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)

    for entry in metadata:
        full_path = os.path.join(".", entry["directory"], entry["file"])
        header = format_header(entry)
        print(f"📄 {entry['file']}\n{header}")

        if WRITE_TO_FILES:
            inject_header_block(full_path, header)

    print("\n✅ All headers injected using metadata_with_reverse_downstream.json")

if __name__ == "__main__":
    main()
