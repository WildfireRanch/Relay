# services/kb.py
# Directory: services/
# Purpose: Semantic KB using LlamaIndex with ingestion pipeline, node-level control, and robust querying (LlamaIndex ≥0.10)
# Author: [Your Name]
# Last Updated: 2025-06-12

import os
import logging
from typing import List, Optional
from pathlib import Path

from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Document,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.extractors import TitleExtractor

# ——— Logging Setup ———————————————————————————————————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("=== [LOADED kb.py: LLAMAINDEX v0.10+ API, %s] ===", __file__)

# === Config Paths & Settings ===
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR = ROOT.parent / "docs"
INDEX_DIR = ROOT.parent / "data/index"

# Pre‑defined ingestion pipeline (for consistent chunking & embedding)
INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        SentenceSplitter(chunk_size=1024, chunk_overlap=200),
        TitleExtractor(),
        OpenAIEmbedding(model="text-embedding-3-large"),
    ]
)

def embed_all(user_id: Optional[str] = None) -> None:
    logger.info("=== [EMBED_ALL] Rebuilding semantic KB index ===")
    # 1. Load documents
    docs = []
    for path in CODE_DIRS + [DOCS_DIR]:
        if path.exists():
            docs.extend(SimpleDirectoryReader(path).load_data())
    logger.info("Loaded %d Document(s)", len(docs))

    # 2. Convert documents → nodes via pipeline
    try:
        nodes = INGEST_PIPELINE.run(documents=docs)
        logger.info("Generated %d Node(s)", len(nodes))
    except Exception:
        logger.exception("❌ Ingestion pipeline failed")
        raise

    # 3. Build vector index from nodes
    try:
        index = VectorStoreIndex(nodes=nodes, embed_model=None)
        index.storage_context.persist(persist_dir=str(INDEX_DIR))
        logger.info("✅ Index persisted to %s", INDEX_DIR)
    except Exception:
        logger.exception("❌ Index build/persist failed")
        raise

def get_index():
    """
    Loads or builds the stored VectorStoreIndex.
    """
    if not INDEX_DIR.exists() or not any(INDEX_DIR.iterdir()):
        logger.warning("Index missing — rebuilding via ingestion pipeline")
        embed_all()
    ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
    return load_index_from_storage(ctx)

def search(
    query: str,
    user_id: Optional[str] = None,
    k: int = 4,
    search_type: str = "all",
    score_threshold: Optional[float] = None,
) -> List[dict]:
    logger.info("[search] Called with query='%s', k=%d, user_id=%s", query, k, user_id)
    try:
        idx = get_index()
        logger.info("[search] Loaded index: %s", type(idx))
        query_engine = idx.as_query_engine(similarity_top_k=k)
        logger.info("[search] Created query_engine: %s", type(query_engine))
        results = query_engine.query(query)
        logger.info("[search] Query completed, got results type: %s", type(results))
        hits = []
        for node_with_score in getattr(results, "source_nodes", []):
            node = node_with_score.node
            score = node_with_score.score
            logger.info("[search] Hit: score=%.3f, text[0:30]='%s...'", score, node.text[:30].replace("\n", " "))
            if score_threshold and score < score_threshold:
                continue
            hits.append({
                "snippet": node.text,
                "score": score,
                "file": node.metadata.get("file_path"),
                "type": node.metadata.get("type"),
                "line": node.metadata.get("line_number"),
            })
        if search_type in ("code", "doc"):
            hits = [h for h in hits if h["type"] == search_type]
        logger.info("[search] Returning %d hits.", len(hits))
        return hits
    except Exception:
        logger.exception("Search failed")
        raise

def api_search(query: str, k: int = 4, search_type: str = "all"):
    return search(query, k=k, search_type=search_type)

def api_reindex():
    embed_all()
    return {"status": "ok", "message": "Re-index complete"}

def get_recent_summaries(user_id: str) -> list:
    """
    Stub for summary API compatibility.
    Replace this with actual per-user or global summary logic as needed.
    """
    return ["No summary implemented yet."]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        for h in search(" ".join(sys.argv[2:]) or "test"):
            print(f"{h['file']} (score={h['score']:.2f}): {h['snippet'][:120]}…")
    else:
        embed_all()
