import os
import zipfile

# List of absolute or relative paths to always include
INCLUDE_PATHS = [
    "README.md",
    ".env.example",
    "main.py",
    "docs/generated/global_context.md",
    "docs/generated/global_context.auto.md",
    "docs/generated/relay_code_map.md",
    "docs/PROJECT_SUMMARY.md",
    "docs/RELAY_CODE_UPDATE.md",
    "docs/imported/",
    "docs/kb/",
    "context/",
    "logs/sessions/",
    "logs/audit.jsonl",
    "services/",
    "routes/",
    # Add more if needed, e.g. "frontend/package.json"
]

# Patterns/directories to skip
EXCLUDE_DIRS = ["node_modules", "__pycache__", ".git", ".next", "dist", "build", ".venv", ".mypy_cache"]

def should_include(path):
    # Exclude unwanted directories anywhere in path
    for excl in EXCLUDE_DIRS:
        if f"/{excl}/" in path or path.endswith(f"/{excl}"):
            return False
    return True

def add_path_to_zip(ziph, base_path):
    if os.path.isdir(base_path):
        for root, dirs, files in os.walk(base_path):
            # Filter out excluded dirs
            dirs[:] = [d for d in dirs if should_include(os.path.join(root, d))]
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path)
                if should_include(rel_path):
                    ziph.write(abs_path, rel_path)
    elif os.path.isfile(base_path):
        ziph.write(base_path, base_path)
    # Ignore missing files/folders gracefully

def make_project_context_zip(output_zip="relay_project_context.zip"):
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as ziph:
        for path in INCLUDE_PATHS:
            if os.path.exists(path):
                print(f"Including: {path}")
                add_path_to_zip(ziph, path)
            else:
                print(f"Skipping missing: {path}")

if __name__ == "__main__":
    make_project_context_zip()
    print("Project context zip created: relay_project_context.zip")
