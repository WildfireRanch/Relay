# ────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Directory: services/
# Purpose  : Semantic KB helpers (build, load, search, auto-heal)
#            • Model-scoped index + dimension guard
#            • LLM-free TitleExtractor (no nested-async)
#            • search() accepts user_id for legacy callers
# Paths    : Index is always written to **/app/index/<env>/<model>**
#            so both the runtime container (root) and `railway run` shells
#            see the same files.  Any stale folders are scrubbed at startup.
# Last Updated: 2025-06-16
# ────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

from services.config import INDEX_DIR, INDEX_ROOT

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

# ─── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("🔥 services.kb loaded")

# ─── Model configuration ───────────────────────────────────────────────────
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
if MODEL_NAME == "text-embedding-3-large":
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME, dimensions=3072)
else:
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME)

# ─── Index cache ───────────────────────────────────────────────────────────
# Reuse the loaded VectorStoreIndex to avoid repeated disk I/O.  The cache is
# invalidated whenever the index is rebuilt.
_INDEX_CACHE: Optional[VectorStoreIndex] = None

# ─── Index paths (from config) ─────────────────────────────────────────────
# INDEX_ROOT / INDEX_DIR provided by services.config

# Scrub any stale model folders (e.g., old Ada or double-nested dirs)
for path in INDEX_ROOT.iterdir():
    if path.is_dir() and path.name != MODEL_NAME:
        logger.warning("Removing stale index folder %s", path)
        shutil.rmtree(path, ignore_errors=True)

# ─── Ingestion pipeline ────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent
CODE_DIRS  = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR   = ROOT.parent / "docs"
CHUNK_SIZE, CHUNK_OVERLAP = 1024, 200

INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(llm=None),                           # no async LLM
        SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP),
        EMBED_MODEL,
    ]
)

# ─── Dimension helpers ─────────────────────────────────────────────────────
def _vector_dim_current() -> int:
    return len(EMBED_MODEL.get_text_embedding("dim_check"))

def _vector_dim_stored() -> int:
    vs_file = INDEX_DIR / "vector_store.json"
    if not vs_file.exists():
        return -1
    store = json.loads(vs_file.read_text())
    for rec in store.values():
        if isinstance(rec, dict) and isinstance(rec.get("embedding"), list):
            return len(rec["embedding"])
    return -1

EXPECTED_DIM = _vector_dim_current()

# ─── Public helpers ────────────────────────────────────────────────────────
def index_is_valid() -> bool:
    stored = _vector_dim_stored()
    valid  = stored == EXPECTED_DIM and stored > 0
    logger.info("[index_is_valid] stored=%s current=%d → %s", stored, EXPECTED_DIM, valid)
    return valid

def embed_all() -> None:
    """Rebuild the full semantic index."""
    logger.info("📚 Re-indexing KB with model %s", MODEL_NAME)

    docs: List = []
    for path in CODE_DIRS + [DOCS_DIR]:
        if path.exists():
            docs.extend(SimpleDirectoryReader(path).load_data())
    logger.info("Loaded %d documents", len(docs))

    nodes = INGEST_PIPELINE.run(documents=docs)
    logger.info("Generated %d vector nodes", len(nodes))

    index = VectorStoreIndex(nodes=nodes, embed_model=EMBED_MODEL)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info("✅ Index persisted → %s", INDEX_DIR)

def get_index() -> VectorStoreIndex:
    """Return a cached or loaded index, rebuilding if missing or mismatched."""
    global _INDEX_CACHE

    if _INDEX_CACHE is not None and index_is_valid():
        return _INDEX_CACHE

    if not index_is_valid():
        embed_all()

    ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
    _INDEX_CACHE = load_index_from_storage(ctx, embed_model=EMBED_MODEL)
    return _INDEX_CACHE

# ─── Core search used by routes ────────────────────────────────────────────
def search(
    query: str,
    k: int = 8,
    search_type: str = "all",
    score_threshold: Optional[float] = None,
    user_id: Optional[str] = None,
) -> List[dict]:
    """
    Tier-priority semantic search: returns top results ordered by tier.
    - Always tries to surface global/context/project summary results first.
    - Still returns code/project_docs if more space is available.
    """
    # Priority order: highest value to lowest
    PRIORITY_TIERS = [
        "global",         # /docs/generated/global_context.md, etc.
        "context",        # /context/context-*.md
        "project_summary",# /docs/PROJECT_SUMMARY.md, etc.
        "project_docs",   # /docs/imported/, /docs/kb/
        "code",           # /services/, /routes/, etc.
    ]

    qe = get_index().as_query_engine(similarity_top_k=k*2)
    raw = qe.query(query)

    # Group results by tier (preserve order for UI/audit)
    tiered = {tier: [] for tier in PRIORITY_TIERS}
    unknown = []
    for n in getattr(raw, "source_nodes", []):
        if score_threshold is not None and n.score < score_threshold:
            continue
        tier = n.node.metadata.get("tier", "unknown")
        hit = {
            "id": n.node.node_id,
            "snippet": n.node.text,
            "similarity": n.score,
            "tier": tier,
            "path": n.node.metadata.get("file_path"),
            "title": n.node.metadata.get("title", n.node.metadata.get("file_path") or "Untitled"),
        }
        if tier in PRIORITY_TIERS:
            tiered[tier].append(hit)
        else:
            unknown.append(hit)

    # Build prioritized list: up to N per tier (to fill k results, favoring higher tiers)
    prioritized = []
    per_tier = max(1, k // len(PRIORITY_TIERS))
    for tier in PRIORITY_TIERS:
        prioritized.extend(tiered[tier][:per_tier])
    # If not enough, fill with more from each tier in order
    while len(prioritized) < k:
        for tier in PRIORITY_TIERS:
            if len(tiered[tier]) > per_tier:
                prioritized.append(tiered[tier][per_tier])
                if len(prioritized) >= k:
                    break
        else:
            break  # No more to add

    # Fill with unknowns if still short
    if len(prioritized) < k:
        prioritized.extend(unknown[: (k - len(prioritized)) ])

    return prioritized[:k]

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query=query, k=k, search_type=search_type)

def api_reindex() -> dict:
    global _INDEX_CACHE
    embed_all()
    _INDEX_CACHE = None
    return {
        "status": "ok",
        "message": "Re-index complete",
        "index_dir": str(INDEX_DIR),
        "model": MODEL_NAME,
    }

def get_recent_summaries(user_id: str) -> list[str]:
    return ["No summary implemented yet."]

# ─── CLI convenience ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "test"
        for h in search(q):
            print(f"{h['title']} (score={h['similarity']:.2f}): {h['snippet'][:120]}…")
    else:
        embed_all()
