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
    """
    Returns True if a file should be indexed, otherwise False.
    Excludes files/folders by name, extension, size, or path.
    Allows broader set for 'code' tier to support code review.
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    # Ignore by filename or extension
    if filename in IGNORED_FILENAMES or ext in IGNORED_EXTENSIONS:
        return False

    # Ignore by folder in path
    parts = filepath.replace("\\", "/").split("/")
    if any(folder in parts for folder in IGNORED_FOLDERS):
        return False

    # Optional: ignore big files
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
    """
    Returns the code language for a given file path by extension.
    Defaults to 'python' if unknown.
    """
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
    # Add more as needed
    return "python"  # fallback

def index_directories():
    """
    Scans all PRIORITY_INDEX_PATHS, splits, tags with tier, and embeds for semantic search.
    Applies strict filtering to skip junk files and folders.
    """
    documents = []

    for tier, paths in PRIORITY_INDEX_PATHS:
        for path in paths:
            if path.endswith("/"):
                # Folder: Use LlamaIndex reader (recursively)
                if os.path.exists(path):
                    docs = SimpleDirectoryReader(path, recursive=True).load_data()
                    # Attach tier and filter
                    filtered_docs = []
                    for d in docs:
                        # LlamaIndex may set file path as 'file_path' or 'filename'
                        file_path = d.metadata.get("file_path") or d.metadata.get("filename") or ""
                        if should_index_file(file_path, tier):
                            d.metadata = d.metadata or {}
                            d.metadata["tier"] = tier
                            filtered_docs.append(d)
                    documents.extend(filtered_docs)
            elif "*" in path or path.endswith(".md"):
                # Glob or single file: Add if not ignored
                for f in glob.glob(path):
                    if os.path.isfile(f) and should_index_file(f, tier):
                        with open(f, "r", encoding="utf-8") as file:
                            text = file.read()
                        doc = Document(
                            text=text,
                            metadata={"tier": tier, "file_path": f}
                        )
                        documents.append(doc)

    # --- 5. Chunking (Code vs Text, with language detection for code) ---
    text_splitter = SentenceSplitter(max_chunk_size=1024)
    for doc in documents:
        file_path = doc.metadata.get('file_path', '')
        # If this is a recognized code file, pick language; otherwise, treat as text
        if file_path.endswith(('.py', '.js', '.ts', '.tsx', '.java', '.go', '.cpp')):
            language = get_language_from_path(file_path)
            code_splitter = CodeSplitter(language=language, max_chars=1024, chunk_lines=30)
            doc.chunks = code_splitter.split(doc.text)
        else:
            doc.chunks = text_splitter.split(doc.text)

    # --- 6. Index & Persist ---
    print(f"Total documents indexed: {len(documents)}")
    index = VectorStoreIndex.from_documents(
        documents, embed_model=embed_model, show_progress=True
    )
    index.storage_context.persist(persist_dir="./data/index")
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("Indexing complete! Prioritized tiers saved.")

if __name__ == "__main__":
    index_directories()
