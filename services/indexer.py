# ──────────────────────────────────────────────────────────────────────────────
# File: indexer.py
# Directory: services
# Purpose: # Purpose: Provides functionality for indexing directories and files, extracting language data, and managing indexing conditions within the system.
#
# Upstream:
#   - ENV: KB_EMBED_MODEL, OPENAI_EMBED_MODEL, WIPE_INDEX
#   - Imports: glob, llama_index.core, llama_index.core.node_parser, llama_index.embeddings.openai, os, pathlib, services.config, shutil, sys
#
# Downstream:
#   - routes.admin
#   - routes.index
#
# Contents:
#   - collect_code_context()
#   - get_language_from_path()
#   - index_directories()
#   - should_index_file()
# ──────────────────────────────────────────────────────────────────────────────
import os
import glob
import sys
from pathlib import Path
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from services.config import INDEX_DIR

import shutil

# --- Guard: WIPE_INDEX only deletes if explicitly set ---
WIPE_INDEX = os.getenv("WIPE_INDEX", "false").lower() == "true"
if WIPE_INDEX:
    if os.path.exists(INDEX_DIR):
        print("WARNING: WIPE_INDEX is set—deleting and recreating index directory.")
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR, exist_ok=True)
else:
    print("WIPE_INDEX not set—existing index will be updated or extended if run.")

# ---- 1. Define priority tiers and associated paths ----
PRIORITY_INDEX_PATHS = [
    ("global", ["./docs/generated/global_context.md", "./docs/generated/global_context.auto.md"]),
    ("context", ["./context/"]),  # Cross-project overlays
    ("project_summary", ["./docs/PROJECT_SUMMARY.md", "./docs/RELAY_CODE_UPDATE.md", "./docs/context-commandcenter.md"]),
    ("project_docs", ["./docs/imported/", "./docs/kb/", "./docs/*.md"]),
    ("code", ["./services/", "./routes/", "./frontend/", "./src/", "./backend/"]),
]

# ---- 2. Exclude Rules for Files, Extensions, and Folders ----
IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", ".env", ".DS_Store", ".gitignore",
}
IGNORED_EXTENSIONS = {
    ".lock", ".log", ".exe", ".bin", ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".ico",
}
IGNORED_FOLDERS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".venv", "env",
}
MAX_FILE_SIZE_MB = 2  # Optional: skip files over 2 MB (adjust as needed)

def should_index_file(filepath: str, tier: str) -> bool:
    """Returns True if a file should be indexed, otherwise False."""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if filename in IGNORED_FILENAMES or ext in IGNORED_EXTENSIONS:
        return False
    # Ignore by folder in path
    parts = filepath.replace("\\", "/").split("/")
    if any(folder in parts for folder in IGNORED_FOLDERS):
        return False
    # Ignore big files
    if os.path.isfile(filepath):
        if os.path.getsize(filepath) > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False
    # For code tier, allow a broad set of code/doc files for review
    if tier == "code":
        return ext in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cpp", ".json", ".md"}
    return True

# ---- 3. Embedding Model ----
model_name = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
embed_model = OpenAIEmbedding(
    model=model_name,
    dimensions=3072 if model_name == "text-embedding-3-large" else None
)

# ---- 4. Language detection for code files ----
def get_language_from_path(file_path: str) -> str:
    """Returns the code language for a given file path by extension."""
    file_path = file_path.lower()
    if file_path.endswith(".py"):
        return "python"
    elif file_path.endswith((".js", ".jsx")):
        return "javascript"
    elif file_path.endswith((".ts", ".tsx")):
        return "typescript"
    elif file_path.endswith(".java"):
        return "java"
    elif file_path.endswith(".go"):
        return "go"
    elif file_path.endswith(".cpp"):
        return "cpp"
    return "python"  # fallback

def collect_code_context(files: list[str], base_dir: str = "./") -> str:
    """Read and join contents of files for prompt context."""
    contents: list[str] = []
    for f in files:
        path = Path(base_dir) / f
        if path.exists() and path.is_file():
            try:
                contents.append(f"### {f}\n" + path.read_text())
            except Exception:
                continue
    return "\n\n".join(contents)

def index_directories():
    """Scans all PRIORITY_INDEX_PATHS, splits, tags with tier, and embeds for semantic search."""
    documents = []
    print(f"[Indexer] Starting directory scan for priority tiers...")
    for tier, paths in PRIORITY_INDEX_PATHS:
        for path in paths:
            if path.endswith("/"):
                if os.path.exists(path):
                    docs = SimpleDirectoryReader(path, recursive=True).load_data()
                    filtered_docs = []
                    for d in docs:
                        file_path = d.metadata.get("file_path") or d.metadata.get("filename") or ""
                        if should_index_file(file_path, tier):
                            d.metadata = d.metadata or {}
                            d.metadata["tier"] = tier
                            filtered_docs.append(d)
                    documents.extend(filtered_docs)
            elif "*" in path or path.endswith(".md"):
                for f in glob.glob(path):
                    if os.path.isfile(f) and should_index_file(f, tier):
                        with open(f, "r", encoding="utf-8") as file:
                            text = file.read()
                        doc = Document(
                            text=text,
                            metadata={"tier": tier, "file_path": f}
                        )
                        documents.append(doc)
    print(f"[Indexer] Total documents collected: {len(documents)}")

    # --- 5. Chunking: Get nodes (split text/code), flatten for indexing ---
    all_chunked_nodes = []
    text_splitter = SentenceSplitter(chunk_size=1024)
    for doc in documents:
        file_path = doc.metadata.get('file_path', '')
        if file_path.endswith(('.py', '.js', '.ts', '.tsx', '.java', '.go', '.cpp')):
            language = get_language_from_path(file_path)
            code_splitter = CodeSplitter(language=language, max_chars=1024, chunk_lines=30)
            nodes = code_splitter.get_nodes_from_documents([doc])
            all_chunked_nodes.extend(nodes)
        else:
            nodes = text_splitter.get_nodes_from_documents([doc])
            all_chunked_nodes.extend(nodes)
    print(f"[Indexer] Total nodes to index: {len(all_chunked_nodes)}")

    if not all_chunked_nodes:
        print("[ERROR] No nodes to index! Aborting persist step.")
        sys.exit(1)

    # --- 6. Index & Persist ---
    index = VectorStoreIndex(
        nodes=all_chunked_nodes,
        embed_model=embed_model,
        show_progress=True
    )
    index.storage_context.persist(persist_dir="./data/index")
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[Indexer] Indexing complete! Prioritized tiers saved to ./data/index.")

if __name__ == "__main__":
    index_directories()
