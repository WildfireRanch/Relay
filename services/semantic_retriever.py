# services/semantic_retriever.py
# Purpose: Safe, self-healing LlamaIndex storage & retriever setup.
# - Loads persisted index from INDEX_ROOT
# - If missing, builds from docs and persists
# - If no docs, creates an empty index so the API never crashes

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List

from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Document
from llama_index.core.readers import SimpleDirectoryReader

log = logging.getLogger("semantic_retriever")

# Where to persist the index on disk
INDEX_ROOT = os.getenv("INDEX_ROOT", "./data/index")
DOCS_DIRS: List[str] = [
    "./docs",
    "./docs/imported",
    "./docs/generated",
]

# Files that typically exist in a persisted LlamaIndex store
REQUIRED_FILES = {
    "docstore.json",
    "index_store.json",
    "default__vector_store.json",
}

def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)

def _persist_exists(root: str) -> bool:
    if not Path(root).exists():
        return False
    present = {p.name for p in Path(root).glob("*.json")}
    return REQUIRED_FILES.issubset(present)

def _load_docs() -> List[Document]:
    docs: List[Document] = []
    for d in DOCS_DIRS:
        p = Path(d)
        if p.exists() and any(p.iterdir()):
            try:
                loader = SimpleDirectoryReader(input_dir=d, recursive=True, required_exts=None)
                docs.extend(loader.load_data())
                log.info("Loaded %d docs from %s", len(docs), d)
            except Exception as e:
                log.warning("Skipping docs dir %s due to error: %s", d, e)
    return docs

def _build_and_persist_empty(root: str):
    log.warning("No docs found; creating EMPTY index at %s", root)
    index = VectorStoreIndex.from_documents([])
    index.storage_context.persist(persist_dir=root)
    return index

def _build_and_persist_from_docs(root: str):
    docs = _load_docs()
    if not docs:
        return _build_and_persist_empty(root)
    log.info("Building index from %d docs…", len(docs))
    index = VectorStoreIndex.from_documents(docs)
    index.storage_context.persist(persist_dir=root)
    log.info("Index persisted to %s", root)
    return index

def get_index():
    """Load existing index or build one if missing; never crash."""
    _ensure_dir(INDEX_ROOT)
    try:
        if _persist_exists(INDEX_ROOT):
            log.info("Loading index from %s", INDEX_ROOT)
            storage = StorageContext.from_defaults(persist_dir=INDEX_ROOT)
            return load_index_from_storage(storage)
        # Fresh build
        return _build_and_persist_from_docs(INDEX_ROOT)
    except Exception as e:
        # Absolute last resort: empty index so API stays up
        log.exception("Index load/build failed; falling back to EMPTY index: %s", e)
        return _build_and_persist_empty(INDEX_ROOT)

# Provide a shared retriever (tune kwargs if you like)
_INDEX = None
def get_retriever():
    global _INDEX
    if _INDEX is None:
        _INDEX = get_index()
    # adjust search kwargs to your needs
    return _INDEX.as_retriever(search_top_k=8)
