# File: index_codebase.py
# Directory: tools
# Purpose: # Purpose: Automate the indexing and validation of files within a directory structure for system-wide management.
#
# Upstream:
#   - ENV: —
#   - Imports: os, pathlib, sys
#
# Downstream:
#   - —
#
# Contents:
#   - is_valid_file()
#   - walk_directory()









import os
import sys
from pathlib import Path

EXCLUDE_DIRS = {"venv", "__pycache__", "node_modules", "build", "dist", ".git"}
EXCLUDE_FILES = {"__init__.py"}
ROOT_DIR = "."  # You can change this to the subdirectory you want to scan

def is_valid_file(filename: str) -> bool:
    if not filename.endswith(".py"):
        return False
    if os.path.basename(filename) in EXCLUDE_FILES:
        return False
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        contents = f.read()
        return "def " in contents or "class " in contents  # Only include non-trivial files

def walk_directory(root: str):
    tracked_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]  # skip excluded dirs
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            if is_valid_file(full_path):
                tracked_files.append(os.path.relpath(full_path, start=root))
    return tracked_files

if __name__ == "__main__":
    files = walk_directory(ROOT_DIR)
    print(f"📄 {len(files)} code files found:\n")
    for f in files:
        print(f"- {f}")
