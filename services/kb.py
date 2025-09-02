# ─────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Purpose: Full-featured semantic KB (LlamaIndex) with robust chunking, tiering,
#          aggressive filtering/dedup, safe (re)index, kwarg-flex search, and a
#          definition extractor to guarantee answer-first behavior.
#
# Public API (unchanged):
#   - index_is_valid() -> bool
#   - embed_all(verbose: bool = False) -> None
#   - get_index() -> VectorStoreIndex
#   - search(query: str, k: int = 8, search_type: str = "all", score_threshold: Optional[float] = None, ...)
#   - api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]
#   - query_index(query: str, k: int = 4) -> str
#   - api_reindex(verbose: bool = False) -> dict
#   - definition_from_kb(query: str, k: int = 6, max_chars: int = 560) -> Optional[str]
#   - _kb_cli() for manual testing
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.config import INDEX_DIR, INDEX_ROOT

# LlamaIndex
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
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("🔥 Robust KB loaded (Echo edition)")

# ─── Model configuration ────────────────────────────────────────────────────
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)

# Ensure directories exist early
INDEX_ROOT.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Remove stale model subfolders so we don’t load wrong-dimension stores.
for path in INDEX_ROOT.iterdir():
    if path.is_dir() and path.name != MODEL_NAME:
        logger.warning("Removing stale index folder %s", path)
        shutil.rmtree(path, ignore_errors=True)

# Initialize embedding model (dimension-aware where applicable)
if MODEL_NAME == "text-embedding-3-large":
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME, dimensions=3072)
else:
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME)

# ─── Aggressive filtering ───────────────────────────────────────────────────
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
IGNORED_FOLDERS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "env", ".mypy_cache", ".pytest_cache"}
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
        try:
            if os.path.getsize(filepath) > MAX_FILE_SIZE_MB * 1024 * 1024:
                return False
        except OSError:
            return False
    if tier == "code":
        return ext in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cpp", ".json", ".md"}
    return True

# ─── Index cache & dimension helpers ────────────────────────────────────────
_INDEX_CACHE: Optional[VectorStoreIndex] = None
EXPECTED_DIM: Optional[int] = None
DIM_FILE = INDEX_DIR / "dim.json"  # sidecar to persist embed dim reliably

def _vector_dim_current() -> int:
    # Single call to avoid warmup thrash; guarded by try/except at caller.
    emb = EMBED_MODEL.get_text_embedding("dim_check")
    if isinstance(emb, list):
        return len(emb)
    try:
        return int(emb or 0)
    except Exception:
        return 0

def _vector_dim_stored() -> int:
    """
    Legacy best-effort probe of older vector store shapes.
    May return -1 on newer formats; that's OK (we'll use dim.json).
    """
    vs_file = INDEX_DIR / "vector_store.json"
    if not vs_file.exists():
        return -1
    try:
        store = json.loads(vs_file.read_text() or "{}")
        for rec in store.values():
            if isinstance(rec, dict) and isinstance(rec.get("embedding"), list):
                return len(rec["embedding"])
    except Exception as e:
        logger.warning("[vector_dim_stored] unable to read %s: %s", vs_file, e)
    return -1

def _write_dim_meta(dim: int) -> None:
    try:
        DIM_FILE.write_text(json.dumps({"dim": int(dim)}))
    except Exception as e:
        logger.warning("[dim_meta] write failed: %s", e)

def _read_dim_meta() -> int:
    try:
        if DIM_FILE.exists():
            data = json.loads(DIM_FILE.read_text() or "{}")
            return int(data.get("dim", -1))
    except Exception as e:
        logger.warning("[dim_meta] read failed: %s", e)
    return -1

def ensure_vector_dim_initialized() -> None:
    global EXPECTED_DIM
    if EXPECTED_DIM is None:
        try:
            EXPECTED_DIM = _vector_dim_current()
        except Exception as e:
            EXPECTED_DIM = -1
            logger.warning("Failed to initialize EXPECTED_DIM: %s", e)

ensure_vector_dim_initialized()

def _maybe_wipe_index() -> None:
    """Honor WIPE_INDEX=1 (or 'true') to force a fresh rebuild."""
    wipe = (os.getenv("WIPE_INDEX") or "").strip().lower()
    if wipe in {"1", "true", "yes"}:
        if INDEX_DIR.exists():
            logger.warning("WIPE_INDEX set — clearing %s", INDEX_DIR)
            shutil.rmtree(INDEX_DIR, ignore_errors=True)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)

