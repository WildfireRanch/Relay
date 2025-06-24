# services/indexer.py
# Purpose: Recursively index code and docs with tier metadata for prioritized semantic search.
# Stack: LlamaIndex, OpenAI, Python 3.12+
# Usage: Call index_directories() to scan, split, and embed all target files.

import os
import glob
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from services.config import INDEX_DIR

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

def index_directories():
    """Scans all PRIORITY_INDEX_PATHS, splits, tags with tier, and embeds for semantic search."""
    documents = []
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

    # --- 6. Index & Persist ---
    print(f"Total nodes to index: {len(all_chunked_nodes)}")
    index = VectorStoreIndex.from_nodes(
        all_chunked_nodes, embed_model=embed_model, show_progress=True
    )
    index.storage_context.persist(persist_dir="./data/index")
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("Indexing complete! Prioritized tiers saved.")

if __name__ == "__main__":
    index_directories()
