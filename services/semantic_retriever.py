# ──────────────────────────────────────────────────────────────────────────────
# File: services/semantic_retriever.py
# Purpose:
#   Compatibility + safety layer for semantic retrieval.
#   - Keeps persisted index safety helpers available (get_index/get_retriever)
#   - Re-exports a robust, planner-friendly get_semantic_context that:
#       * accepts both `top_k` and `k` (prefers `k`)
#       * calls services.kb.search(...)
#       * renders hits into readable markdown for prompts
#   - Never crashes the API: logs and returns a placeholder on failure
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List

from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Document
from llama_index.core.readers import SimpleDirectoryReader

log = logging.getLogger("semantic_retriever")

# ===== Persisted-index safety (unchanged) ====================================

INDEX_ROOT = os.getenv("INDEX_ROOT", "./data/index")
DOCS_DIRS: List[str] = ["./docs", "./docs/imported", "./docs/generated"]
REQUIRED_FILES = {"docstore.json", "index_store.json", "default__vector_store.json"}

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
        return _build_and_persist_from_docs(INDEX_ROOT)
    except Exception as e:
        log.exception("Index load/build failed; falling back to EMPTY index: %s", e)
        return _build_and_persist_empty(INDEX_ROOT)

_INDEX = None
def get_retriever():
    """LLM-native retriever (kept for callers that want nodes instead of tiered search)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = get_index()
    return _INDEX.as_retriever(search_top_k=8)

# ===== Compat wrapper for kb.search ==========================================

from services.kb import search as _kb_search

_SUPPORTED_FORWARD = {"k", "search_type", "score_threshold", "user_id", "explain", "min_global"}

def _render_hits_markdown(hits: list) -> str:
    """Turn kb.search hits into planner-friendly markdown."""
    if not isinstance(hits, list) or not hits:
        return "[No semantic matches]"
    lines = []
    for i, h in enumerate(hits, 1):
        title = h.get("title") or h.get("path") or "Snippet"
        path = h.get("path") or ""
        snippet = (h.get("snippet") or "").strip()
        meta_tier = h.get("tier") or "unknown"
        sim = h.get("similarity")
        sim_s = f"{sim:.3f}" if isinstance(sim, (int, float)) else ""
        path_s = f" ({path})" if path else ""
        lines.append(f"{i}. **{title}**{path_s}  — _tier: {meta_tier}{(', score: ' + sim_s) if sim_s else ''}_\n{snippet}")
    return "\n\n".join(lines)

def get_semantic_context(query: str, **kwargs) -> str:
    """
    Compatibility entrypoint for context_injector:
      - Accepts `top_k` or `k` (prefers `k`)
      - Forwards only supported kwargs to kb.search(...)
      - Renders list of hits → markdown string for prompt consumption
      - Returns a safe placeholder on any failure
    """
    # Normalize kwarg names: allow callers to pass top_k
    if "k" not in kwargs and "top_k" in kwargs:
        kwargs["k"] = kwargs.pop("top_k")

    # Whitelist supported kwargs to avoid TypeError from unknown keys
    forward = {k: v for k, v in kwargs.items() if k in _SUPPORTED_FORWARD}

    try:
        hits = _kb_search(query=query, **forward)
        return _render_hits_markdown(hits)
    except TypeError as e:
        # Last-ditch stripping of anything weird and retry once
        log.warning("kb.search bad kwargs (%s); retrying with minimal set", e)
        minimal = {k: forward[k] for k in ("k",) if k in forward}
        try:
            hits = _kb_search(query=query, **minimal)
            return _render_hits_markdown(hits)
        except Exception as inner:
            log.error("Semantic retrieval failed after retry: %s", inner)
            return "[Semantic retrieval unavailable]"
    except Exception as e:
        log.error("Semantic retrieval failure: %s", e)
        return "[Semantic retrieval unavailable]"
