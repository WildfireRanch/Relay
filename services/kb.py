# ──────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Purpose: Deterministic, well-logged knowledge-base ingestion & embedding.
#
# Highlights:
#   • Single source of truth for file filters (names/exts/folders/size)
#   • Structured skip/warn logs with optional core.logging.log_event fallback
#   • Model + dimension normalization and index-dimension guardrail
#   • Never raises unhandled exceptions during embed/build; returns status dict
#   • Simple module CLI: `python -m services.kb [embed|health|search "..."]`
#
# Safe to run locally (Codespaces) or remotely (Railway job).
# Dependencies: llama-index (VectorStoreIndex, StorageContext), openai (if used).
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ── Config fallbacks (do not import heavy modules at import-time) ─────────────
# If your project already defines these, we use them; else default under ./.data
try:
    from services.config import INDEX_DIR as _INDEX_DIR, INDEX_ROOT as _INDEX_ROOT  # type: ignore
except Exception:
    _INDEX_ROOT = Path(".data/index").resolve()
    _INDEX_DIR = _INDEX_ROOT

INDEX_ROOT: Path = Path(os.getenv("INDEX_ROOT", str(_INDEX_ROOT))).resolve()
INDEX_DIR: Path = Path(os.getenv("INDEX_DIR", str(_INDEX_DIR))).resolve()
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Where your docs and code live (adjust if your repo uses different paths)
PROJECT_ROOT = Path(os.getenv("RELAY_PROJECT_ROOT", Path(".").resolve()))
DEFAULT_DOC_DIRS = [PROJECT_ROOT / "docs", PROJECT_ROOT / "README.md"]
DEFAULT_CODE_DIRS = [PROJECT_ROOT / "agents", PROJECT_ROOT / "services", PROJECT_ROOT / "routes", PROJECT_ROOT / "core"]

# ── Logging (fallback to stdlib if core.logging unavailable) ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("services.kb")

try:
    # Optional, lightweight structured logger
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Fallback no-op structured logger."""
        return

logger.info("🔎 KB module loaded | INDEX_DIR=%s", INDEX_DIR)

# ── Embedding model normalization & dimensions ────────────────────────────────
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)

# Map common OpenAI embedding models to expected dimensions.
# You can extend this if you swap providers.
MODEL_DIMS: Dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    # legacy:
    "text-embedding-ada-002": 1536,
}

# Allow explicit override via env (for custom providers)
_EXPECTED_DIM_ENV = os.getenv("KB_EMBED_DIM")
EXPECTED_DIM: Optional[int] = int(_EXPECTED_DIM_ENV) if _EXPECTED_DIM_ENV else MODEL_DIMS.get(MODEL_NAME)

logger.info("[KB] Embedding model=%s dim=%s", MODEL_NAME, EXPECTED_DIM)
log_event("kb_model_selected", {"model": MODEL_NAME, "dim": EXPECTED_DIM})

# ── Filter rules: single source of truth used by all ingestion paths ─────────
IGNORED_FILENAMES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".env", ".env.local", ".DS_Store", ".gitignore",
    "poetry.lock", "Pipfile.lock", "requirements.txt",
    ".dockerignore", "Dockerfile", "Makefile",
    "tsconfig.json", "jsconfig.json",
    "Thumbs.db", "desktop.ini", "mypy.ini", "pyrightconfig.json",
}
IGNORED_EXTENSIONS: set[str] = {
    ".lock", ".log", ".exe", ".bin", ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".ico",
    ".tgz", ".zip", ".tar", ".gz", ".mp4", ".mov", ".wav", ".mp3", ".pyc", ".so", ".dll",
}
IGNORED_FOLDERS: set[str] = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".venv", "env",
    ".mypy_cache", ".pytest_cache",
}
MAX_FILE_SIZE_MB: int = int(os.getenv("KB_MAX_FILE_SIZE_MB", "2"))

def _log_skip(path: str, tier: str, reason: str) -> None:
    """Log a structured skip/warn so we never drop files silently."""
    logger.warning("[KB:skip] %s (%s): %s", path, tier, reason)
    log_event("kb_skip_file", {"path": path, "tier": tier, "reason": reason})

def should_index_file(filepath: str, tier: str) -> bool:
    """
    Canonical file gating:
      • skip ignored filenames, extensions, and folders
      • skip files larger than MAX_FILE_SIZE_MB
      • for tier='code' restrict to code-y extensions
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    if filename in IGNORED_FILENAMES or ext in IGNORED_EXTENSIONS:
        return False

    # Folder-based exclusions
    parts = filepath.replace("\\", "/").split("/")
    if any(folder in parts for folder in IGNORED_FOLDERS):
        return False

    # Size limit
    try:
        if os.path.isfile(filepath):
            if os.path.getsize(filepath) > MAX_FILE_SIZE_MB * 1024 * 1024:
                return False
    except OSError:
        return False

    if tier == "code":
        return ext in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cpp", ".json", ".md"}
    return True

