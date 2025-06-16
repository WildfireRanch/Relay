# ────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Directory: services/
# Purpose : Semantic KB helpers (build, load, search, auto-heal)
#           • Model-scoped index + dimension guard
#           • LLM-free TitleExtractor (no nested-async)
#           • search() accepts user_id for legacy callers
# NOTE     : Set INDEX_ROOT to /app/index/dev  or  /app/index/prod
#             — do NOT include the model folder; code appends MODEL_NAME.
# Last Updated: 2025-06-16
# ────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

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

# ─── Env-driven configuration ──────────────────────────────────────────────
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
EMBED_MODEL = OpenAIEmbedding(model_name=MODEL_NAME)

INDEX_ROOT = Path(os.getenv("INDEX_ROOT", "data/index/dev")).expanduser()
INDEX_DIR  = INDEX_ROOT / MODEL_NAME                     # …/<env>/<model>
INDEX_DIR.mkdir(parents=True, exist_ok=True)

ROOT      = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR  = ROOT.parent / "docs"

# ─── Ingest pipeline (LLM-free) ────────────────────────────────────────────
CHUNK_SIZE, CHUNK_OVERLAP = 1024, 200
INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(llm=None),                        # no async LLM
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
    logger.info("📚 Re-indexing KB with model %s", MODEL_NAME)

    docs: List = []
    for path in CODE_DIRS + [DOCS_DIR]:
        if path.exists():
            docs.extend(SimpleDirectoryReader(path).load_data())
    logger.info("Loaded %d documents", len(docs))

    nodes = INGEST_PIPELINE.run(documents=docs)
    logger.info("Generated %d vector nodes", len(nodes))

    index = VectorStoreIndex(nodes=nodes)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info("✅ Index persisted → %s", INDEX_DIR)

def get_index() -> VectorStoreIndex:
    if not index_is_valid():
        embed_all()
    ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
    return load_index_from_storage(ctx)

# ─── Core search used by routes ────────────────────────────────────────────
def search(
    query: str,
    k: int = 4,
    search_type: str = "all",
    score_threshold: Optional[float] = None,
    user_id: Optional[str] = None,         # accepted, currently unused
) -> List[dict]:
    qe  = get_index().as_query_engine(similarity_top_k=k)
    raw = qe.query(query)

    hits: List[dict] = []
    for n in getattr(raw, "source_nodes", []):
        if score_threshold is not None and n.score < score_threshold:
            continue
        hits.append(
            {
                "id":         n.node.node_id,
                "snippet":    n.node.text,
                "similarity": n.score,
                "path":       n.node.metadata.get("file_path"),
                "title":      n.node.metadata.get(
                    "title", n.node.metadata.get("file_path") or "Untitled"
                ),
            }
        )
    return hits

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query=query, k=k, search_type=search_type)

def api_reindex() -> dict:
    embed_all()
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
