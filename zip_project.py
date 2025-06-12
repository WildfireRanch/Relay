#!/usr/bin/env python3
"""
bundle_project_files.py

Bundles key backend (FastAPI, services) and frontend (Next.js/React) source files for review.
Outputs: project_bundle.zip and manifest.txt

Usage:
    python bundle_project_files.py
"""

import os
import zipfile

# === CONFIG: Update as needed ===
INCLUDE_DIRS = [
    "services",      # Backend core logic
    "pages"
    "routes",        # FastAPI API routes
    "frontend/src/app",       # Next.js (pages, API routes)
    "frontend/src/api"
    "frontend/src/components",# React components
    "docs",          # Documentation/specs
]
INCLUDE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".env")
EXCLUDE = ("__pycache__", "node_modules", ".venv", ".git", "dist", "build", "out")

ZIP_NAME = "project_bundle.zip"
MANIFEST = "manifest.txt"

# === Helper functions ===
def should_include(path):
    if any(part in EXCLUDE for part in path.split(os.sep)):
        return False
    if path.endswith(INCLUDE_EXTS):
        return True
    return False

def gather_files():
    files = []
    for d in INCLUDE_DIRS:
        for root, dirs, filenames in os.walk(d):
            for f in filenames:
                full = os.path.join(root, f)
                if should_include(full):
                    files.append(full)
    return files

def write_manifest(files):
    with open(MANIFEST, "w") as mf:
        for f in files:
            mf.write(f + "\n")
    print(f"Manifest written to {MANIFEST}")

def bundle_files(files):
    with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f)
    print(f"Bundled {len(files)} files into {ZIP_NAME}")

if __name__ == "__main__":
    files = gather_files()
    write_manifest(files)
    bundle_files(files)
