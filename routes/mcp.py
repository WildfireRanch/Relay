# File: routes/mcp.py
# Purpose: Robust MCP entrypoint with strict I/O models, timeout budget, targeted retries,
#          optional circuit breaker, correlation ID propagation, OpenTelemetry spans,
#          stable error envelopes, and guaranteed final_text via finalize_envelope().
#
# Notes:
# - Keeps external behavior stable while adding resilience & observability.
# - Uses asyncio.timeout for a hard deadline (Python 3.11+).
# - Retries are limited and jittered; only for transient classes (e.g., 429/5xx).
# - Circuit breaker is optional (pybreaker). If not installed, route still functions.
# - Correlation ID is read from X-Request-ID or asgi-correlation-id middleware state.
# - finalize_envelope() ensures final_text on success; errors return a stable shape.
#
# See “References & rationale” (below the code) for design sources.

from __future__ import annotations

import asyncio
import random
import time
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field, conlist

from core.logging import log_event
from services.answer_finalizer import finalize_envelope
from agents.mcp_agent import run_mcp  # should be async

# ----------------------------- Optional dependencies -----------------------------

# Circuit breaker (optional). If not available, we fall back to a no-op wrapper.
try:
    from pybreaker import CircuitBreaker, CircuitBreakerError  # type: ignore
except Exception:  # pragma: no cover
    class CircuitBreakerError(Exception):
        pass

    class CircuitBreaker:  # minimal "pass-through" fallback
        def __init__(self, *_, **__):
            pass

        async def call(self, func, *args, **kwargs):
            # Call the async function directly; no circuit-breaking if library missing.
            return await func(*args, **kwargs)

# OpenTelemetry (optional). If not configured, we no-op safely.
try:
    from opentelemetry import trace  # type: ignore
    from opentelemetry.trace.status import Status, StatusCode  # type: ignore

    tracer = trace.get_tracer(__name__)
except Exception:  # pragma: no cover
    tracer = None

    class StatusCode:  # type: ignore
        OK = "OK"
        ERROR = "ERROR"

    class Status:  # type: ignore
        def __init__(self, *_args, **_kwargs):
            pass


router = APIRouter()

# --------------------------------- Models ---------------------------------------

AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]


class McpRunBody(BaseModel):
    """
    Request schema for /mcp/run.
    - query: main user question or instruction (guarded length)
    - role: agent role hint; defaults to planner
    - files/topics: optional inputs; capped for safety
    - debug: diagnostics flag (logs/echoing may be increased server-side)
    - timeout_s: hard deadline for the entire request
    - max_context_tokens: soft hint for downstream packing (if supported)
    """
    query: str = Field(..., min_length=1, max_length=8000)
    role: Optional[AllowedRole] = Field(default="planner")
    files: Optional[conlist(str, max_items=16)] = None
    topics: Optional[conlist(str, max_items=16)] = None
    debug: bool = Field(default=False)
    timeout_s: int = Field(default=45, ge=1, le=120)
    max_context_tokens: Optional[int] = Field(default=120_000, ge=1024, le=300_000)


# --------------------------------- Utilities ------------------------------------

def _compute_jitter_backoff(attempt: int, base: float = 0.25, cap: float = 2.5) -> float:
    """
    Exponential backoff with full jitter.
    attempt: 1-based attempt counter.
    returns: randomized delay seconds, capped.
    """
    # min(cap, base * 2^attempt) * random[0,1)
    return min(cap, base * (2 ** attempt)) * random.random()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_error_envelope(message: str, code: str, request_id: str, extra_meta: dict | None = None) -> dict:
    """
    Stable error JSON shape that the frontend can always parse.
    We intentionally leave final_text empty for hard errors.
    """
    return {
        "final_text": "",
        "error": {"code": code, "message": message},
        "meta": {"request_id": request_id, **(extra_meta or {})},
    }


def _sanitize_str_list(values: Optional[list[str]]) -> list[str]:
    """
    Deduplicate and trim items; reject dangerous path traversal in file lists.
    """
    out: list[str] = []
    if not values:
        return out
    seen = set()
    for v in values:
        s = (v or "").strip()
        if not s or s in seen:
            continue
        # very basic path safety check; downstream should still validate
        if ".." in s or "\x00" in s:
            continue
        seen.add(s)
        out.append(s)
    return out


# A tuned circuit breaker: trip after several consecutive failures; auto-reset.
# If pybreaker isn't available, this remains a no-op pass-through.
mcp_cb = CircuitBreaker(fail_max=5, reset_timeout=30)


# ------------------------------- Route handler ----------------------------------

