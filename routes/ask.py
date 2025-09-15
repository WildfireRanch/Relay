# ──────────────────────────────────────────────────────────────────────────────
# File: routes/ask.py
# Purpose: FastAPI endpoints for /ask — production-grade and CORS-tolerant
#          • Accepts q/query/prompt/question/text (coalesced → payload.query)
#          • Explicit OPTIONS /ask → 204 to guarantee clean preflight
#          • Pydantic v1/v2 compatible validators
#          • Retrieval Gate, Anti-Parrot, Context build, MCP call preserved
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import os
import re
import traceback
from collections import Counter
from inspect import iscoroutinefunction
from typing import Any, Dict, List, Optional, Annotated, AsyncGenerator, Union
from uuid import uuid4
import inspect

from fastapi import APIRouter, HTTPException, Query, Request, Header, Response, status
from fastapi.responses import StreamingResponse

# --- Pydantic v1/v2 compatibility ---------------------------------------------
try:
    from pydantic import BaseModel, Field  # type: ignore
    try:
        from pydantic import field_validator, model_validator  # v2
        _PD_V2 = True
    except Exception:  # pragma: no cover
        from pydantic import validator as field_validator  # v1
        from pydantic import root_validator as model_validator  # v1
        _PD_V2 = False
except Exception as _e:  # pragma: no cover
    raise RuntimeError("Pydantic is required") from _e

# Router (no prefix; paths are /ask, /ask/stream, /ask/codex_stream)
router = APIRouter()

# --- Logging shim (safe; no agent/route deps) ---------------------------------
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.ask")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

# ── Env helpers & tunables (support legacy + new names) -----------------------

def _env_float(*names: str, default: float) -> float:
    for n in names:
        v = os.getenv(n)
        if v is not None:
            try:
                return float(v)
            except Exception:
                continue
    return default

def _env_int(*names: str, default: int) -> int:
    for n in names:
        v = os.getenv(n)
        if v is not None:
            try:
                return int(v)
            except Exception:
                continue
    return default

# Retrieval gate thresholds
KB_SCORE_THRESHOLD: float = _env_float("ASK_MIN_MAX_SCORE", "KB_SCORE_THRESHOLD", default=0.35)
KB_MIN_HITS: int = _env_int("ASK_MIN_HITS", "KB_MIN_HITS", default=1)

# Anti-parrot thresholds
ANTI_PARROT_MAX_CONTIGUOUS_MATCH: int = _env_int("ANTI_PARROT_MAX_CONTIGUOUS_MATCH", default=180)
ANTI_PARROT_JACCARD: float = _env_float("ANTI_PARROT_JACCARD", default=0.35)

# Final text clamp
FINAL_TEXT_MAX_LEN: int = _env_int("FINAL_TEXT_MAX_LEN", default=20000)

# Agent timeout (router-enforced)
ASK_TIMEOUT_S: int = _env_int("ASK_TIMEOUT_S", default=60)

# ── Models --------------------------------------------------------------------

class AskRequest(BaseModel):
    """Validated payload for /ask (POST). Supports multiple aliases for the question."""
    if _PD_V2:
        model_config = {"populate_by_name": True}  # type: ignore[attr-defined]
    else:
        class Config:  # type: ignore[no-redef]
            allow_population_by_field_name = True

    # Accept several keys; we coalesce them → query via model validator
    q: Optional[str] = None
    query: Optional[str] = Field(default=None, description="User question/prompt.", alias="question")
    prompt: Optional[str] = None
    question: Optional[str] = None
    text: Optional[str] = None

    role: Optional[str] = Field("planner", description="Planner (default) or a specific route key.")
    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths to include.")
    topics: Optional[List[str]] = Field(default=None, description="Optional topical tags/labels.")
    user_id: str = Field("anonymous", description="Caller identity for logging/metrics.")
    debug: bool = Field(False, description="Enable extra debug output where supported.")

    # Coalesce aliases into .query (run BEFORE field validation)
    if _PD_V2:
        @model_validator(mode="before")
        def _coalesce_query(cls, values):
            if isinstance(values, dict):
                for key in ("q", "query", "prompt", "question", "text"):
                    v = values.get(key)
                    if isinstance(v, str) and v.strip():
                        values["query"] = v.strip()
                        break
            return values
    else:
        @model_validator(pre=True)  # type: ignore[no-redef]
        def _coalesce_query(cls, values):
            if isinstance(values, dict):
                for key in ("q", "query", "prompt", "question", "text"):
                    v = values.get(key)
                    if isinstance(v, str) and v.strip():
                        values["query"] = v.strip()
                        break
            return values

    if _PD_V2:
        @field_validator("query")
        @classmethod
        def _strip_query(cls, v: Optional[str]) -> str:
            v = (v or "").strip()
            if len(v) < 3:
                raise ValueError("query must be at least 3 chars")
            return v
    else:  # v1
        @field_validator("query")  # type: ignore[no-redef]
        def _strip_query(cls, v: Optional[str]) -> str:
            v = (v or "").strip()
            if len(v) < 3:
                raise ValueError("query must be at least 3 chars")
            return v

