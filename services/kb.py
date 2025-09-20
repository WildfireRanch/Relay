# ──────────────────────────────────────────────────────────────────────────────
# File: services/kb.py
# Purpose: Deterministic, well-logged knowledge-base ingestion & embedding.
#
# Guarantees
#   • api_reindex() returns a stable JSON shape and never raises.
#   • Index dimension guardrail via dim.json; logs and tolerates mismatches.
#   • Avoids heavy imports at module import time (lazy LlamaIndex imports).
#   • Works with/without a concrete semantic indexer (graceful fallback).
#   • CLI: python -m services.kb [embed|health|search "..."]
#
# Public API (kept stable for routes and services):
#   - api_reindex(*, tiers=None, verbose=False) -> Dict[str, Any]
#   - embed_all(verbose=False, tiers=None) -> Dict[str, Any]
#   - index_is_valid() -> bool
#   - get_index() -> VectorStoreIndex|None
#   - simple_search(query, top_k=5, score_threshold=None) -> List[Dict]
#   - search(query=..., k/top_k=..., score_threshold=None, **kwargs) -> List[Dict]
#   - api_search(query, k=5, search_type=None) -> List[Dict]
#   - warmup() -> None
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

# ── Stdlib --------------------------------------------------------------------
import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("services.kb")

# Optional structured logger shim
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        return


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Paths & Config (lightweight; no heavy imports here)                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# Correct default is ./data/index (NOT .data/index)
ENV_INDEX_ROOT = os.getenv("INDEX_ROOT")
_INDEX_ROOT_FALLBACK = Path("./data/index").resolve()

try:
    from services.config import INDEX_DIR as _CFG_INDEX_DIR, INDEX_ROOT as _CFG_INDEX_ROOT  # type: ignore
except Exception:
    _CFG_INDEX_ROOT = _INDEX_ROOT_FALLBACK
    _CFG_INDEX_DIR = _CFG_INDEX_ROOT

INDEX_ROOT: Path = Path(ENV_INDEX_ROOT or str(_CFG_INDEX_ROOT)).resolve()
INDEX_DIR: Path = Path(os.getenv("INDEX_DIR", str(_CFG_INDEX_DIR))).resolve()
INDEX_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT = Path(os.getenv("RELAY_PROJECT_ROOT") or Path(".").resolve())
DEFAULT_DOC_DIRS = [PROJECT_ROOT / "docs", PROJECT_ROOT / "README.md"]
DEFAULT_CODE_DIRS = [
    PROJECT_ROOT / "agents",
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "routes",
    PROJECT_ROOT / "core",
]

logger.info("🔎 KB module loaded | INDEX_DIR=%s INDEX_ROOT=%s", INDEX_DIR, INDEX_ROOT)

# Embedding model and dimensions
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")  # back-compat
    or "text-embedding-3-large"
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDINGS_MODEL = os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")

MODEL_DIMS: Dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    # legacy:
    "text-embedding-ada-002": 1536,
}
_EXPECTED_DIM_ENV = os.getenv("KB_EMBED_DIM")
EXPECTED_DIM: Optional[int] = int(_EXPECTED_DIM_ENV) if _EXPECTED_DIM_ENV else MODEL_DIMS.get(MODEL_NAME)

logger.info("[KB] Embedding model=%s dim=%s", MODEL_NAME, EXPECTED_DIM)
log_event("kb_model_selected", {"model": MODEL_NAME, "dim": EXPECTED_DIM})

# File filters (single source of truth)
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