@router.post("/mcp/run")
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    """
    Robust MCP endpoint:
    - Enforces a route-level deadline via asyncio.timeout().
    - Applies targeted retries with jitter for transient classes.
    - Optionally guards dependencies via circuit breaker.
    - Propagates a correlation ID and records OpenTelemetry spans.
    - Finalizes success responses to guarantee final_text.
    - Returns a stable error envelope on failure.
    """
    # ------------------- Correlation / request identity -------------------
    req_id = x_request_id or getattr(request.state, "correlation_id", None) or f"req-{_now_ms()}"
    start = time.time()

    # Inputs (sanitized)
    role = body.role or "planner"
    files = _sanitize_str_list(body.files)
    topics = _sanitize_str_list(body.topics)
    timeout_s = int(body.timeout_s)
    debug = bool(body.debug)

    # ------------------- OpenTelemetry span (optional) --------------------
    span_cm = tracer.start_as_current_span("mcp.run") if tracer else None
    if span_cm:
        span = span_cm.__enter__()  # type: ignore
        try:
            span.set_attribute("request.id", req_id)
            span.set_attribute("mcp.role", role)
            span.set_attribute("mcp.files_count", len(files))
            span.set_attribute("mcp.topics_count", len(topics))
            span.set_attribute("mcp.timeout_s", timeout_s)
        except Exception:
            pass

    # ------------------- Core call with deadline & retries ----------------
    async def _invoke_once():
        """
        Call agents.mcp_agent.run_mcp with best-effort extended hints.
        Falls back to a minimal signature if the implementation doesn't support hints.
        """
        try:
            # Preferred call shape (if run_mcp supports these kwargs)
            return await run_mcp(
                query=body.query,
                files=files,
                topics=topics,
                role=role,
                user_id=None,             # inject from auth/session if you have it
                debug=debug,
                timeout_s=timeout_s,      # budget hint for downstream
                max_context_tokens=body.max_context_tokens,
                request_id=req_id,
            )
        except TypeError:
            # Back-compat path for older signatures
            return await run_mcp(
                query=body.query,
                files=files,
                topics=topics,
                role=role,
                user_id=None,
                debug=debug,
            )

    attempts = 0
    last_exc: Exception | None = None

    try:
        async with asyncio.timeout(timeout_s):
            while True:
                try:
                    attempts += 1
                    result = await mcp_cb.call(_invoke_once)
                    break
                except CircuitBreakerError as cbe:
                    # Dependency is open-circuited: fast fail with stable envelope
                    if span_cm:
                        try:
                            span.record_exception(cbe)  # type: ignore
                            span.set_status(Status(StatusCode.ERROR))  # type: ignore
                        except Exception:
                            pass
                    return _stable_error_envelope(
                        "Dependency unavailable (circuit open)",
                        "CIRCUIT_OPEN",
                        req_id,
                    )
                except Exception as e:
                    last_exc = e
                    # Retry only on classes that are likely transient
                    status = getattr(e, "status_code", None)
                    transient = status in (408, 423, 425, 429, 500, 502, 503, 504)
                    if not transient or attempts >= 3:
                        raise
                    await asyncio.sleep(_compute_jitter_backoff(attempts))
    except asyncio.TimeoutError:
        # Hard route deadline hit
        if span_cm:
            try:
                span.set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception:
                pass
        return _stable_error_envelope("Operation timed out", "TIMEOUT", req_id)
    except Exception as e:
        # Unhandled error path
        if span_cm:
            try:
                span.record_exception(e)  # type: ignore
                span.set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception:
                pass
        # Keep message terse; detailed traces should be in logs/APM
        return _stable_error_envelope("Unhandled server error", "UNHANDLED", req_id)

    # ------------------- Finalization & observability ---------------------
    envelope = finalize_envelope(result or {})

    # Stamp request ID for cross-service debugging
    envelope.setdefault("meta", {}).update({"request_id": req_id})

    # Log structured summaries for quick triage
    meta = envelope.get("meta") or {}
    rr = envelope.get("routed_result") or {}
    latency_ms = int((time.time() - start) * 1000)

    log_event("mcp_run_completed", {
        "request_id": req_id,
        "role": role,
        "latency_ms": latency_ms,
        "attempts": attempts,
    })
    log_event("reply_summary", {
        "request_id": req_id,
        "route": meta.get("route"),
        "origin": meta.get("origin"),
        "plan_id": meta.get("plan_id"),
        "final_len": len(envelope.get("final_text") or ""),
        "rr_has_answer": bool((rr or {}).get("answer")),
    })

    if span_cm:
        try:
            span.set_status(Status(StatusCode.OK))  # type: ignore
        except Exception:
            pass
        finally:
            span_cm.__exit__(None, None, None)  # type: ignore

    return envelope