class ErrorEnvelope(BaseModel):
    error: str
    corr_id: str
    message: Optional[str] = None
    hint: Optional[str] = None

class AskResponse(BaseModel):
    """Normalized response from MCP pipeline (UI reads `final_text`)."""
    plan: Optional[Dict[str, Any]] = None
    routed_result: Union[Dict[str, Any], str, None] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str = ""
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    final_text: str = ""  # Canonical field for UI rendering

class StreamRequest(BaseModel):
    """Payload for streaming endpoints; mirrors AskRequest minimally."""
    if _PD_V2:
        model_config = {"populate_by_name": True}  # type: ignore[attr-defined]
    else:
        class Config:  # type: ignore[no-redef]
            allow_population_by_field_name = True

    query: Annotated[str, Field(min_length=3, alias="question")] = ...
    context: Optional[str] = Field(default="", description="Optional prebuilt context")
    user_id: str = Field("anonymous")

# ── Core helpers ---------------------------------------------------------------

def _filter_kwargs_for_callable(func, **kwargs):
    """Filter kwargs to only those accepted by `func`'s signature."""
    try:
        sig = inspect.signature(func)
        params = sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return kwargs
        return {k: v for k, v in kwargs.items() if k in params}
    except Exception:
        return {}

def _json_safe(obj: Any) -> Any:
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_safe(x) for x in obj]
        return str(obj)
    except Exception:
        return "[unserializable]"

def _normalize_result(result_or_wrapper: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(result_or_wrapper, dict) and "result" in result_or_wrapper:
        inner = result_or_wrapper.get("result") or {}
        if isinstance(inner, dict):
            inner.setdefault("context", result_or_wrapper.get("context", ""))
            inner.setdefault("files_used", result_or_wrapper.get("files_used", []))
            inner.setdefault("meta", result_or_wrapper.get("meta", {}))
            return inner
    return result_or_wrapper

def _final_text_from(plan: Any, rr: Any, root_final: Optional[str] = None) -> str:
    if isinstance(root_final, str) and root_final.strip():
        return root_final
    if isinstance(rr, dict):
        for key in ("final_text", "response", "answer"):
            val = rr.get(key)
            if isinstance(val, str) and val.strip():
                return val
        resp = rr.get("response")
        if isinstance(resp, dict):
            t = resp.get("text")
            if isinstance(t, str) and t.strip():
                return t
    elif isinstance(rr, str) and rr.strip():
        return rr
    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa
    return ""

def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] if (max_len and isinstance(s, str) and len(s) > max_len) else s

def _anti_parrot_contiguous(final_text: str, context: str) -> bool:
    if not final_text or not context:
        return False
    if len(final_text) < ANTI_PARROT_MAX_CONTIGUOUS_MATCH:
        return False
    step = max(ANTI_PARROT_MAX_CONTIGUOUS_MATCH // 2, 60)
    for i in range(0, len(final_text) - ANTI_PARROT_MAX_CONTIGUOUS_MATCH + 1, step):
        snippet = final_text[i : i + ANTI_PARROT_MAX_CONTIGUOUS_MATCH]
        pattern = re.escape(snippet)
        if re.search(pattern, context):
            return True
    return False

def _jaccard_ngrams(a: str, b: str, n: int = 5) -> float:
    def ngrams(s: str):
        toks = [t for t in re.findall(r"\w+", s.lower()) if t]
        return Counter(tuple(toks[i:i+n]) for i in range(0, max(0, len(toks)-n+1)))
    sa, sb = ngrams(a), ngrams(b)
    if not sa or not sb:
        return 0.0
    inter = sum((sa & sb).values())
    union = sum((sa | sb).values())
    return inter / union if union else 0.0

GROUNDING_LINE_RE = re.compile(
    r"[\u2022\-\*]\s+\*\*(?P<path>[^*]+)\*\*.*?\(score:\s*(?P<score>0\.\d+|1\.0+)\)",
    re.IGNORECASE,
)

def _extract_grounding_from_context(context: str):
    hits = 0
    max_score = None
    sources: List[Dict[str, Any]] = []
    if not context:
        return 0, None, []
    for m in GROUNDING_LINE_RE.finditer(context):
        path = (m.group("path") or "").strip()
        try:
            score = float(m.group("score"))
        except Exception:
            score = None
        sources.append({"path": path, "score": score})
        hits += 1
        if score is not None:
            max_score = score if max_score is None else max(max_score, score)
    return hits, max_score, sources

async def _maybe_await(func, *args, timeout_s: int, **kwargs):
    if iscoroutinefunction(func):
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(None, lambda: func(*args, **kwargs)), timeout=timeout_s)

