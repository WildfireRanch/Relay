"""
zip_project.py

Zips up all relevant Relay project files for backup, handoff, or review.
Usage: python zip_project.py [zipfilename.zip]
"""

import os
import zipfile
import sys

# What to include
INCLUDE_EXTS = [".py", ".ts", ".tsx", ".js", ".md", ".json", ".yml", ".yaml", ".env", ".sh"]
INCLUDE_DIRS = [
    "relay-backend/app",
    "relay-backend/docs",
    "relay-frontend/components",
    "relay-frontend/pages",
    "relay-frontend/lib",
    "docs",  # If project root/docs exists
]
EXCLUDE = ["__pycache__", ".git", "node_modules", ".venv", "file_embeddings.pkl"]

def is_relevant_file(path):
    # Exclude obvious dirs
    for x in EXCLUDE:
        if x in path:
            return False
    # Only include whitelisted extensions
    return any(path.endswith(ext) for ext in INCLUDE_EXTS)

def add_files_to_zip(zipf, base_dir):
    for dirpath, _, filenames in os.walk(base_dir):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            relpath = os.path.relpath(fpath)
            if is_relevant_file(fpath):
                zipf.write(fpath, relpath)
                print(f"Added: {relpath}")

def main():
    zname = sys.argv[1] if len(sys.argv) > 1 else "relay_project.zip"
    with zipfile.ZipFile(zname, "w", zipfile.ZIP_DEFLATED) as zipf:
        for d in INCLUDE_DIRS:
            if os.path.isdir(d):
                add_files_to_zip(zipf, d)
    print(f"\nProject zipped to {zname}")

if __name__ == "__main__":
    main()
