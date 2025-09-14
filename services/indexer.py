# ──────────────────────────────────────────────────────────────────────────────
# File: services/indexer.py
# Purpose: Priority-tier indexing for code + docs with code-aware chunking,
#          reusing canonical KB filter/model/dimension logic from services.kb.
#
# Why this version:
#   • De-duplicates filters: imports should_index_file from services.kb
#   • Uses kb’s model/dimension resolution (one source of truth)
#   • Structured warnings for unreadable/filtered files (no silent drops)
#   • Returns status dict; no sys.exit() or unhandled exceptions
#   • Persists to INDEX_DIR (authoritative) + ./data/index (back-compat)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import glob
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

# Canonical KB plumbing (filters, model/dimensions, index path, logging helper)
from services import kb as kb  # keep as module alias for internals
from services.kb import (
    should_index_file,  # single source of truth for filters
    INDEX_DIR,
    INDEX_ROOT,
    MODEL_NAME,
    EXPECTED_DIM,
)

# LlamaIndex bits (import here so env overrides in kb are already applied)
from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter

# ── Logging (align with kb) ───────────────────────────────────────────────────
logger = logging.getLogger("services.indexer")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, payload: Optional[Dict] = None) -> None:
        return

logger.info("📦 indexer loaded | INDEX_DIR=%s | MODEL=%s dim=%s", INDEX_DIR, MODEL_NAME, EXPECTED_DIM)

# ── Priority tiers (kept from your version; adjust as your repo evolves) ─────
PRIORITY_INDEX_PATHS: List[tuple[str, List[str]]] = [
    ("global", ["./docs/generated/global_context.md", "./docs/generated/global_context.auto.md"]),
    ("context", ["./context/"]),  # Cross-project overlays
    ("project_summary", ["./docs/PROJECT_SUMMARY.md", "./docs/RELAY_CODE_UPDATE.md", "./docs/context-commandcenter.md"]),
    ("project_docs", ["./docs/imported/", "./docs/kb/", "./docs/*.md"]),
    ("code", ["./services/", "./routes/", "./frontend/", "./src/", "./backend/"]),
]

# ── Helpers you already had (kept and slightly tidied) ───────────────────────
def get_language_from_path(file_path: str) -> str:
    """Map file extension → CodeSplitter language label."""
    f = file_path.lower()
    if f.endswith(".py"):
        return "python"
    if f.endswith((".js", ".jsx")):
        return "javascript"
    if f.endswith((".ts", ".tsx")):
        return "typescript"
    if f.endswith(".java"):
        return "java"
    if f.endswith(".go"):
        return "go"
    if f.endswith(".cpp"):
        return "cpp"
    return "python"  # safe fallback

def collect_code_context(files: List[str], base_dir: str = "./") -> str:
    """Read & join contents (used for prompt context elsewhere)."""
    parts: List[str] = []
    base = Path(base_dir)
    for rel in files:
        path = base / rel
        if path.exists() and path.is_file():
            try:
                parts.append(f"### {rel}\n{path.read_text(encoding='utf-8')}")
            except Exception as e:
                logger.warning("[indexer] skip context %s: %s", rel, e.__class__.__name__)
                log_event("indexer_context_skip", {"file": str(path), "reason": e.__class__.__name__})
                continue
    return "\n\n".join(parts)

# ── WIPE_INDEX handling (supports true/1/True) ────────────────────────────────
def _maybe_wipe() -> None:
    wipe = os.getenv("WIPE_INDEX", "false").strip().lower() in {"1", "true", "yes"}
    if wipe:
        logger.warning("[indexer] WIPE_INDEX → removing %s", INDEX_DIR)
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        log_event("indexer_wipe_index", {"index_dir": str(INDEX_DIR)})
    else:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("[indexer] WIPE_INDEX not set — existing index will be updated/extended if run.")

# ── Core: gather documents according to PRIORITY_INDEX_PATHS ─────────────────
def _gather_documents() -> List[Document]:
    docs: List[Document] = []
    text_splitter = SentenceSplitter(chunk_size=1024)

    for tier, paths in PRIORITY_INDEX_PATHS:
        for p in paths:
            # 1) Directory walk
            if p.endswith("/"):
                dpath = Path(p)
                if not dpath.exists():
                    kb._log_skip(str(dpath), tier, "directory not found")
                    continue
                for f in dpath.rglob("*"):
                    if not f.is_file():
                        continue
                    fpath = str(f)
                    if should_index_file(fpath, tier):
                        try:
                            text = f.read_text(encoding="utf-8")
                        except Exception as e:
                            kb._log_skip(fpath, tier, f"unreadable: {e.__class__.__name__}")
                            continue
                        docs.append(Document(text=text, metadata={"tier": tier, "file_path": fpath}))
                    else:
                        kb._log_skip(fpath, tier, "filtered by rules")

            # 2) Glob patterns (incl. *.md lists)
            elif "*" in p or p.endswith(".md"):
                for f in glob.glob(p):
                    if not Path(f).is_file():
                        continue
                    if should_index_file(f, tier):
                        try:
                            text = Path(f).read_text(encoding="utf-8")
                        except Exception as e:
                            kb._log_skip(f, tier, f"unreadable: {e.__class__.__name__}")
                            continue
                        docs.append(Document(text=text, metadata={"tier": tier, "file_path": f}))
                    else:
                        kb._log_skip(f, tier, "filtered by rules")

            # 3) Single file path given
            else:
                f = Path(p)
                if f.exists() and f.is_file():
                    if should_index_file(str(f), tier):
                        try:
                            text = f.read_text(encoding="utf-8")
                        except Exception as e:
                            kb._log_skip(str(f), tier, f"unreadable: {e.__class__.__name__}")
                            continue
                        docs.append(Document(text=text, metadata={"tier": tier, "file_path": str(f)}))
                    else:
                        kb._log_skip(str(f), tier, "filtered by rules")
                else:
                    kb._log_skip(str(f), tier, "file not found")
    logger.info("[indexer] gathered %d base documents", len(docs))
    return docs