# ── Context building (safe optional) ------------------------------------------

async def _build_context_safe(query: str, corr_id: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "context": "",
        "files_used": [],
        "kb": {"hits": 0, "max_score": 0.0, "sources": []},
        "grounding": [],
    }
    try:
        import importlib
        ctx_mod = importlib.import_module("core.context_engine")
        build_context = getattr(ctx_mod, "build_context", None)
        ContextRequest = getattr(ctx_mod, "ContextRequest", None)
        EngineConfig = getattr(ctx_mod, "EngineConfig", None)
        RetrievalTier = getattr(ctx_mod, "RetrievalTier", None)

        if not callable(build_context) or ContextRequest is None or EngineConfig is None or RetrievalTier is None:
            raise RuntimeError("context engine not available")

        from services.semantic_retriever import SemanticRetriever, TieredSemanticRetriever  # type: ignore

        score_thresh_env = os.getenv("RERANK_MIN_SCORE_GLOBAL") or os.getenv("SEMANTIC_SCORE_THRESHOLD")
        score_thresh = float(score_thresh_env) if score_thresh_env else None

        retrievers = {
            RetrievalTier.GLOBAL:       TieredSemanticRetriever("global",       score_threshold=score_thresh),
            RetrievalTier.PROJECT_DOCS: TieredSemanticRetriever("project_docs", score_threshold=score_thresh),
        }
        cfg = EngineConfig(retrievers=retrievers)  # type: ignore
        ctx = build_context(ContextRequest(query=query, corr_id=corr_id), cfg)  # type: ignore

        context_text = str((ctx or {}).get("context") or "")
        files_used = (ctx or {}).get("files_used") or []
        kb = ((ctx or {}).get("meta") or {}).get("kb") or {}
        matches = (ctx or {}).get("matches") or []

        result["context"] = context_text
        result["files_used"] = [{"path": p} for p in files_used if isinstance(p, str)]
        result["kb"] = {
            "hits": int(kb.get("hits") or 0),
            "max_score": float(kb.get("max_score") or 0.0),
            "sources": list(kb.get("sources") or []),
        }
        result["grounding"] = [
            {"path": m.get("path"), "score": float(m.get("score", 0.0)), "tier": m.get("tier")}
            for m in matches
            if isinstance(m, dict) and m.get("path")
        ]
    except Exception as e:
        log_event("ask_context_build_skipped", {"corr_id": corr_id, "error": str(e)})

    return result

# ── Routes --------------------------------------------------------------------