def _should_index_file(filepath: str, tier: str) -> bool:
    """
    Canonical file gating:
      • skip ignored filenames, extensions, and folders
      • skip files larger than MAX_FILE_SIZE_MB
      • for tier='code' restrict to code-centric extensions
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    if filename in IGNORED_FILENAMES or ext in IGNORED_EXTENSIONS:
        return False

    parts = filepath.replace("\\", "/").split("/")
    if any(folder in parts for folder in IGNORED_FOLDERS):
        return False

    try:
        if os.path.isfile(filepath) and os.path.getsize(filepath) > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False
    except OSError:
        return False

    if tier == "code":
        return ext in {".py", ".js", ".ts", ".tsx", ".java", ".go", ".cpp", ".json", ".md"}
    return True

def _log_skip(path: str, tier: str, reason: str) -> None:
    logger.warning("[KB:skip] %s (%s): %s", path, tier, reason)
    log_event("kb_skip_file", {"path": path, "tier": tier, "reason": reason})


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Lazy LlamaIndex imports                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _llama_imports():
    """
    Import LlamaIndex lazily to keep module import cheap.
    """
    from llama_index.core import Document, StorageContext, VectorStoreIndex, load_index_from_storage
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.extractors import TitleExtractor
    from llama_index.core.embeddings import resolve_embed_model
    return (
        Document,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
        IngestionPipeline,
        SentenceSplitter,
        TitleExtractor,
        resolve_embed_model,
    )

def _resolve_embed_model():
    """
    Try LlamaIndex resolver first. If it fails and OPENAI_API_KEY is set,
    fall back to OpenAIEmbedding.
    """
    *_, resolve_embed_model = _llama_imports()
    try:
        return resolve_embed_model(MODEL_NAME)
    except Exception as e_resolve:
        try:
            if not OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY not set for OpenAI fallback")
            from llama_index.embeddings.openai import OpenAIEmbedding  # lazy
            emb = OpenAIEmbedding(model=OPENAI_EMBEDDINGS_MODEL, api_key=OPENAI_API_KEY)
            log_event("kb_embeddings_fallback", {"from_model": MODEL_NAME, "to_model": OPENAI_EMBEDDINGS_MODEL})
            return emb
        except Exception as e_openai:
            raise RuntimeError(
                f"Failed to resolve embeddings for MODEL_NAME={MODEL_NAME}; "
                f"resolver_error={e_resolve}; openai_fallback_error={e_openai}"
            )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Dimension sidecar (dim.json)                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

DIM_FILE = INDEX_DIR / "dim.json"

def _write_dim_meta(dim: int) -> None:
    DIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIM_FILE.write_text(
        json.dumps({"dim": dim, "model": MODEL_NAME, "ts": int(time.time())}, indent=2),
        encoding="utf-8",
    )

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
        logger.warning("[KB] EXPECTED_DIM not set; accepting stored dim=%s (model=%s)", stored, meta.get("model"))
        return True
    ok = int(stored or -1) == int(EXPECTED_DIM)
    if not ok:
        logger.error(
            "[KB] Index dim mismatch: stored=%s current=%s model_now=%s model_then=%s",
            stored, EXPECTED_DIM, MODEL_NAME, meta.get("model"),
        )
        log_event(
            "kb_dim_mismatch",
            {"stored": stored, "expected": EXPECTED_DIM, "model_now": MODEL_NAME, "model_then": meta.get("model")},
        )
    return ok


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Ingestion (discover → read → Document[])                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass
class TierSpec:
    name: str
    paths: List[Path]  # can include files or directories

def _discover_default_tiers() -> List[TierSpec]:
    code = [p for p in DEFAULT_CODE_DIRS if p.exists()]
    docs = [Path(p) for p in DEFAULT_DOC_DIRS if Path(p).exists()]
    return [TierSpec("code", code), TierSpec("project_docs", docs)]

def _iter_docs(tiers: Optional[List[TierSpec]] = None) -> List[Any]:
    """
    Walk targets and return Document objects with proper metadata.
    Never raises; logs structured reasons for skips.
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
                        if not f.is_file():
                            continue
                        fpath = str(f)
                        if _should_index_file(fpath, tier):
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
                    if _should_index_file(fpath, tier):
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


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Index persistence (build/load)                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

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
    Returns a normalized dict:
      {"ok": bool, "error": str|None, "model": str, "indexed": int}
    """
    try:
        _maybe_wipe_index()
        EMBED_MODEL = _resolve_embed_model()
        INGEST_PIPELINE = _pipeline()

        logger.info("📚 Re-indexing KB | model=%s dim=%s", MODEL_NAME, EXPECTED_DIM)
        docs = _iter_docs(tiers=tiers)
        logger.info("[KB] Docs loaded: %s", len(docs))
        if verbose:
            for d in docs[:5]:
                fp = (d.metadata or {}).get("file_path")
                logger.info("[KB] sample → %s", fp)

        if len(docs) == 0:
            msg = "No valid docs for KB index. Populate docs/code directories."
            logger.error("[KB] %s", msg)
            log_event("kb_index_empty", {"model": MODEL_NAME})
            return {"ok": False, "error": msg, "model": MODEL_NAME, "indexed": 0}

        t0 = time.time()
        nodes = INGEST_PIPELINE.run(documents=docs)
        logger.info("[KB] Nodes generated: %s", len(nodes))

        from llama_index.core import VectorStoreIndex
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


def api_reindex(
    *,
    tiers: Optional[List[TierSpec]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    API-friendly wrapper around embed_all() with a stable response shape.
    Never raises.
    Returns:
      {
        "ok": true|false,
        "status": "done"|"error",
        "indexed": <int>,
        "model": "<name>",
        "took_ms": <int>,
        "error": "<str>"? ,
        "note": "<str>"?     # present when indexer is absent or no-op
      }
    """
    t0 = time.perf_counter()

    # Prefer a concrete semantic indexer if you have one wired
    # (kept for compatibility; we normalize its output below).
    indexer_result = None
    indexer_error: Optional[Exception] = None
    try:  # pragma: no cover
        from services.semantic_retriever import reindex_all as _reindex_all  # type: ignore
        indexer_result = _reindex_all(root=str(INDEX_DIR))  # kwarg helps clarity
    except Exception as e:  # noqa: E722 - intentional broad catch; normalize below
        indexer_error = e
        # Fall back to embed_all below.

    if indexer_result is not None and indexer_error is None:
        # Best-effort normalization for custom indexers
        took_ms = int((time.perf_counter() - t0) * 1000)
        counts = {}
        if isinstance(indexer_result, dict):
            docs = indexer_result.get("documents") or indexer_result.get("doc_count") or indexer_result.get("files")
            chks = indexer_result.get("chunks") or indexer_result.get("chunk_count")
            if isinstance(docs, int):
                counts["documents"] = docs
            if isinstance(chks, int):
                counts["chunks"] = chks
        return {
            "ok": True,
            "status": "done",
            "indexed": int(counts.get("documents", 0)),
            "model": MODEL_NAME,
            "took_ms": took_ms,
            **({"counts": counts} if counts else {}),
        }

    # Fall back to our embed_all flow
    status = embed_all(verbose=verbose, tiers=tiers)
    took_ms = int((time.perf_counter() - t0) * 1000)
    ok = bool(status.get("ok"))
    indexed = int(status.get("indexed") or 0)
    error = status.get("error")

    response = {
        "ok": ok,
        "status": "done" if ok else "error",
        "indexed": indexed,
        "model": status.get("model"),
        "took_ms": took_ms,
    }
    if indexer_error:
        response["note"] = f"semantic_retriever reindex_all unavailable: {indexer_error}"
    if error:
        response["error"] = error

    logger.info("[KB] api_reindex → ok=%s indexed=%s model=%s took_ms=%s", ok, indexed, MODEL_NAME, took_ms)
    if not ok and error:
        logger.error("[KB] api_reindex error: %s", error)
    return response


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Health & Load                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def index_is_valid() -> bool:
    """
    Return True if an on-disk index exists and dimension matches expectation.
    """
    if not INDEX_DIR.exists() or not any(INDEX_DIR.glob("*")):
        logger.info("[KB] index_is_valid → missing storage")
        return False
    return _index_dim_matches_expected()

