# routes/embeddings.py — modernized to use services.kb

from __future__ import annotations
import os, time
from typing import Any, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

import services.kb as kb  # ← real index + embed/search lifecycle

router = APIRouter()

def _corr_id(req: Optional[Request]) -> str:
    try:
        return getattr(getattr(req, "state", None), "corr_id", "") or ""
    except Exception:
        return ""

@router.get("/embeddings/ping")
def embeddings_ping() -> JSONResponse:
    return JSONResponse({"ok": True})

@router.get("/embeddings/status")
def embeddings_status(request: Request) -> JSONResponse:
    rid = _corr_id(request)
    exists = bool(kb.index_is_valid())  # fast check
    info: Dict[str, Any] = {
        "exists": exists,
        "last_modified": None,
        "num_files": None,
        "request_id": rid,
    }
    # Try to infer last_modified from the index dir if available
    try:
        from services.config import INDEX_DIR  # kb uses this
        if os.path.isdir(INDEX_DIR):
            mt = max((os.path.getmtime(os.path.join(INDEX_DIR, p)) for p in os.listdir(INDEX_DIR)), default=None)
            if mt:
                info["last_modified"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))
    except Exception:
        pass

    # Estimate num_files via kb.search() sampling or kb.get_index() if cheap
    try:
        # Prefer cheap index metadata if kb exposes it
        # (If not, we leave num_files=None)
        idx = kb.get_index()
        try:
            # LlamaIndex VectorStoreIndex: number of doc nodes in storage context (best-effort)
            storage = idx.storage_context  # type: ignore
            doc = getattr(storage, "docstore", None)
            if doc and hasattr(doc, "docs"):
                info["num_files"] = len(getattr(doc, "docs", {}))
        except Exception:
            pass
    except Exception:
        pass

    return JSONResponse(info)

@router.post("/embeddings/rebuild")
def embeddings_rebuild(request: Request, background: BackgroundTasks) -> JSONResponse:
    rid = _corr_id(request)

    def _do_rebuild():
        try:
            kb.embed_all(verbose=False)  # same behavior, calls into OpenAIEmbedding + LlamaIndex
        except Exception as e:
            try:
                from core.logging import log_event  # type: ignore
                log_event("embeddings_rebuild_error", {"request_id": rid, "error": str(e)})
            except Exception:
                pass

    background.add_task(_do_rebuild)
    return JSONResponse({"status": "queued", "request_id": rid, "message": "KB embedding rebuild started."})
