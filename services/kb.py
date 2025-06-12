# services/kb.py
# Directory: services/
# Purpose: LlamaIndex-powered semantic knowledge base for context, code/doc search, and summaries.

import os
from typing import List, Optional, Any
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, SimpleDirectoryReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from pathlib import Path

# === Patch: Exclude Audio/Video Files ===
from llama_index.core.readers.file.base import DEFAULT_FILE_EXTRACTOR
EXCLUDED_SUFFIXES = {".mp3", ".wav", ".mp4", ".avi", ".mov", ".mkv", ".flac"}

def safe_simple_directory_reader(directory, recursive=True):
    """
    Create a SimpleDirectoryReader that ignores audio/video files.
    """
    file_extractor = {k: v for k, v in DEFAULT_FILE_EXTRACTOR.items() if k not in EXCLUDED_SUFFIXES}
    return SimpleDirectoryReader(str(directory), recursive=recursive, file_extractor=file_extractor)

# === Paths and Config ===
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / "src", ROOT.parent / "backend", ROOT.parent / "frontend"]
DOCS_DIR = ROOT.parent / "docs"
INDEX_DIR = ROOT.parent / "data/index"
EMBED_MODEL = OpenAIEmbedding(model="text-embedding-3-large")

# === Indexing Function ===
def embed_all(user_id: Optional[str] = None):
    """
    Index all code and docs recursively for semantic search.
    Use this to (re)build your KB index.
    """
    documents = []
    # Index all code files
    for code_dir in CODE_DIRS:
        if code_dir.exists():
            docs = safe_simple_directory_reader(code_dir, recursive=True).load_data()
            for doc in docs:
                doc.metadata['type'] = "code"
            documents.extend(docs)
    # Index all markdown/docs
    if DOCS_DIR.exists():
        docs = safe_simple_directory_reader(DOCS_DIR, recursive=True).load_data()
        for doc in docs:
            doc.metadata['type'] = "doc"
        documents.extend(docs)
    # Split by file type
    code_splitter = CodeSplitter(max_chars=1024, chunk_lines=30, chunk_overlap=10)
    text_splitter = SentenceSplitter(max_chunk_size=1024)
    for doc in documents:
        if doc.metadata.get('type') == "code":
            doc.chunks = code_splitter.split(doc.text)
        else:
            doc.chunks = text_splitter.split(doc.text)
    # Build and persist vector index
    index = VectorStoreIndex.from_documents(
        documents, embed_model=EMBED_MODEL, show_progress=True
    )
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[KB] Indexing complete!")

# === Load Vector Index ===
def get_index():
    storage_context = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
    return load_index_from_storage(storage_context)

# === Semantic Search ===
def search(
    query: str,
    user_id: Optional[str] = None,
    k: int = 4,
    search_type: str = "all",
    score_threshold: Optional[float] = None
) -> List[dict]:
    """
    Search code/docs for semantic matches.
    - search_type: 'all', 'code', or 'doc'
    - score_threshold: only return hits above this score (if provided)
    """
    index = get_index()
    results = index.query(query, embed_model=EMBED_MODEL, top_k=k)
    # Format each hit for easy API/UI/agent consumption
    formatted = []
    for r in results:
        if score_threshold is not None and r.score < score_threshold:
            continue
        formatted.append({
            "snippet": r.text,
            "score": r.score,
            "file": r.metadata.get("file_path"),
            "type": r.metadata.get("type"),
            "line": r.metadata.get("line_number"),
        })
    if search_type in ("code", "doc"):
        formatted = [h for h in formatted if h.get("type") == search_type]
    return formatted

# === Per-user or Generic Context Summaries ===
def get_recent_summaries(user_id: Optional[str] = None) -> str:
    """
    Load most recent context summary for this user, or fallback to generic.
    """
    base = ROOT.parent
    if user_id:
        summary = base / f"docs/generated/{user_id}_context.md"
        if summary.exists():
            try:
                return summary.read_text()
            except Exception as e:
                print(f"[KB] Error reading user summary: {e}")
                return ""
    generic = base / "docs/generated/relay_context.md"
    return generic.read_text() if generic.exists() else ""

# === API Helper Functions ===
def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    """
    API-friendly wrapper for search (for FastAPI).
    """
    return search(query, k=k, search_type=search_type)

def api_reindex() -> dict:
    """
    API-friendly wrapper to (re)build the index.
    """
    embed_all()
    return {"status": "ok", "message": "Re-index complete"}

# === CLI Entrypoint ===
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "agent context"
        for hit in search(q):
            print(f"{hit['file']} (score={hit['score']:.2f})\n{hit['snippet'][:160]}...\n")
    else:
        embed_all()
