# ──────────────────────────────────────────────────────────────────────────────
# File: services/semantic_retriever.py
# Purpose:
#   Safe, self-healing LlamaIndex storage & retriever setup.
#   - Ensures persisted index can always be loaded or rebuilt.
#   - Provides compatibility layer for semantic retrieval in context_injector.
#   - Re-exports robust tiered semantic search (services.kb.search) as
#     get_semantic_context so downstream callers never break.
#
# Upstream:
#   - ENV: INDEX_ROOT (default "./data/index")
#   - Imports: llama_index.core, services.kb
#
# Downstream:
#   - services.context_injector (calls get_semantic_context)
#   - agents.mcp_agent (through context_injector)
#
# Notes:
#   - If the index is missing or corrupt, this module falls back to building
#     a minimal empty index so the API never crashes.
#   - get_semantic_context is the canonical entrypoint for semantic retrieval.
# ──────────────────────────────────────────────────────────────────────────────

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

# Candidate docs directories for fallback index build
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

# ─── Utility helpers ─────────────────────────────────────────────────────────

def _ensure_dir(path: str) -> None:
    """Ensure directory exists for persisted index."""
    Path(path).mkdir(parents=True, exist_ok=True)

def _persist_exists(root: str) -> bool:
    """Check whether a persisted index exists and is valid."""
    if not Path(root).exists():
        return False
    present = {p.name for p in Path(root).glob("*.json")}
    return REQUIRED_FILES.issubset(present)

def _load_docs() -> List[Document]:
    """Load all documents from candidate doc directories."""
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
    """Create and persist an empty index if no docs available."""
    log.warning("No docs found; creating EMPTY index at %s", root)
    index = VectorStoreIndex.from_documents([])
    index.storage_context.persist(persist_dir=root)
    return index

def _build_and_persist_from_docs(root: str):
    """Build and persist an index from docs, or fallback to empty."""
    docs = _load_docs()
    if not docs:
        return _build_and_persist_empty(root)
    log.info("Building index from %d docs…", len(docs))
    index = VectorStoreIndex.from_documents(docs)
    index.storage_context.persist(persist_dir=root)
    log.info("Index persisted to %s", root)
    return index

# ─── Public Index Accessors ───────────────────────────────────────────────────

def get_index():
    """
    Load existing index or build one if missing; never crash.
    If load/build fails, returns an empty index to keep API alive.
    """
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

_INDEX = None
def get_retriever():
    """
    Provide a shared retriever instance (LlamaIndex native).
    Use this if you want direct node retrieval instead of tiered kb.search.
    """
    global _INDEX
    if _INDEX is None:
        _INDEX = get_index()
    # adjust search kwargs to your needs
    return _INDEX.as_retriever(search_top_k=8)

# ─── Canonical Semantic Context Function ──────────────────────────────────────

try:
    # Import robust tiered search from services.kb
    from services.kb import search as get_semantic_context
    log.info("✅ get_semantic_context wired to services.kb.search (tiered semantic search)")
except Exception as e:
    log.exception("⚠️ Failed to import services.kb.search, falling back to retriever: %s", e)

    def get_semantic_context(query: str, top_k: int = 6) -> str:
        """
        Fallback: Use retriever directly if kb.search is unavailable.
        Returns concatenated text snippets.
        """
        try:
            retriever = get_retriever()
            results = retriever.retrieve(query)
            snippets = [n.node.text for n in results[:top_k]]
            return "\n\n".join(snippets)
        except Exception as inner:
            log.error("Semantic retrieval fallback failed: %s", inner)
            return "[Semantic retrieval unavailable]"
