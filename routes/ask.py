# File: routes/ask.py
# Directory: routes
# Purpose: FastAPI endpoints for /ask — validates input, runs MCP pipeline,
#          enforces Retrieval Gate (no-answer on insufficient grounding),
#          adds Anti-Parrot guard (no raw pastes), normalizes output,
#          provides GET compatibility and streaming shims, and guarantees
#          JSON-safe responses with correlation IDs and structured logs.

from __future__ import annotations

import os
import re
import traceback
from collections import Counter
from typing import Any, Dict, List, Optional, Annotated, AsyncGenerator, Union
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Router (no prefix; paths are /ask, /ask/stream, /ask/codex_stream)
router = APIRouter()

# Logging is safe to import at module load (does not import routes/agents)
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.ask")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

# ── Tunables (env-overridable) ───────────────────────────────────────────────

KB_SCORE_THRESHOLD: float = float(os.getenv("KB_SCORE_THRESHOLD", "0.35"))
KB_MIN_HITS: int = int(os.getenv("KB_MIN_HITS", "1"))
ANTI_PARROT_MAX_CONTIGUOUS_MATCH: int = int(os.getenv("ANTI_PARROT_MAX_CONTIGUOUS_MATCH", "180"))
ANTI_PARROT_JACCARD: float = float(os.getenv("ANTI_PARROT_JACCARD", "0.35"))
FINAL_TEXT_MAX_LEN: int = int(os.getenv("FINAL_TEXT_MAX_LEN", "20000"))

# ── Request / Response models (local, non-breaking) ─────────────────────────

class AskRequest(BaseModel):
    """Validated payload for /ask (POST). Supports legacy 'question' alias."""
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=3, description="User question/prompt.", alias="question")] = ...
    role: Optional[str] = Field("planner", description="Planner (default) or a specific route key.")
    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths to include.")
    topics: Optional[List[str]] = Field(default=None, description="Optional topical tags/labels.")
    user_id: str = Field("anonymous", description="Caller identity for logging/metrics.")
    debug: bool = Field(False, description="Enable extra debug output where supported.")


class AskResponse(BaseModel):
    """Normalized response from MCP pipeline (UI reads `final_text`)."""
    plan: Optional[Dict[str, Any]] = None
    routed_result: Union[Dict[str, Any], str, None] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    final_text: str = ""  # Canonical field for UI rendering


class StreamRequest(BaseModel):
    """Payload for streaming endpoints; mirrors AskRequest minimally."""
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=3, alias="question")] = ...
    context: Optional[str] = Field(default="", description="Optional prebuilt context")
    user_id: str = Field("anonymous")

# ── Helpers ─────────────────────────────────────────────────────────────────

def _json_safe(obj: Any) -> Any:
    """Best-effort coercion of arbitrary objects into JSON-serializable structures."""
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
    """
    Some callers may wrap results in {"result": {...}, "context": "...", "files_used": [...] }.
    Normalize into a single dict with the expected top-level keys.
    """
    if isinstance(result_or_wrapper, dict) and "result" in result_or_wrapper:
        inner = result_or_wrapper.get("result") or {}
        if isinstance(inner, dict):
            inner.setdefault("context", result_or_wrapper.get("context", ""))
            inner.setdefault("files_used", result_or_wrapper.get("files_used", []))
            inner.setdefault("meta", result_or_wrapper.get("meta", {}))
            return inner
    return result_or_wrapper


def _extract_final_text(plan: Any, routed_result: Any) -> str:
    """
    Canonical extraction of the user-facing text (synthesis only, no raw paste):
      1) routed_result.response
      2) routed_result.answer
      3) plan.final_answer
      4) "" (never None)
    """
    if isinstance(routed_result, dict):
        text = routed_result.get("response") or routed_result.get("answer") or ""
        if isinstance(text, str) and text.strip():
            return text
        resp = routed_result.get("response")
        if isinstance(resp, dict):
            t = resp.get("text") or ""
            if isinstance(t, str) and t.strip():
                return t
    elif isinstance(routed_result, str) and routed_result.strip():
        return routed_result

    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa

    return ""


def _truncate(s: str, max_len: int) -> str:
    if max_len and len(s) > max_len:
        return s[:max_len]
    return s


