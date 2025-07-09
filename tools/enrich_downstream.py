# File: tools/enrich_downstream.py
# Purpose: Enrich metadata_with_purpose.json with real downstream connections using pydeps

import os
import json
import tempfile
from pathlib import Path
from subprocess import run, PIPE

INPUT = Path("tools/metadata_with_purpose.json")
OUTPUT = Path("tools/metadata_with_downstream.json")

DOC_ROOT = Path(".")  # root of codebase

# Build a map of modules to file paths
MODULE_MAP = {}
for path in DOC_ROOT.rglob("*.py"):
    if "venv" in str(path) or "__pycache__" in str(path):
        continue
    module = str(path.with_suffix(""))
    module = module.replace("/", ".").replace(".py", "")
    MODULE_MAP[path.resolve()] = module


def get_pydeps_downstream(file_path: Path):
    """Run pydeps on a file and parse imported modules that match internal files"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as tmp_svg:
        result = run([
            "pydeps",
            str(file_path),
            "--noshow",
            "--max-bacon=2",
            f"--output={tmp_svg.name}"
        ], stderr=PIPE, stdout=PIPE)

    output = result.stderr.decode()
    found = []
    for line in output.splitlines():
        if "->" in line:
            parts = line.strip().split("->")
            if len(parts) == 2:
                mod = parts[1].strip()
                found.append(mod)
    return list(set(found))


def main():
    with open(INPUT, "r") as f:
        metadata = json.load(f)

    enriched = []
    for entry in metadata:
        rel_path = Path(entry["directory"]) / entry["file"]
        full_path = DOC_ROOT / rel_path

        if not full_path.exists():
            entry["downstream"] = []
            enriched.append(entry)
            continue

        downstream = get_pydeps_downstream(full_path)
        entry["downstream"] = downstream
        enriched.append(entry)
        print(f"✅ {entry['file']}: {len(downstream)} downstream modules")

    with open(OUTPUT, "w") as f:
        json.dump(enriched, f, indent=2)

    print("\n✅ Enriched downstream relationships saved to metadata_with_downstream.json")


if __name__ == "__main__":
    main()
