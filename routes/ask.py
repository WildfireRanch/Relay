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

from core.logging import log_event
from agents.mcp_agent import run_mcp

# Optional streaming agents (best-effort imports)
try:
    from agents.echo_agent import stream as echo_stream
except Exception:  # pragma: no cover
    echo_stream = None  # type: ignore

try:
    from agents.codex_agent import stream as codex_stream
except Exception:  # pragma: no cover
    codex_stream = None  # type: ignore


router = APIRouter()

# ── Tunables (env-overridable) ───────────────────────────────────────────────

# Minimum relevance score (0..1) to accept grounding as sufficient.
KB_SCORE_THRESHOLD: float = float(os.getenv("KB_SCORE_THRESHOLD", "0.35"))

# Minimum number of grounded hits (documents/sections) to consider.
KB_MIN_HITS: int = int(os.getenv("KB_MIN_HITS", "1"))

# Anti-parrot: if we detect any contiguous overlap >= this many characters
# between final_text and provided context, we treat it as a paste.
ANTI_PARROT_MAX_CONTIGUOUS_MATCH: int = int(os.getenv("ANTI_PARROT_MAX_CONTIGUOUS_MATCH", "180"))

# Anti-parrot: n-gram Jaccard similarity threshold (0..1) across 5-grams.
ANTI_PARROT_JACCARD: float = float(os.getenv("ANTI_PARROT_JACCARD", "0.35"))

# Optional hard maximum final_text length to avoid pathological outputs
FINAL_TEXT_MAX_LEN: int = int(os.getenv("FINAL_TEXT_MAX_LEN", "20000"))


# ── Request / Response models (local, non-breaking) ─────────────────────────

class AskRequest(BaseModel):
    """
    Validated payload for /ask (POST).
    Supports legacy 'question' alias; we store into canonical 'query'.
    """
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=3, description="User question/prompt.", alias="question")] = ...
    role: Optional[str] = Field("planner", description="Planner (default) or a specific route key.")
    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths to include.")
    topics: Optional[List[str]] = Field(default=None, description="Optional topical tags/labels.")
    user_id: str = Field("anonymous", description="Caller identity for logging/metrics.")
    debug: bool = Field(False, description="Enable extra debug output where supported.")


class AskResponse(BaseModel):
    """
    Normalized response from MCP pipeline (UI reads `final_text`).
    We keep your existing shape to avoid breaking the frontend.
    """
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
        # Fallback to string for exotic objects
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
    # routed_result may be dict/str/None
    if isinstance(routed_result, dict):
        text = routed_result.get("response") or routed_result.get("answer") or ""
        if isinstance(text, str) and text.strip():
            return text
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
    Returns a dict with:
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

    # Fallbacks based on routed_result shape
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
    """
    Detects large verbatim copy by searching for a contiguous overlap >= ANTI_PARROT_MAX_CONTIGUOUS_MATCH.
    Uses a simple sliding window regex approach for robustness and speed.
    """
    if not final_text or not context:
        return False
    # Only bother if the candidate output is longer than the threshold
    if len(final_text) < ANTI_PARROT_MAX_CONTIGUOUS_MATCH:
        return False

    # Check overlapping chunks from final_text against context
    step = max(ANTI_PARROT_MAX_CONTIGUOUS_MATCH // 2, 60)
    for i in range(0, len(final_text) - ANTI_PARROT_MAX_CONTIGUOUS_MATCH + 1, step):
        snippet = final_text[i : i + ANTI_PARROT_MAX_CONTIGUOUS_MATCH]
        # Make a moderately permissive pattern (escape most special chars)
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


# Parse sources out of the pretty "Top Matches" block in context, e.g.:
# • **/path/to/file.md** — _(tier: ..., score: 0.552)
GROUNDING_LINE_RE = re.compile(
    r"[\u2022\-\*]\s+\*\*(?P<path>[^*]+)\*\*.*?\(score:\s*(?P<score>0\.\d+|1\.0+)\)",
    re.IGNORECASE,
)


def _extract_grounding_from_context(context: str):
    """
    Parse 'Semantic Retrieval (Top Matches)' lines in the context block.
    Returns (hits, max_score, sources[]) where sources = [{path, score}]
    """
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
    """
    Simple n-gram Jaccard similarity to catch paraphrased pastes.
    """
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
    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "hint": "query must be non-empty"},
        )

    corr_id = request.headers.get("x-corr-id") or str(uuid4())
    try:
        request.state.corr_id = corr_id  # for downstream logging
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

    # Run MCP (planner/docs/codex orchestration)
    try:
        mcp_raw = await run_mcp(
            query=q,
            role=role,
            files=files,
            topics=topics,
            user_id=user_id,
            debug=debug,
            corr_id=corr_id,  # if your agent supports it, great; otherwise ignored
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

    # ---- Grounding detection (prefer structured; fallback to context parsing) ----
    grounding = _detect_grounding(upstream_meta if isinstance(upstream_meta, dict) else {}, routed_result)

    if grounding["hits"] == 0 and not grounding["has_attribution"]:
        hits, max_score_ctx, sources = _extract_grounding_from_context(context)
        if hits > 0:
            grounding["hits"] = hits
            grounding["max_score"] = max_score_ctx if max_score_ctx is not None else grounding["max_score"]
            grounding["has_attribution"] = True
            # Surface parsed sources back to client for transparency
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

    # ---- Anti-parrot guard (only if not already gated) ----
    anti_parrot = False
    if gated_no_answer_reason is None:
        final_text_candidate = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        contiguous_hit = _anti_parrot_triggered(final_text_candidate, context)
        jaccard = _jaccard_ngrams(final_text_candidate, context, n=5)
        if contiguous_hit or jaccard >= ANTI_PARROT_JACCARD:
            anti_parrot = True
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

    # ---- Shape meta and final_text according to gate results ----
    meta: Dict[str, Any] = {"role": role, "debug": debug, "corr_id": corr_id}
    if isinstance(upstream_meta, dict):
        # upstream meta may include origin, timings_ms, kb.*, request_id, etc.
        meta.update(_json_safe(upstream_meta))

    # Always reflect grounding stats in meta for observability
    meta.update({
        "kb_hits": grounding["hits"],
        "kb_max_score": grounding["max_score"],
        "kb_has_attribution": has_attr,
    })

    if gated_no_answer_reason:
        # No-answer outcome: clear final_text, record reason & flags
        meta = _make_no_answer_meta(gated_no_answer_reason, meta, corr_id)
        final_text_out = ""
    else:
        final_text_out = _truncate(final_text_raw or "", FINAL_TEXT_MAX_LEN)
        meta.update(
            {
                "no_answer": False,
                "anti_parrot_triggered": False,
            }
        )

    # Ensure routed_result is JSON-safe (only after we've extracted text)
    routed_result_safe = _json_safe(routed_result)

    # Quick ops summary
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
    """
    Legacy GET shim: /ask?question=...
    Reuses POST logic by constructing an AskRequest, so behavior stays identical.
    """
    payload = AskRequest.model_validate({"question": question})
    return await ask(payload, request)


@router.post("/ask/stream")
async def ask_stream(payload: StreamRequest, request: Request):
    """
    Streamed answer via Echo. Returns 501 if echo streaming is unavailable.
    Returns plain text chunks (compatible with your frontend's current reader).
    """
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
    """
    Streamed code/patch output via Codex agent. Returns 501 if codex streaming is unavailable.
    """
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
