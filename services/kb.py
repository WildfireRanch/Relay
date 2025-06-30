# ─────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Purpose: Full-featured semantic KB for LlamaIndex (robust chunking, tiering, filtering, search)
#           - Aggressive junk filtering & deduplication
#           - Tier-aware, content-boosted ranking
#           - Context-rich node metadata for intelligent agent answers
#           - CLI & debug
# Updated: 2025-06-30 (Debug hardening for startup hangs)
# ─────────────────────────────────────────────────────────────────────────────

import os
import json
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

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
logger.info("🔥 Robust KB loaded (Echo edition)")

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

# ─── Aggressive filtering ──────────────────────────────────────────────────
IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".env", ".DS_Store", ".gitignore",
    "poetry.lock", "Pipfile.lock", "requirements.txt", ".dockerignore",
    "Dockerfile", "Makefile", "tsconfig.json", "jsconfig.json", "node_modules",
    "README.md", "LICENSE", "Thumbs.db", "desktop.ini", "mypy.ini", "pyrightconfig.json",
}
IGNORED_EXTENSIONS = {
    ".lock", ".log", ".exe", ".bin", ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".ico",
    ".tgz", ".zip", ".tar", ".gz", ".mp4", ".mov", ".wav", ".pyc", ".so", ".dll",
}
IGNORED_FOLDERS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".venv", "env", ".mypy_cache", ".pytest_cache",
}
MAX_FILE_SIZE_MB = 2

def should_index_file(filepath: str, tier: str) -> bool:
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    if filename in IGNORED_FILENAMES or ext in IGNORED_EXTENSIONS:
        return False
    parts = filepath.replace("\\", "/").split("/")
    if any(folder in parts for folder in IGNORED_FOLDERS):
        return False
    if os.path.isfile(filepath):
        if os.path.getsize(filepath) > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False
    if tier == "code":
        return ext in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cpp", ".json", ".md"}
    return True

# ─── Index cache ───────────────────────────────────────────────────────────
_INDEX_CACHE: Optional[VectorStoreIndex] = None

# ─── Scrub any stale model folders ─────────────────────────────────────────
for path in INDEX_ROOT.iterdir():
    if path.is_dir() and path.name != MODEL_NAME:
        logger.warning("Removing stale index folder %s", path)
        shutil.rmtree(path, ignore_errors=True)

# ─── Ingestion pipeline ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend", "services", "routes")]
DOCS_DIR = ROOT.parent / "docs"
CHUNK_SIZE, CHUNK_OVERLAP = 1024, 200

INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(llm=None),
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

EXPECTED_DIM = None  # placeholder

def ensure_vector_dim_initialized():
    global EXPECTED_DIM
    if EXPECTED_DIM is None:
        EXPECTED_DIM = _vector_dim_current()

# ─── Public helpers ────────────────────────────────────────────────────────
def index_is_valid() -> bool:
    stored = _vector_dim_stored()
    valid = stored == EXPECTED_DIM and stored > 0
    logger.info("[index_is_valid] stored=%s current=%d → %s", stored, EXPECTED_DIM, valid)
    return valid