# ── LlamaIndex imports (lazy to keep import-time light) ──────────────────────
# Use delayed import so unit tests can monkeypatch config easily
def _llama_imports():
    from llama_index.core import Document, StorageContext, VectorStoreIndex, load_index_from_storage
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.extractors import TitleExtractor
    from llama_index.core.embeddings import resolve_embed_model
    return Document, StorageContext, VectorStoreIndex, load_index_from_storage, IngestionPipeline, SentenceSplitter, TitleExtractor, resolve_embed_model

# ── Persistent dimension sidecar (guards mismatched indices) ─────────────────
DIM_FILE = INDEX_DIR / "dim.json"

def _write_dim_meta(dim: int) -> None:
    DIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIM_FILE.write_text(json.dumps({"dim": dim, "model": MODEL_NAME, "ts": int(time.time())}, indent=2), encoding="utf-8")

def _read_dim_meta() -> Optional[Dict[str, Any]]:
    if not DIM_FILE.exists():
        return None
    try:
        return json.loads(DIM_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

def _index_dim_matches_expected() -> bool:
    meta = _read_dim_meta()
    if meta is None:
        logger.info("[KB] No dim.json present")
        return EXPECTED_DIM is None  # if unknown expected, allow pass-through
    stored = meta.get("dim")
    if EXPECTED_DIM is None:
        # We don't know expected (custom model). Assume compatible.
        logger.warning("[KB] EXPECTED_DIM not set; accepting stored dim=%s (model=%s)", stored, meta.get("model"))
        return True
    ok = int(stored or -1) == int(EXPECTED_DIM)
    if not ok:
        logger.error("[KB] Index dim mismatch: stored=%s current=%s model_now=%s model_then=%s",
                     stored, EXPECTED_DIM, MODEL_NAME, meta.get("model"))
        log_event("kb_dim_mismatch", {"stored": stored, "expected": EXPECTED_DIM, "model_now": MODEL_NAME, "model_then": meta.get("model")})
    return ok

# ── Ingestion inputs (docs + code) ───────────────────────────────────────────
@dataclass
class TierSpec:
    name: str
    paths: List[Path]  # can include files or directories

def _discover_default_tiers() -> List[TierSpec]:
    code = [p for p in DEFAULT_CODE_DIRS if p.exists()]
    docs = []
    for p in DEFAULT_DOC_DIRS:
        if Path(p).exists():
            docs.append(Path(p))
    return [
        TierSpec("code", code),
        TierSpec("project_docs", docs),
    ]

def _iter_docs(tiers: Optional[List[TierSpec]] = None) -> List[Any]:
    """
    Walk targets and return Document objects with proper metadata:
      • Never throw; log structured reasons for skips
      • Only include files that pass should_index_file
    """
    Document, *_ = _llama_imports()
    docs: List[Any] = []
    tiers = tiers or _discover_default_tiers()

    for spec in tiers:
        tier = spec.name
        for path in spec.paths:
            try:
                if path.is_dir():
                    for f in path.rglob("*"):
                        if f.is_file():
                            fpath = str(f)
                            if should_index_file(fpath, tier):
                                try:
                                    text = f.read_text(encoding="utf-8")
                                except Exception as e:
                                    _log_skip(fpath, tier, f"unreadable: {e.__class__.__name__}")
                                    continue
                                docs.append(Document(text=text, metadata={"tier": tier, "file_path": fpath}))
                            else:
                                _log_skip(fpath, tier, "filtered by rules")
                elif path.is_file():
                    fpath = str(path)
                    if should_index_file(fpath, tier):
                        try:
                            text = path.read_text(encoding="utf-8")
                        except Exception as e:
                            _log_skip(fpath, tier, f"unreadable: {e.__class__.__name__}")
                            continue
                        docs.append(Document(text=text, metadata={"tier": tier, "file_path": fpath}))
                    else:
                        _log_skip(fpath, tier, "filtered by rules")
                else:
                    _log_skip(str(path), tier, "not found")
            except Exception as e:
                _log_skip(str(path), tier, f"walker error: {e.__class__.__name__}")
                continue
    return docs

# ── Index building & loading (exception-safe) ────────────────────────────────
def _resolve_embed_model():
    *_, resolve_embed_model = _llama_imports()
    # LlamaIndex will choose OpenAI embedder based on model string.
    # Ensure OPENAI_API_KEY is present when using OpenAI models.
    return resolve_embed_model(MODEL_NAME)

def _pipeline():
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.extractors import TitleExtractor
    return IngestionPipeline(
        transformations=[
            SentenceSplitter(chunk_size=1000, chunk_overlap=100),
            TitleExtractor(nodes=5),
        ]
    )

def _maybe_wipe_index() -> None:
    if os.getenv("WIPE_INDEX") == "1":
        logger.warning("[KB] WIPE_INDEX=1 → removing %s", INDEX_DIR)
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)