@router.options("/ask")
def ask_preflight() -> Response:
    """Guarantee a clean 204 for CORS preflight; Starlette CORS will attach headers."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/ask",
    response_model=AskResponse,
    response_model_exclude_none=True,
    responses={400: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}, 504: {"model": ErrorEnvelope}},
)
async def ask(
    payload: AskRequest,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id"),
):
    """
    Run the MCP pipeline for a validated query and return a normalized response.
    Enforces:
      - Retrieval Gate (insufficient grounding => 'no answer')
      - Anti-Parrot (contiguous copy + n-gram Jaccard)
    Keeps response shape stable for the frontend (final_text or "").
    """
    # Lazy agent import to avoid circular imports at module load
    try:
        from agents.mcp_agent import run_mcp  # type: ignore
    except Exception as e:
        corr_id = (x_corr_id or x_request_id or getattr(request.state, "corr_id", None) or uuid4().hex)
        log_event("ask_import_error", {"corr_id": corr_id, "error": str(e)})
        raise HTTPException(status_code=500, detail={"error": "mcp_import_failed", "corr_id": corr_id})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="Missing 'q' (or query/prompt/question/text)")

    corr_id = (x_corr_id or x_request_id or getattr(request.state, "corr_id", None) or uuid4().hex)
    try:
        request.state.corr_id = corr_id
    except Exception:
        pass

    role = (payload.role or "planner").strip() or "planner"
    files = payload.files or []
    topics = payload.topics or []
    user_id = payload.user_id
    debug = bool(payload.debug)

    log_event(
        "ask_received",
        {
            "corr_id": corr_id,
            "user": user_id,
            "role": role,
            "files_count": len(files),
            "topics_count": len(topics),
            "debug": debug,
        },
    )

    # 1) Build context (optional; never errors)
    ctx = await _build_context_safe(q, corr_id)
    context_text = ctx["context"]
    files_used = ctx["files_used"]
    kb_meta = ctx["kb"]
    grounding_from_ctx = ctx["grounding"]

    # 2) Retrieval Gate (require evidence before answering)
    has_hits = int(kb_meta["hits"]) >= KB_MIN_HITS
    score_ok = float(kb_meta["max_score"]) >= KB_SCORE_THRESHOLD
    has_attr = len(grounding_from_ctx) > 0
    gated_no_answer_reason = None
    if not (has_hits and score_ok and has_attr):
        gated_no_answer_reason = "Insufficient grounding"
        log_event(
            "ask_gate_blocked",
            {
                "corr_id": corr_id,
                "user": user_id,
                "hits": kb_meta["hits"],
                "max_score": kb_meta["max_score"],
                "has_attribution": has_attr,
                "threshold": KB_SCORE_THRESHOLD,
            },
        )

    # 3) If not gated yet, call MCP with timeout; pass context for reuse
    mcp_raw: Dict[str, Any] | Any = {}
    if gated_no_answer_reason is None:
        try:
            mcp_raw = await _maybe_await(
                run_mcp,
                query=q,
                role=role,
                files=files,
                topics=topics,
                user_id=user_id,
                debug=debug,
                corr_id=corr_id,
                context=context_text,
                timeout_s=ASK_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            log_event("ask_mcp_timeout", {"corr_id": corr_id, "timeout_s": ASK_TIMEOUT_S})
            raise HTTPException(status_code=504, detail={"error": "ask_timeout", "message": "Agent exceeded timeout", "corr_id": corr_id})
        except Exception as e:
            log_event(
                "ask_mcp_exception",
                {"corr_id": corr_id, "user": user_id, "error": str(e), "trace": traceback.format_exc()},
            )
            raise HTTPException(
                status_code=500,
                detail={"error": "mcp_failed", "message": "Failed to run MCP.", "corr_id": corr_id},
            )

    # 4) Normalize agent result (or empty if gated earlier)
    normalized = {}
    try:
        normalized = _normalize_result(mcp_raw if isinstance(mcp_raw, dict) else {})
        plan = _json_safe(normalized.get("plan"))
        routed_result = normalized.get("routed_result", {})
        critics = _json_safe(normalized.get("critics"))
        context_from_agent = str(normalized.get("context") or "")
        files_used_agent = _json_safe(normalized.get("files_used") or [])
        upstream_meta = normalized.get("meta") or {}
        final_text_raw = _final_text_from(plan, routed_result, root_final=normalized.get("final_text"))
    except Exception as e:
        log_event(
            "ask_normalize_exception",
            {"corr_id": corr_id, "user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "normalize_failed", "message": "Failed to normalize MCP result.", "corr_id": corr_id},
        )

    # Prefer agent context/files if provided, else our own
    context = context_from_agent or context_text
    files_used_out = files_used_agent or files_used
    if isinstance(files_used_out, list) and files_used_out and isinstance(files_used_out[0], str):
        files_used_out = [{"path": p} for p in files_used_out]  # type: ignore[assignment]

    # 5) Grounding: prefer engine matches; else agent; else parse context text
    grounding = grounding_from_ctx[:]
    if isinstance(routed_result, dict):
        grounding_agent = routed_result.get("grounding") or []
        if grounding_agent:
            grounding = grounding_agent
    if not grounding:
        hits_ctx, max_score_ctx, sources_ctx = _extract_grounding_from_context(context)
        if hits_ctx > 0:
            grounding = sources_ctx
            if kb_meta["hits"] == 0:
                kb_meta["hits"] = hits_ctx
            if (kb_meta["max_score"] or 0.0) == 0.0 and (max_score_ctx is not None):
                kb_meta["max_score"] = max_score_ctx

    # 6) Anti-parrot (only if not already gated)
    if gated_no_answer_reason is None:
        final_text_candidate = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        contiguous_hit = _anti_parrot_contiguous(final_text_candidate, context)
        jaccard = _jaccard_ngrams(final_text_candidate, context, n=5)
        if contiguous_hit or jaccard >= ANTI_PARROT_JACCARD:
            gated_no_answer_reason = "Anti-parrot guard: output mirrors source context"
            log_event(
                "ask_anti_parrot_blocked",
                {
                    "corr_id": corr_id,
                    "user": user_id,
                    "contiguous_hit": contiguous_hit,
                    "jaccard": jaccard,
                    "final_len": len(final_text_candidate),
                    "context_len": len(context),
                },
            )

    # 7) Shape meta + final_text
    meta: Dict[str, Any] = {"role": role, "debug": debug, "corr_id": corr_id}
    if isinstance(upstream_meta, dict):
        meta.update(_json_safe(upstream_meta))
    meta["kb"] = {
        "hits": int(kb_meta.get("hits") or 0),
        "max_score": float(kb_meta.get("max_score") or 0.0),
        "sources": kb_meta.get("sources") or [s.get("path") for s in grounding if isinstance(s, dict) and s.get("path")],
    }

    if gated_no_answer_reason:
        meta.update(
            {
                "no_answer": True,
                "reason": gated_no_answer_reason,
                "kb_threshold": KB_SCORE_THRESHOLD,
                "kb_min_hits": KB_MIN_HITS,
                "anti_parrot_threshold": ANTI_PARROT_MAX_CONTIGUOUS_MATCH,
                "anti_parrot_jaccard": ANTI_PARROT_JACCARD,
            }
        )
        final_text_out = ""
        routed_result_out = {"grounding": grounding}
    else:
        final_text_out = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        meta.update({"no_answer": False, "anti_parrot_triggered": False})
        routed_result_out = normalized.get("routed_result") or {}
        if isinstance(routed_result_out, dict) and not routed_result_out.get("grounding"):
            routed_result_out["grounding"] = grounding

    log_event(
        "ask_response_summary",
        {
            "corr_id": corr_id,
            "user": user_id,
            "final_text_head": (final_text_out or "")[:200],
            "no_answer": meta.get("no_answer"),
            "kb_hits": meta["kb"]["hits"],
            "kb_max_score": meta["kb"]["max_score"],
            "has_grounding": bool(grounding),
        },
    )

    return AskResponse(
        plan=plan if isinstance(plan, dict) else None,
        routed_result=_json_safe(routed_result_out) if isinstance(routed_result_out, (dict, str)) else {},
        critics=critics if critics is not None else None,
        context=context,
        files_used=files_used_out if isinstance(files_used_out, list) else [],
        meta=_json_safe(meta),
        final_text=final_text_out,
    )

@router.get("/ask")
async def ask_get(
    question: Annotated[str, Query(min_length=3)],
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id"),
):
    """Legacy GET shim: /ask?question=..."""
    payload = AskRequest.model_validate({"question": question})
    return await ask(payload, request, x_request_id=x_request_id, x_corr_id=x_corr_id)

@router.post("/ask/stream")
async def ask_stream(payload: StreamRequest, request: Request):
    """Streamed answer via Echo (lazy-imported)."""
    try:
        from agents.echo_agent import stream as echo_stream  # type: ignore
    except Exception:
        echo_stream = None  # type: ignore

    if echo_stream is None:
        raise HTTPException(status_code=501, detail={"error": "not_implemented", "message": "Echo streaming not available."})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "hint": "query must be non-empty"})

    corr_id = request.headers.get("X-Corr-Id") or uuid4().hex

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in echo_stream(query=q, context=payload.context or "", user_id=payload.user_id, corr_id=corr_id):
                yield (chunk if isinstance(chunk, str) else str(chunk)).encode("utf-8")
        except Exception as e:
            log_event("ask_stream_error", {"corr_id": corr_id, "error": str(e)})
            yield f"[stream error] {str(e)}".encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain")

@router.post("/ask/codex_stream")
async def ask_codex_stream(payload: StreamRequest, request: Request):
    """Streamed code/patch output via Codex (lazy-imported)."""
    try:
        from agents.codex_agent import stream as codex_stream  # type: ignore
    except Exception:
        codex_stream = None  # type: ignore

    if codex_stream is None:
        raise HTTPException(status_code=501, detail={"error": "not_implemented", "message": "Codex streaming not available."})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "hint": "query must be non-empty"})

    corr_id = request.headers.get("X-Corr-Id") or uuid4().hex

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in codex_stream(query=q, context=payload.context or "", user_id=payload.user_id, corr_id=corr_id):
                yield (chunk if isinstance(chunk, str) else str(chunk)).encode("utf-8")
        except Exception as e:
            log_event("ask_codex_stream_error", {"corr_id": corr_id, "error": str(e)})
            yield f"[stream error] {str(e)}".encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain")

# ──────────────────────────────────────────────────────────────────────────────