def embed_all(verbose: bool = False) -> None:
    """Rebuild the full semantic index, applying file exclusion and content deduplication."""
    logger.info("📚 Re-indexing KB with model %s", MODEL_NAME)

    docs: List = []
    tier_paths = [
        ("global", [DOCS_DIR / "generated/global_context.md", DOCS_DIR / "generated/global_context.auto.md"]),
        ("context", [ROOT.parent / "context/"]),
        ("project_summary", [
            DOCS_DIR / "PROJECT_SUMMARY.md",
            DOCS_DIR / "RELAY_CODE_UPDATE.md",
            DOCS_DIR / "context-commandcenter.md"
        ]),
        ("project_docs", [DOCS_DIR / "imported/", DOCS_DIR / "kb/", DOCS_DIR.glob("*.md")]),
        ("code", CODE_DIRS),
    ]

    # Aggressively filter and tag all docs with tier/metadata
    for tier, paths in tier_paths:
        for path in paths:
            # Folder: Use LlamaIndex reader (recursively)
            if isinstance(path, Path) and path.is_dir():
                docs_ = SimpleDirectoryReader(str(path), recursive=True).load_data() if path.exists() else []
                docs_ = [d for d in docs_ if should_index_file(
                    d.metadata.get("file_path") or d.metadata.get("filename") or "", tier)]
                for d in docs_:
                    d.metadata = d.metadata or {}
                    d.metadata["tier"] = tier
                docs.extend(docs_)
            # Glob or single file
            elif hasattr(path, "__iter__") and not isinstance(path, str):
                for f in path:
                    if f and os.path.isfile(f) and should_index_file(str(f), tier):
                        with open(f, "r", encoding="utf-8") as file:
                            text = file.read()
                        from llama_index.core import Document
                        doc = Document(text=text, metadata={"tier": tier, "file_path": str(f)})
                        docs.append(doc)
            elif isinstance(path, Path) and path.is_file():
                if should_index_file(str(path), tier):
                    with open(path, "r", encoding="utf-8") as file:
                        text = file.read()
                    from llama_index.core import Document
                    doc = Document(text=text, metadata={"tier": tier, "file_path": str(path)})
                    docs.append(doc)

    # Deduplicate by file_path and text hash
    seen = set()
    deduped_docs = []
    import hashlib
    for d in docs:
        fp = d.metadata.get("file_path", "NOFILE")
        content_hash = hashlib.md5(d.text.encode("utf-8")).hexdigest()
        key = (fp, content_hash)
        if key not in seen:
            seen.add(key)
            deduped_docs.append(d)
    docs = deduped_docs

    # ─── NEW: Debug output for document loading ───────────────
    logger.info(f"[KB] Docs loaded for indexing: {len(docs)}")
    for d in docs[:5]:
        logger.info(f"[KB] Sample doc: {d.metadata.get('file_path')} ({len(d.text)} chars)")
    if len(docs) == 0:
        logger.error("[KB] No valid docs to index! Aborting index build to avoid hang.")
        raise RuntimeError("No valid docs for KB index. Please check your docs/code directory population.")

    # ─── NEW: Wrap embedding in try/except for logging ────────
    try:
        nodes = INGEST_PIPELINE.run(documents=docs)
    except Exception as e:
        logger.exception("[KB] Failed in INGEST_PIPELINE.run")
        raise

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
    explain: bool = False,
    min_global: int = 1,
) -> List[dict]:
    """
    Tier-priority semantic search: returns top results ordered by tier.
    - Always tries to surface global/context/project summary results first.
    - Still returns code/project_docs if more space is available.
    - Junk/unknown tier results are de-prioritized unless nothing else is found.
    """
    PRIORITY_TIERS = [
        "global", "context", "project_summary", "project_docs", "code",
    ]

    qe = get_index().as_query_engine(similarity_top_k=k * 3)
    raw = qe.query(query)
    tiered: Dict[str, List[Any]] = {tier: [] for tier in PRIORITY_TIERS}
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
            "meta": n.node.metadata,
        }
        if tier in PRIORITY_TIERS:
            tiered[tier].append(hit)
        else:
            unknown.append(hit)

    # 1. First, fill with all global/context/summary docs, up to at least min_global if available
    prioritized = []
    for tier in ["global", "context", "project_summary"]:
        prioritized.extend(tiered[tier][:k])
    if len(prioritized) < min_global:
        for tier in ["project_docs"]:
            prioritized.extend(tiered[tier][:k - len(prioritized)])
    if len(prioritized) < k:
        prioritized.extend(tiered["code"][:k - len(prioritized)])
    if len(prioritized) < k:
        prioritized.extend(unknown[:(k - len(prioritized))])

    # Remove exact duplicates (by snippet or file path)
    seen = set()
    out = []
    for h in prioritized:
        key = (h["snippet"], h["path"])
        if key not in seen:
            seen.add(key)
            out.append(h)

    # If explain, add debug info
    if explain:
        print("[KB Search Debug]")
        for idx, h in enumerate(out):
            print(f"{idx+1:2d}. {h['tier']}: {h['title']} (score={h['similarity']:.3f})")
            print(f"    Path: {h['path']}")
            print(f"    Snippet: {h['snippet'][:200].replace(chr(10),' ')}")
        print(f"\nReturned {len(out)} results (out of {len(prioritized)})")

    return out[:k]

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query=query, k=k, search_type=search_type)

def query_index(query: str, k: int = 4) -> str:
    """Return formatted search snippets for a query."""
    results = search(query, k=k)
    return "\n\n".join(f"{r['title']}:\n{r['snippet']}" for r in results)

def api_reindex(verbose: bool = False) -> dict:
    global _INDEX_CACHE
    embed_all(verbose=verbose)
    _INDEX_CACHE = None
    return {
        "status": "ok",
        "message": "Re-index complete",
        "index_dir": str(INDEX_DIR),
        "model": MODEL_NAME,
    }

def get_recent_summaries(user_id: str) -> list[str]:
    return ["No summary implemented yet."]

# ─── CLI tools & debugging ─────────────────────────────────────────────────
def _kb_cli():
    import sys
    import time
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "test"
        print(f"\n[KB CLI] Query: {q}\n")
        t0 = time.time()
        hits = search(q, k=10, explain=True)
        print(f"⏱️  Search time: {time.time() - t0:.2f}s\n")
        for h in hits:
            print(f"{h['title']} (score={h['similarity']:.2f}): {h['snippet'][:120].replace(chr(10),' ')}…")
    else:
        print("[KB CLI] Rebuilding index...")
        embed_all(verbose=True)
        print("Index rebuild complete.")

if __name__ == "__main__":
    _kb_cli()
