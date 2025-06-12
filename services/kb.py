# services/kb.py
# Directory: services/
# Purpose: Semantic KB using LlamaIndex with logging and overlap chunking.
# Author: [Your Name]
# Last Updated: 2025-06-12
# KNOWN ISSUE:
#  - Chunk Gap: This mitigates boundary context loss with overlap, but native support preferred.

import os
import logging
from typing import List, Optional
from pathlib import Path
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    SimpleDirectoryReader,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import SentenceSplitter

# ——— Logging Setup —————————————————————————————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# === AV file exclusion ===
EXCLUDED_SUFFIXES = {".mp3", ".wav", ".mp4", ".avi", ".mov", ".mkv", ".flac"}

def safe_simple_directory_reader(directory: Path, recursive: bool = True) -> SimpleDirectoryReader:
    all_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if not any(f.lower().endswith(ext) for ext in EXCLUDED_SUFFIXES):
                all_files.append(os.path.join(root, f))
        if not recursive:
            break
    return SimpleDirectoryReader(input_files=all_files)

def overlapping_chunks(text: str, max_chars: int, chunk_lines: int, overlap_lines: int) -> List[str]:
    lines = text.splitlines()
    chunks, i = [], 0
    while i < len(lines):
        chunk = "\n".join(lines[i:i+chunk_lines])
        if len(chunk) > max_chars:
            chunk = chunk[:max_chars]
        chunks.append(chunk)
        if i + chunk_lines >= len(lines):
            break
        i += chunk_lines - overlap_lines
    return chunks

# === Paths & Config ===
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR = ROOT.parent / "docs"
INDEX_DIR = ROOT.parent / "data/index"
EMBED_MODEL = OpenAIEmbedding(model="text-embedding-3-large")

def embed_all(user_id: Optional[str] = None) -> None:
    logger.info("📦 Starting index build...")
    documents = []
    for code_dir in CODE_DIRS:
        if code_dir.exists():
            docs = safe_simple_directory_reader(code_dir).load_data()
            for d in docs:
                d.metadata["type"] = "code"
            documents.extend(docs)
    if DOCS_DIR.exists():
        docs = safe_simple_directory_reader(DOCS_DIR).load_data()
        for d in docs:
            d.metadata["type"] = "doc"
        documents.extend(docs)
    logger.info("Found %d docs to index", len(documents))

    text_splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    code_max_chars, code_chunk_lines, code_overlap_lines = 1024, 30, 10

    for d in documents:
        if d.metadata.get("type") == "code":
            d.chunks = overlapping_chunks(d.text, code_max_chars, code_chunk_lines, code_overlap_lines)
        else:
            d.chunks = text_splitter.split(d.text)

    try:
        index = VectorStoreIndex.from_documents(documents, embed_model=EMBED_MODEL, show_progress=True)
        index.storage_context.persist(persist_dir=str(INDEX_DIR))
        logger.info("✅ Indexing complete!")
    except Exception:
        logger.exception("❌ Index build failed")
        raise

def get_index():
    if not INDEX_DIR.exists() or not any(INDEX_DIR.iterdir()):
        logger.warning("Index missing—triggering embed_all()")
        embed_all()
    try:
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        return load_index_from_storage(ctx)
    except Exception:
        logger.exception("Failed to load index")
        raise

def search(query: str, user_id: Optional[str] = None, k: int = 4, search_type: str = "all", score_threshold: Optional[float] = None) -> List[dict]:
    try:
        idx = get_index()
        results = idx.query(query, embed_model=EMBED_MODEL, top_k=k)
        formatted = []
        for r in results:
            if score_threshold is not None and r.score < score_threshold:
                continue
            formatted.append({"snippet": r.text, "score": r.score, "file": r.metadata.get("file_path"), "type": r.metadata.get("type"), "line": r.metadata.get("line_number")})
        if search_type in ("code", "doc"):
            formatted = [h for h in formatted if h.get("type") == search_type]
        return formatted
    except Exception:
        logger.exception("Search failed")
        raise

def get_recent_summaries(user_id: Optional[str] = None) -> str:
    base = ROOT.parent
    if user_id:
        fn = base / f"docs/generated/{user_id}_context.md"
        if fn.exists():
            try:
                return fn.read_text()
            except Exception:
                logger.exception("Error loading user summary")
    fn_gen = base / "docs/generated/relay_context.md"
    return fn_gen.read_text() if fn_gen.exists() else ""

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query, k=k, search_type=search_type)

def api_reindex() -> dict:
    embed_all()
    return {"status": "ok", "message": "Re-index complete"}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "agent context"
        for h in search(q):
            print(f"{h['file']} (score={h['score']:.2f})\n{h['snippet'][:160]}...\n")
    else:
        embed_all()