def embed_all(verbose: bool = False, tiers: Optional[List[TierSpec]] = None) -> Dict[str, Any]:
    """
    Rebuild the full KB index.
    • Never raises to caller; returns status dict {ok, error, model, indexed}
    • Logs dimension metadata to sidecar for future guardrails
    """
    try:
        _maybe_wipe_index()
        EMBED_MODEL = _resolve_embed_model()
        INGEST_PIPELINE = _pipeline()

        logger.info("📚 Re-indexing KB | model=%s dim=%s", MODEL_NAME, EXPECTED_DIM)
        docs = _iter_docs(tiers=tiers)
        logger.info("[KB] Docs loaded: %s", len(docs))
        for d in docs[:5]:
            fp = (d.metadata or {}).get("file_path")
            logger.info("[KB] sample → %s", fp)

        if len(docs) == 0:
            msg = "No valid docs for KB index. Populate docs/code directories."
            logger.error("[KB] %s", msg)
            log_event("kb_index_empty", {"model": MODEL_NAME})
            return {"ok": False, "error": msg, "model": MODEL_NAME, "indexed": 0}

        t0 = time.time()
        nodes = _pipeline().run(documents=docs)
        logger.info("[KB] Nodes generated: %s", len(nodes))

        # Build & persist
        from llama_index.core import VectorStoreIndex, StorageContext
        index = VectorStoreIndex(nodes=nodes, embed_model=EMBED_MODEL)
        index.storage_context.persist(persist_dir=str(INDEX_DIR))
        _write_dim_meta(int(EXPECTED_DIM or 0))
        dt = time.time() - t0

        logger.info("✅ Index persisted → %s (%.2fs)", INDEX_DIR, dt)
        log_event("kb_index_built", {"model": MODEL_NAME, "docs": len(docs), "seconds": round(dt, 2)})
        return {"ok": True, "error": None, "model": MODEL_NAME, "indexed": len(docs)}
    except Exception as e:
        logger.exception("[KB] Ingest/index build failed")
        log_event("kb_index_build_fail", {"model": MODEL_NAME, "error": str(e)})
        return {"ok": False, "error": str(e), "model": MODEL_NAME, "indexed": 0}