def get_index():
    """
    Load (or rebuild once) and return a VectorStoreIndex.
    Never leaves the index unusable; performs one rebuild attempt on errors.
    """
    from llama_index.core import StorageContext, load_index_from_storage  # lazy
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
            return None
        ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        return load_index_from_storage(ctx, embed_model=_resolve_embed_model())

def warmup() -> None:
    """Optional convenience for readiness probes."""
    try:
        _ = get_index()
    except Exception as e:
        log_event("kb_warmup_failed", {"error": str(e)})


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Search (public API)                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def simple_search(
    query: str,
    top_k: int = 5,
    *,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Quick similarity search with normalized rows:
      {title, path, tier, snippet, similarity, meta}
    """
    index = get_index()
    if index is None:
        return []
    try:
        engine = index.as_query_engine(similarity_top_k=top_k)
        res = engine.query(query)

        rows: List[Dict[str, Any]] = []
        for sn in getattr(res, "source_nodes", []) or []:
            try:
                score = getattr(sn, "score", None)
                node = getattr(sn, "node", sn)
                text = getattr(node, "text", "") or (getattr(node, "get_text", lambda: "")() or "")
                meta = getattr(node, "metadata", {}) or {}
                path = meta.get("file_path") or meta.get("path") or meta.get("source") or ""
                tier = meta.get("tier")
                title = meta.get("title") or (os.path.basename(str(path)) if path else "Untitled")

                thr_env = os.getenv("SEMANTIC_SCORE_THRESHOLD")
                thr = score_threshold if score_threshold is not None else (float(thr_env) if thr_env not in (None, "") else None)
                if thr is not None and (score is not None):
                    try:
                        if float(score) < float(thr):
                            continue
                    except Exception:
                        pass

                rows.append(
                    {
                        "title": str(title),
                        "path": str(path),
                        "tier": (str(tier).lower() if tier else None),
                        "snippet": str(text)[:1500],
                        "similarity": float(score) if score is not None else None,
                        "meta": meta,
                    }
                )
            except Exception:
                continue

        try:
            rows.sort(key=lambda r: float(r.get("similarity", 0.0) or 0.0), reverse=True)
        except Exception:
            pass
        return rows[: int(top_k or 5)]
    except Exception as e:
        logger.exception("[KB] simple_search failed: %s", e)
        return []

def search(
    *,
    query: str,
    k: Optional[int] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    Primary entrypoint compatible with services.semantic_retriever.search(...).
    Accepts both `k` and `top_k`. Returns normalized rows.
    """
    use_k = int((k if k not in (None, "") else (top_k if top_k not in (None, "") else 5)))
    return simple_search(query, top_k=use_k, score_threshold=score_threshold)

def api_search(query: str, k: int = 5, search_type: str | None = None):
    """Back-compat shim for routes/kb.search proxy. Ignores `search_type`."""
    return simple_search(query, top_k=k)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ CLI                                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

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