# ─── Ingestion pipeline ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CODE_DIRS = [ROOT.parent / p for p in ("src", "backend", "frontend", "services", "routes")]
DOCS_DIR = ROOT.parent / "docs"
CHUNK_SIZE, CHUNK_OVERLAP = 1024, 200

# TitleExtractor takes an LLM by default; use None to avoid extra calls.
INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(llm=None),
        SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP),
        EMBED_MODEL,
    ]
)

# ─── Public helpers ────────────────────────────────────────────────────────
def index_is_valid() -> bool:
    """
    True if a persisted index exists and matches the current embedder dimension.
    Uses dim.json sidecar as source of truth; falls back to legacy probe.
    """
    ensure_vector_dim_initialized()
    stored = _read_dim_meta()
    if stored <= 0:
        stored = _vector_dim_stored()  # legacy fallback
    valid = stored > 0 and EXPECTED_DIM is not None and stored == EXPECTED_DIM
    logger.info("[index_is_valid] stored=%s current=%s → %s", stored, EXPECTED_DIM, valid)
    return valid

def _iter_docs() -> List[Any]:
    """
    Collect documents across tiers with aggressive filtering and consistent metadata.
    """
    docs: List = []
    tier_paths: List[Tuple[str, List[Any]]] = [
        ("global", [DOCS_DIR / "generated/global_context.md", DOCS_DIR / "generated/global_context.auto.md"]),
        ("context", [ROOT.parent / "context/"]),
        ("project_summary", [
            DOCS_DIR / "PROJECT_SUMMARY.md",
            DOCS_DIR / "RELAY_CODE_UPDATE.md",
            DOCS_DIR / "context-commandcenter.md",
        ]),
        ("project_docs", [DOCS_DIR / "imported/", DOCS_DIR / "kb/", DOCS_DIR.glob("*.md")]),
        ("code", CODE_DIRS),
    ]

    from llama_index.core import Document  # late import to keep module import light

    for tier, paths in tier_paths:
        for path in paths:
            try:
                # 1) Directory
                if isinstance(path, Path) and path.exists() and path.is_dir():
                    raw_docs = SimpleDirectoryReader(str(path), recursive=True).load_data()
                    for d in raw_docs:
                        fpath = (d.metadata or {}).get("file_path") or (d.metadata or {}).get("filename") or ""
                        if fpath and should_index_file(fpath, tier):
                            d.metadata = d.metadata or {}
                            d.metadata["tier"] = tier
                            docs.append(d)

                # 2) Glob (generator of Paths)
                elif hasattr(path, "__iter__") and not isinstance(path, (str, bytes, Path)):
                    for f in path:
                        if not f:
                            continue
                        fpath = str(f)
                        if os.path.isfile(fpath) and should_index_file(fpath, tier):
                            try:
                                text = Path(fpath).read_text(encoding="utf-8")
                                docs.append(Document(text=text, metadata={"tier": tier, "file_path": fpath}))
                            except Exception:
                                continue

                # 3) Single file
                elif isinstance(path, Path) and path.exists() and path.is_file():
                    fpath = str(path)
                    if should_index_file(fpath, tier):
                        try:
                            text = path.read_text(encoding="utf-8")
                            docs.append(Document(text=text, metadata={"tier": tier, "file_path": fpath}))
                        except Exception:
                            continue

            except Exception as e:
                logger.warning("[_iter_docs] Skipped %s (%s): %s", path, tier, e)
                continue

    # De-dupe by (path, content hash)
    seen = set()
    deduped = []
    for d in docs:
        fp = (d.metadata or {}).get("file_path", "NOFILE")
        h = hashlib.md5((d.text or "").encode("utf-8")).hexdigest()
        key = (fp, h)
        if key not in seen:
            seen.add(key)
            deduped.append(d)
    return deduped

