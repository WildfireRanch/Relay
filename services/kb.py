# Directory: services
# File: kb.py
# Purpose: Semantic knowledge‑base utilities using LlamaIndex (≥ 0.10.40).
#          Model‑scoped index dirs + dimension guard to prevent mixed vectors.
# Author: Bret Westwood & Echo
# Last Updated: 2025‑06‑12

"""Semantic KB helper module

Key design points
-----------------
* **Model‑scoped persistence** – each embedding model writes to its own
  `data/index/<model>/` folder, eliminating silent mix‑ups when the model
  changes between deploys.
* **Dimension guard** – startup check aborts if stored vectors and current
  embedding model have mismatched dimensions.
* **Fully self‑contained** – `python services/kb.py` rebuilds the index.
* **Verbose logging** – every stage logs for remote debugging (Railway).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.extractors import TitleExtractor
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("=== [LOADED kb.py @ %s] ===", __file__)

# ─── Paths & Constants ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR = ROOT.parent / "docs"

EMBED_MODEL_NAME = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
EMBED_MODEL = OpenAIEmbedding(model=EMBED_MODEL_NAME)

# Model‑scoped index directory
INDEX_ROOT = ROOT.parent / "data/index"
INDEX_DIR = INDEX_ROOT / EMBED_MODEL_NAME
INDEX_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200

INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(),
        SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP),
        EMBED_MODEL,
    ]
)

# ─── Helpers ────────────────────────────────────────────────────────────────

def _vector_dim_current() -> int:
    """Return embedding dimension for current model."""
    return len(EMBED_MODEL.get_text_embedding("dim_check"))


def _vector_dim_stored() -> int:
    """Return embedding dimension detected in stored index or ‑1 if none."""
    vs_file = INDEX_DIR / "vector_store.json"
    if not vs_file.exists():
        return -1
    store = json.loads(vs_file.read_text())
    # take first embedding array we find
    for rec in store.values():
        if "embedding" in rec and isinstance(rec["embedding"], list):
            return len(rec["embedding"])
    return -1


STORED_DIM, CURR_DIM = _vector_dim_stored(), _vector_dim_current()
if STORED_DIM > -1 and STORED_DIM != CURR_DIM:
    raise RuntimeError(
        f"Embedding dimension mismatch: stored={STORED_DIM} vs current={CURR_DIM}. "
        "Delete the index directory or set OPENAI_EMBED_MODEL to match."
    )

# ─── Build & Load ───────────────────────────────────────────────────────────

def embed_all(user_id: Optional[str] = None) -> None:
    """(Re)build the semantic KB index for all configured files."""
    logger.info("=== [EMBED_ALL] Rebuilding index with model %s ===", EMBED_MODEL_NAME)

    docs = []
    for path in CODE_DIRS + [DOCS_DIR]:
        if path.exists():
            docs.extend(SimpleDirectoryReader(path).load_data())
    logger.info("Loaded %d documents", len(docs))

    nodes = INGEST_PIPELINE.run(documents=docs)
    logger.info("Generated %d nodes", len(nodes))

    index = VectorStoreIndex(nodes=nodes)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info("✅ Index persisted to %s", INDEX_DIR)


def get_index() -> VectorStoreIndex:
    """Load existing index or trigger rebuild."""
    if not any(INDEX_DIR.iterdir()):
        logger.warning("Index dir empty – running embed_all()…")
        embed_all()
    ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
    return load_index_from_storage(ctx)


# ─── Search  ───────────────────────────────────────────────────────────────

def search(
    query: str,
    user_id: Optional[str] = None,
    k: int = 4,
    search_type: str = "all",
    score_threshold: Optional[float] = None,
) -> List[dict]:
    logger.info("[search] q='%s' k=%d", query, k)

    qe = get_index().as_query_engine(similarity_top_k=k)
    results = qe.query(query)

    hits: List[dict] = []
    for n in getattr(results, "source_nodes", []):
        if score_threshold is not None and n.score < score_threshold:
            continue
        hits.append(
            {
                "id": n.node.node_id,
                "snippet": n.node.text,
                "similarity": n.score,
                "path": n.node.metadata.get("file_path"),
                "title": n.node.metadata.get("title", n.node.metadata.get("file_path") or "Untitled"),
            }
        )
    return hits


# ─── API wrappers ──────────────────────────────────────────────────────────

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query=query, k=k, search_type=search_type)


def api_reindex():
    embed_all()
    return {"status": "ok", "message": "Re‑index complete"}


def get_recent_summaries(user_id: str) -> list[str]:
    return ["No summary implemented yet."]


# ─── CLI entrypoint ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "test"
        for h in search(q):
            print(f"{h['title']} (score={h['similarity']:.2f}): {h['snippet'][:120]}…")
    else:
        embed_all()