def index_is_valid() -> bool:
    """Return True if an on-disk index exists and dimension matches expectation."""
    # quick existence check
    if not INDEX_DIR.exists() or not any(INDEX_DIR.glob("*")):
        logger.info("[KB] index_is_valid → missing storage")
        return False
    return _index_dim_matches_expected()

def get_index():
    """
    Load (or rebuild once) and return a VectorStoreIndex.
    Never leaves the index unusable; performs one rebuild attempt on errors.
    """
    from llama_index.core import StorageContext, load_index_from_storage
    EMBED_MODEL = _resolve_embed_model()

    try:
        if not index_is_valid():
            status = embed_all()
            if not status.get("ok"):
                logger.error("[KB] embed_all() returned error: %s", status.get("error"))
                log_event("kb_load_invalid_after_embed", {"error": status.get("error")})
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        return load_index_from_storage(ctx, embed_model=EMBED_MODEL)
    except Exception:
        logger.exception("[KB] load_index_from_storage failed — wiping and rebuilding once")
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        status = embed_all()
        if not status.get("ok"):
            logger.error("[KB] embed_all() after wipe returned error: %s", status.get("error"))
            log_event("kb_load_rebuild_fail", {"error": status.get("error")})
            # return a sentinel None rather than throwing
            return None
        from llama_index.core import StorageContext, load_index_from_storage
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        return load_index_from_storage(ctx, embed_model=_resolve_embed_model())

# ── Simple search helper (for manual testing / CLI) ──────────────────────────
def simple_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    index = get_index()
    if index is None:
        return []
    try:
        engine = index.as_query_engine(similarity_top_k=top_k)
        res = engine.query(query)
        # Normalize result to a friendly list
        results: List[Dict[str, Any]] = []
        for n in getattr(res, "source_nodes", []) or []:
            meta = getattr(n, "node", {}).metadata if hasattr(n, "node") else {}
            results.append({
                "score": getattr(n, "score", None),
                "file_path": (meta or {}).get("file_path"),
                "tier": (meta or {}).get("tier"),
                "preview": (getattr(n, "text", "") or "")[:300],
            })
        return results
    except Exception as e:
        logger.exception("[KB] simple_search failed: %s", e)
        return []
    # Add near the bottom of services/kb.py (below simple_search)

def search(query: str, top_k: int = 5):
    """
    Back-compat shim for older callers expecting `services.kb.search`.
    Returns a list of {score,file_path,tier,preview} dicts.
    """
    return simple_search(query, top_k=top_k)

def api_search(query: str, k: int = 5, search_type: str | None = None):
    """
    Back-compat shim for routes/kb.search proxy. Ignores `search_type`
    and delegates to simple_search for now.
    """
    return simple_search(query, top_k=k)


# ── Module CLI ───────────────────────────────────────────────────────────────
def _cli(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Relay KB ingestion")
    sub = parser.add_subparsers(dest="cmd", required=False)

    sub.add_parser("embed", help="(Re)build the KB index")
    sub.add_parser("health", help="Check index presence & dimension compatibility")

    p_search = sub.add_parser("search", help="Run a quick similarity search")
    p_search.add_argument("query", type=str, nargs="+", help="Query string")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args(argv or ["embed"])
    if args.cmd == "health":
        ok = index_is_valid()
        print(f"[kb] health: {ok} | model={MODEL_NAME} dim={EXPECTED_DIM} dir={INDEX_DIR}")
        return 0 if ok else 1

    if args.cmd == "search":
        q = " ".join(args.query)
        out = simple_search(q)
        print(json.dumps(out, indent=2))
        return 0

    # default: embed
    status = embed_all(verbose=args.verbose)
    if status.get("ok"):
        print(f"[kb] OK — model={status.get('model')} docs={status.get('indexed')}")
        return 0
    else:
        print(f"[kb] ERROR — {status.get('error')}", file=sys.stderr)
        return 1

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli(sys.argv[1:]))