# ── Chunking into nodes (code-aware) ─────────────────────────────────────────
def _chunk_documents(docs: List[Document]) -> List:
    nodes = []
    text_splitter = SentenceSplitter(chunk_size=1024)
    for doc in docs:
        file_path = (doc.metadata or {}).get("file_path", "")
        if file_path.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".cpp")):
            language = get_language_from_path(file_path)
            code_splitter = CodeSplitter(language=language, max_chars=1024, chunk_lines=30)
            try:
                nodes.extend(code_splitter.get_nodes_from_documents([doc]))
            except Exception as e:
                kb._log_skip(file_path, (doc.metadata or {}).get("tier", "code"), f"code_split_fail: {e.__class__.__name__}")
        else:
            try:
                nodes.extend(text_splitter.get_nodes_from_documents([doc]))
            except Exception as e:
                kb._log_skip(file_path, (doc.metadata or {}).get("tier", "project_docs"), f"text_split_fail: {e.__class__.__name__}")
    logger.info("[indexer] total nodes prepared: %d", len(nodes))
    return nodes

# ── Public entry: build index with this indexer strategy ─────────────────────
def index_directories() -> Dict[str, object]:
    """
    Scans PRIORITY_INDEX_PATHS, filters, chunks (code-aware), embeds & persists.
    Returns a status dict; never raises to callers.
    """
    try:
        _maybe_wipe()

        # Keep model/dimension logic aligned with kb
        EMBED_MODEL = kb._resolve_embed_model()
        logger.info("[indexer] using model=%s dim=%s", MODEL_NAME, EXPECTED_DIM)
        log_event("indexer_model_selected", {"model": MODEL_NAME, "dim": EXPECTED_DIM})

        base_docs = _gather_documents()
        if not base_docs:
            msg = "No documents matched filters; nothing to index."
            logger.error("[indexer] %s", msg)
            log_event("indexer_empty", {})
            return {"ok": False, "error": msg, "indexed_docs": 0, "nodes": 0, "model": MODEL_NAME}

        nodes = _chunk_documents(base_docs)
        if not nodes:
            msg = "No nodes produced after chunking; check filters/splitters."
            logger.error("[indexer] %s", msg)
            log_event("indexer_no_nodes", {})
            return {"ok": False, "error": msg, "indexed_docs": len(base_docs), "nodes": 0, "model": MODEL_NAME}

        # Build & persist (authoritative location)
        index = VectorStoreIndex(nodes=nodes, embed_model=EMBED_MODEL, show_progress=True)
        sc: StorageContext = index.storage_context
        sc.persist(persist_dir=str(INDEX_DIR))
        # Sidecar for dimension guardrails (so kb can sanity-check on load)
        kb._write_dim_meta(int(EXPECTED_DIM or 0))

        # Back-compat: also persist to ./data/index if different
        legacy_dir = Path("./data/index").resolve()
        try:
            if legacy_dir != INDEX_DIR:
                legacy_dir.mkdir(parents=True, exist_ok=True)
                sc.persist(persist_dir=str(legacy_dir))
        except Exception as e:
            logger.warning("[indexer] legacy persist skipped: %s", e.__class__.__name__)

        logger.info("✅ indexer complete | docs=%d nodes=%d → %s", len(base_docs), len(nodes), INDEX_DIR)
        log_event("indexer_complete", {"docs": len(base_docs), "nodes": len(nodes), "index_dir": str(INDEX_DIR)})
        return {"ok": True, "error": None, "indexed_docs": len(base_docs), "nodes": len(nodes), "model": MODEL_NAME, "index_dir": str(INDEX_DIR)}

    except Exception as e:
        logger.exception("[indexer] fatal error")
        log_event("indexer_fail", {"error": str(e)})
        return {"ok": False, "error": str(e), "indexed_docs": 0, "nodes": 0, "model": MODEL_NAME}

# ── CLI passthrough (optional) ───────────────────────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    status = index_directories()
    print(status if status.get("ok") else f"[indexer] ERROR — {status.get('error')}")