def embed_all(verbose: bool = False) -> None:
    """Rebuild the full semantic index with filtering/dedup and safe logs."""
    _maybe_wipe_index()
    logger.info("📚 Re-indexing KB with model %s", MODEL_NAME)

    docs = _iter_docs()
    logger.info("[KB] Docs loaded for indexing: %s", len(docs))
    for d in docs[:5]:
        logger.info("[KB] Sample doc: %s (%s chars)", (d.metadata or {}).get("file_path"), len(d.text or ""))

    if len(docs) == 0:
        logger.error("[KB] No valid docs to index! Aborting index build.")
        raise RuntimeError("No valid docs for KB index. Populate docs/code directories.")

    try:
        t0 = time.time()
        nodes = INGEST_PIPELINE.run(documents=docs)
        logger.info("Generated %s vector nodes", len(nodes))
        index = VectorStoreIndex(nodes=nodes, embed_model=EMBED_MODEL)
        index.storage_context.persist(persist_dir=str(INDEX_DIR))
        # write dimension sidecar so index_is_valid is stable on future boots
        _write_dim_meta(EXPECTED_DIM or 0)
        logger.info("✅ Index persisted → %s (%.2fs)", INDEX_DIR, time.time() - t0)
    except Exception:
        logger.exception("[KB] Failed during ingest/index/persist")
        raise

def get_index() -> VectorStoreIndex:
    """
    Return the cached/loaded index, rebuilding if missing or mismatched.
    Safe against dimension mismatches and partial/corrupt stores.
    """
    global _INDEX_CACHE
    try:
        if _INDEX_CACHE is not None and index_is_valid():
            return _INDEX_CACHE
        if not index_is_valid():
            embed_all()
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        _INDEX_CACHE = load_index_from_storage(ctx, embed_model=EMBED_MODEL)
        return _INDEX_CACHE
    except Exception:
        # If loading failed (e.g., partial store), wipe and rebuild once
        logger.exception("[KB] load_index_from_storage failed — wiping and rebuilding once")
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        embed_all()
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        _INDEX_CACHE = load_index_from_storage(ctx, embed_model=EMBED_MODEL)
        return _INDEX_CACHE

# ─── Search (tier-aware + kwarg-flex) ───────────────────────────────────────
def search(
    query: str,
    k: int = 8,
    search_type: str = "all",
    score_threshold: Optional[float] = None,
    user_id: Optional[str] = None,
    explain: bool = False,
    min_global: int = 1,
    **kwargs: Any,  # accept extra kwargs from callers without blowing up
) -> List[Dict[str, Any]]:
    """
    Tier-priority semantic search: returns top results ordered by tier.
    - Prefers global/context/project_summary definitions first.
    - Returns project_docs/code if space remains.
    - Ignores unknown/junk unless nothing else is found.
    - Tolerates extra kwargs; ignores unsupported knobs.
    """
    PRIORITY_TIERS = ["global", "context", "project_summary", "project_docs", "code"]

    try:
        qe = get_index().as_query_engine(similarity_top_k=max(k * 3, 10))
        raw = qe.query(query)
    except Exception as e:
        logger.warning("[KB Search] query() failed: %s", e)
        return []

    # Normalize possible response shapes
    source_nodes = getattr(raw, "source_nodes", None)
    if source_nodes is None:
        return []

    tiered: Dict[str, List[Dict[str, Any]]] = {t: [] for t in PRIORITY_TIERS}
    unknown: List[Dict[str, Any]] = []

    for n in source_nodes:
        try:
            sim = float(getattr(n, "score", 0.0) or 0.0)
        except Exception:
            sim = 0.0
        if score_threshold is not None and sim < score_threshold:
            continue

        node = getattr(n, "node", None)
        meta = (getattr(node, "metadata", {}) or {}) if node else {}
        tier = meta.get("tier", "unknown")
        path = meta.get("file_path")
        title = meta.get("title") or path or "Untitled"
        snippet = getattr(node, "text", "") or ""

        hit = {
            "id": getattr(node, "node_id", None),
            "snippet": snippet,
            "similarity": sim,
            "tier": tier,
            "path": path,
            "title": title,
            "meta": meta,
        }
        (tiered if tier in tiered else unknown)[tier if tier in tiered else "unknown"].append(hit)

    # Heuristic: prefer definition-like snippets (“X is …”, “Overview”, “Summary”)
    def _def_boost(h: Dict[str, Any]) -> float:
        sn = (h.get("snippet") or "").strip().lower()
        ti = (h.get("title") or "").strip().lower()
        score = float(h.get("similarity") or 0.0)
        if " overview" in ti or "summary" in ti or "definition" in ti:
            score += 0.15
        if " is a " in sn or " is an " in sn or sn.startswith("relay command center is"):
            score += 0.10
        return score

    for t in tiered:
        tiered[t].sort(key=_def_boost, reverse=True)
    unknown.sort(key=_def_boost, reverse=True)

    prioritized: List[Dict[str, Any]] = []
    for t in ("global", "context", "project_summary"):
        prioritized.extend(tiered[t][:k])
    if len(prioritized) < max(min_global, k):
        prioritized.extend(tiered["project_docs"][: max(0, k - len(prioritized))])
    if len(prioritized) < k:
        prioritized.extend(tiered["code"][: max(0, k - len(prioritized))])
    if len(prioritized) < k:
        prioritized.extend(unknown[: max(0, k - len(prioritized))])

    # Dedup by (snippet, path)
    out, seen = [], set()
    for h in prioritized:
        key = ((h.get("snippet") or "").strip(), h.get("path"))
        if key not in seen and (h.get("snippet") or "").strip():
            seen.add(key)
            out.append(h)

    if explain:
        print("[KB Search Debug]")
        for idx, h in enumerate(out[:k]):
            print(f"{idx+1:2d}. {h['tier']}: {h['title']} (score={float(h['similarity']):.3f}) path={h['path']}")
            sn = (h['snippet'] or "").replace("\n", " ")
            print(f"    Snippet: {sn[:200]}")

    return out[:k]

