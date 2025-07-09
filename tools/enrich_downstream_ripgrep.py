# File: tools/enrich_downstream_ripgrep.py
# Purpose: Build reverse dependency map using import analysis and enrich metadata with real downstream usage

import os
import json
from pathlib import Path
from collections import defaultdict

INPUT_PATH = Path("tools/metadata_with_purpose.json")
OUTPUT_PATH = Path("tools/metadata_with_reverse_downstream.json")

# Step 1: Build a map from file path to module name
PROJECT_ROOT = Path(".").resolve()
file_to_module = {}
module_to_file = {}

for path in PROJECT_ROOT.rglob("*.py"):
    if any(part in {"venv", "__pycache__"} for part in path.parts):
        continue
    rel_path = path.relative_to(PROJECT_ROOT)
    module = str(rel_path.with_suffix("")).replace(os.sep, ".")
    file_to_module[str(rel_path)] = module
    module_to_file[module] = str(rel_path)

# Step 2: Build a reverse dependency map
reverse_deps = defaultdict(list)

for src_path, src_module in file_to_module.items():
    try:
        with open(PROJECT_ROOT / src_path, "r", encoding="utf-8") as f:
            code = f.read()
        for imported_module in module_to_file:
            if imported_module == src_module:
                continue
            if f"import {imported_module}" in code or f"from {imported_module} import" in code:
                reverse_deps[imported_module].append(src_module)
    except Exception as e:
        print(f"❌ Error reading {src_path}: {e}")

# Step 3: Enrich metadata
with open(INPUT_PATH, "r") as f:
    metadata = json.load(f)

for entry in metadata:
    mod = file_to_module.get(os.path.join(entry["directory"], entry["file"]))
    entry["downstream"] = sorted(reverse_deps.get(mod, []))

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2)

print("\n✅ Reverse downstream enriched: saved to metadata_with_reverse_downstream.json")