def _detect_grounding(meta: Dict[str, Any], routed_result: Any) -> Dict[str, Any]:
    """
    Returns:
      {
        "hits": int,
        "max_score": float|None,
        "has_attribution": bool
      }
    Heuristics:
      - Prefer meta.kb.{hits,max_score}
      - Fallback to routed_result.grounding/sources/citations lengths
    """
    kb = {}
    if isinstance(meta, dict):
        kb = meta.get("kb") or meta.get("retrieval") or {}

    hits = 0
    max_score = None
    if isinstance(kb, dict):
        hits = int(kb.get("hits") or 0)
        try:
            max_score = float(kb.get("max_score")) if kb.get("max_score") is not None else None
        except Exception:
            max_score = None

    has_attr = False
    if isinstance(routed_result, dict):
        for k in ("grounding", "sources", "citations", "attributions"):
            v = routed_result.get(k)
            if isinstance(v, list) and len(v) > 0:
                has_attr = True
                if hits == 0:
                    hits = len(v)

    return {"hits": hits, "max_score": max_score, "has_attribution": has_attr}


def _anti_parrot_triggered(final_text: str, context: str) -> bool:
    """Detect large verbatim copy by contiguous overlap ≥ threshold."""
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


def _make_no_answer_meta(reason: str, base_meta: Dict[str, Any], corr_id: str) -> Dict[str, Any]:
    meta = dict(base_meta or {})
    meta.update(
        {
            "no_answer": True,
            "reason": reason,
            "corr_id": corr_id,
            "kb_threshold": KB_SCORE_THRESHOLD,
            "kb_min_hits": KB_MIN_HITS,
            "anti_parrot_threshold": ANTI_PARROT_MAX_CONTIGUOUS_MATCH,
            "anti_parrot_jaccard": ANTI_PARROT_JACCARD,
        }
    )
    return meta


GROUNDING_LINE_RE = re.compile(
    r"[\u2022\-\*]\s+\*\*(?P<path>[^*]+)\*\*.*?\(score:\s*(?P<score>0\.\d+|1\.0+)\)",
    re.IGNORECASE,
)

def _extract_grounding_from_context(context: str):
    """Parse 'Top Matches' lines in the context block → (hits, max_score, sources[])."""
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


def _jaccard_ngrams(a: str, b: str, n: int = 5) -> float:
    """Simple n-gram Jaccard similarity to catch paraphrased pastes."""
    def ngrams(s: str):
        toks = [t for t in re.findall(r"\w+", s.lower()) if t]
        return Counter(tuple(toks[i:i+n]) for i in range(0, max(0, len(toks)-n+1)))
    sa, sb = ngrams(a), ngrams(b)
    if not sa or not sb:
        return 0.0
    inter = sum((sa & sb).values())
    union = sum((sa | sb).values())
    return inter / union if union else 0.0

# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, request: Request):
    """
    Run the MCP pipeline for a validated query and return a normalized response.
    Enforces:
      - Retrieval Gate (insufficient grounding => 'no answer')
      - Anti-Parrot (large verbatim or high Jaccard overlap => 'no answer')
    Keeps response shape stable for the frontend (final_text or "").
    Details surface via `meta`.
    """
    # 🔽 Lazy import here to avoid circular import at module load
    try:
        from agents.mcp_agent import run_mcp  # type: ignore
    except Exception as e:
        corr_id = request.headers.get("x-corr-id") or str(uuid4())
        log_event("ask_import_error", {"corr_id": corr_id, "error": str(e)})
        raise HTTPException(status_code=500, detail={"error": "mcp_import_failed", "corr_id": corr_id})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "hint": "query must be non-empty"},
        )

    corr_id = request.headers.get("x-corr-id") or str(uuid4())
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

    # Run MCP
    try:
        mcp_raw = await run_mcp(
            query=q,
            role=role,
            files=files,
            topics=topics,
            user_id=user_id,
            debug=debug,
            corr_id=corr_id,
        )
    except Exception as e:
        log_event(
            "ask_mcp_exception",
            {"corr_id": corr_id, "user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "mcp_failed", "message": "Failed to run MCP.", "corr_id": corr_id},
        )

    # Normalize & JSON-coerce all parts
    try:
        normalized = _normalize_result(mcp_raw if isinstance(mcp_raw, dict) else {})
        plan = _json_safe(normalized.get("plan"))
        routed_result = normalized.get("routed_result", {})
        critics = _json_safe(normalized.get("critics"))
        context = str(normalized.get("context") or "")
        files_used = _json_safe(normalized.get("files_used") or [])
        upstream_meta = normalized.get("meta") or {}
        final_text_raw = _extract_final_text(plan, routed_result)
    except Exception as e:
        log_event(
            "ask_normalize_exception",
            {"corr_id": corr_id, "user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "normalize_failed", "message": "Failed to normalize MCP result.", "corr_id": corr_id},
        )

    # Grounding detection (prefer structured; fallback to context parsing)
    grounding = _detect_grounding(upstream_meta if isinstance(upstream_meta, dict) else {}, routed_result)
    if grounding["hits"] == 0 and not grounding["has_attribution"]:
        hits, max_score_ctx, sources = _extract_grounding_from_context(context)
        if hits > 0:
            grounding["hits"] = hits
            grounding["max_score"] = max_score_ctx if max_score_ctx is not None else grounding["max_score"]
            grounding["has_attribution"] = True
            if isinstance(routed_result, dict) and not routed_result.get("grounding"):
                routed_result.setdefault("grounding", sources)

    # Tightened criteria: require non-None score meeting threshold AND attributions
    has_hits = grounding["hits"] >= KB_MIN_HITS
    score_ok = (grounding["max_score"] is not None) and (grounding["max_score"] >= KB_SCORE_THRESHOLD)
    has_attr = grounding["has_attribution"]

    gated_no_answer_reason = None
    if not (has_hits and score_ok and has_attr):
        gated_no_answer_reason = "Insufficient grounding"
        log_event(
            "ask_gate_blocked",
            {
                "corr_id": corr_id,
                "user": user_id,
                "hits": grounding["hits"],
                "max_score": grounding["max_score"],
                "has_attribution": has_attr,
                "threshold": KB_SCORE_THRESHOLD,
            },
        )

    # Anti-parrot (only if not already gated)
    if gated_no_answer_reason is None:
        final_text_candidate = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        contiguous_hit = _anti_parrot_triggered(final_text_candidate, context)
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

    # Shape meta + final_text
    meta: Dict[str, Any] = {"role": role, "debug": debug, "corr_id": corr_id}
    if isinstance(upstream_meta, dict):
        meta.update(_json_safe(upstream_meta))
    meta.update({"kb_hits": grounding["hits"], "kb_max_score": grounding["max_score"], "kb_has_attribution": has_attr})

    if gated_no_answer_reason:
        meta = _make_no_answer_meta(gated_no_answer_reason, meta, corr_id)
        final_text_out = ""
    else:
        final_text_out = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        meta.update({"no_answer": False, "anti_parrot_triggered": False})

    routed_result_safe = _json_safe(routed_result)

    log_event(
        "ask_response_summary",
        {
            "corr_id": corr_id,
            "user": user_id,
            "origin": meta.get("origin"),
            "final_text_head": (final_text_out or "")[:200],
            "no_answer": bool(gated_no_answer_reason),
            "kb_hits": grounding["hits"],
            "kb_max_score": grounding["max_score"],
            "kb_has_attr": has_attr,
        },
    )

    return AskResponse(
        plan=plan if isinstance(plan, dict) else None,
        routed_result=routed_result_safe if isinstance(routed_result_safe, (dict, str)) else {},
        critics=critics if critics is not None else None,
        context=context,
        files_used=files_used if isinstance(files_used, list) else [],
        meta=meta,
        final_text=final_text_out,
    )


@router.get("/ask")
async def ask_get(question: Annotated[str, Query(min_length=3)], request: Request):
    """Legacy GET shim: /ask?question=..."""
    payload = AskRequest.model_validate({"question": question})
    return await ask(payload, request)


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

    corr_id = request.headers.get("x-corr-id") or str(uuid4())

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in echo_stream(query=q, context=payload.context or "", user_id=payload.user_id, corr_id=corr_id):
                yield chunk.encode("utf-8")
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

    corr_id = request.headers.get("x-corr-id") or str(uuid4())

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in codex_stream(query=q, context=payload.context or "", user_id=payload.user_id, corr_id=corr_id):
                yield chunk.encode("utf-8")
        except Exception as e:
            log_event("ask_codex_stream_error", {"corr_id": corr_id, "error": str(e)})
            yield f"[stream error] {str(e)}".encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain")