def api_search(query: str, k: int = 4, search_type: str = "all") -> List[dict]:
    return search(query=query, k=k, search_type=search_type)

def query_index(query: str, k: int = 4) -> str:
    """Return formatted search snippets for a query."""
    results = search(query=query, k=k)
    return "\n\n".join(f"{r['title']}:\n{r['snippet']}" for r in results)

def api_reindex(verbose: bool = False) -> dict:
    global _INDEX_CACHE
    embed_all(verbose=verbose)
    _INDEX_CACHE = None
    return {"status": "ok", "message": "Re-index complete", "index_dir": str(INDEX_DIR), "model": MODEL_NAME}

def get_recent_summaries(user_id: str) -> List[str]:
    # Placeholder (explicitly not implemented yet)
    return ["No summary implemented yet."]

# ─── “No-parrot guarantee” helper for Echo/Planner ─────────────────────────
_DEF_PREFIXES = ("what is", "who is", "define", "describe")

def definition_from_kb(query: str, k: int = 6, max_chars: int = 560) -> Optional[str]:
    """
    Synthesize a 2–4 sentence definition directly from KB results.
    Used when LLM parrots (“Define what …”) or Planner missed final_answer.
    Deterministic, short, and non-parroting.
    """
    hits = search(query=query, k=max(k, 6), min_global=1)
    if not hits:
        return None

    def _score_def(h: Dict[str, Any]) -> float:
        # Boost obvious definition-y material
        s = (h.get("snippet") or "").strip().lower()
        t = (h.get("title") or "").strip().lower()
        base = float(h.get("similarity") or 0.0)
        if " overview" in t or "summary" in t or "definition" in t:
            base += 0.20
        if " is a " in s or " is an " in s:
            base += 0.15
        if s.startswith("relay command center is"):
            base += 0.25
        return base

    hits.sort(key=_score_def, reverse=True)

    # Try up to three candidates to avoid pulling a parrot-ish first sentence
    import re
    for cand_hit in hits[:3]:
        cand = (cand_hit.get("snippet") or "").strip()
        if not cand:
            continue
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cand) if s.strip()]
        if not sents:
            continue
        out = " ".join(sents[:4]).strip()
        if len(out) > max_chars:
            out = out[:max_chars].rstrip() + "…"
        if not out:
            continue
        # Avoid outputs that start with directive verbs (parrot-ish)
        if out.lower().startswith(_DEF_PREFIXES):
            continue
        return out

    return None

# ─── CLI tools & debugging ──────────────────────────────────────────────────
def _kb_cli():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:]) or "test"
        print(f"\n[KB CLI] Query: {q}\n")
        t0 = time.time()
        hits = search(query=q, k=10, explain=True)  # fixed: use query kwarg
        print(f"⏱️  Search time: {time.time() - t0:.2f}s\n")
        for h in hits:
            sn = (h['snippet'] or "").replace("\n", " ")
            print(f"{h['title']} (score={float(h['similarity']):.2f}): {sn[:120]}…")
    elif len(sys.argv) > 1 and sys.argv[1] == "define":
        q = " ".join(sys.argv[2:]) or "What is Relay Command Center?"
        print(f"\n[KB CLI] Define: {q}\n")
        ans = definition_from_kb(q) or "[no definition found]"
        print(ans)
    else:
        print("[KB CLI] Rebuilding index...")
        embed_all(verbose=True)
        print("Index rebuild complete.")

if __name__ == "__main__":
    _kb_cli()
