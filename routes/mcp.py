# File: routes/mcp.py
# Purpose: Stable MCP entrypoint with strict I/O models, deadline, targeted retries,
#          optional circuit breaker, correlation ID propagation, OTel spans,
#          stable error envelopes, and guaranteed final_text finalization.

from __future__ import annotations

import asyncio
import random
import time
from typing import Optional, Literal, Dict, Any, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field, conlist

# ---------- Logging (fallback-safe) ----------
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        import logging
        logging.getLogger("relay.mcp").info("event=%s data=%s", event, (data or {}))

# ---------- Finalizer (fallback-safe) ----------
try:
    from services.answer_finalizer import finalize_envelope  # type: ignore
except Exception:  # pragma: no cover
    # Minimal finalizer: mimic /ask normalization contract
    def finalize_envelope(result: Dict[str, Any]) -> Dict[str, Any]:
        plan = result.get("plan")
        rr = result.get("routed_result")
        final_text = ""
        if isinstance(rr, dict):
            final_text = (rr.get("response") or rr.get("answer") or "") or ""
        elif isinstance(rr, str):
            final_text = rr
        if not final_text and isinstance(plan, dict):
            final_text = plan.get("final_answer") or ""
        env = {
            "plan": plan if isinstance(plan, dict) else None,
            "routed_result": rr if isinstance(rr, (dict, str)) else {},
            "critics": result.get("critics"),
            "context": result.get("context") or "",
            "files_used": result.get("files_used") or [],
            "meta": result.get("meta") or {},
            "final_text": final_text or "",
        }
        return env

from agents.mcp_agent import run_mcp  # your orchestrator (async)

# ---------- Optional dependencies ----------
try:
    from pybreaker import CircuitBreaker, CircuitBreakerError  # type: ignore
except Exception:  # pragma: no cover
    class CircuitBreakerError(Exception): ...
    class CircuitBreaker:  # no-op fallback
        def __init__(self, *_, **__): ...
        async def call(self, func, *args, **kwargs): return await func(*args, **kwargs)

try:
    from opentelemetry import trace  # type: ignore
    from opentelemetry.trace.status import Status, StatusCode  # type: ignore
    tracer = trace.get_tracer(__name__)
except Exception:  # pragma: no cover
    tracer = None
    class StatusCode: OK = "OK"; ERROR = "ERROR"  # type: ignore
    class Status:  # type: ignore
        def __init__(self, *_a, **_k): ...

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ---------- Models ----------
# ---------- Models ----------
from typing import List

AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]

class McpRunBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    role: Optional[AllowedRole] = Field(default="planner")
    files: Optional[conlist(str, max_items=16)] = None
    topics: Optional[conlist(str, max_items=16)] = None
    debug: bool = Field(default=False)
    timeout_s: int = Field(default=45, ge=1, le=120)
    max_context_tokens: Optional[int] = Field(default=120_000, ge=1024, le=300_000)


# ---------- Utilities ----------
def _jitter_backoff(attempt: int, base: float = 0.25, cap: float = 2.5) -> float:
    return min(cap, base * (2 ** attempt)) * random.random()

def _stable_error(message: str, code: str, request_id: str, extra_meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "final_text": "",
        "error": {"code": code, "message": message},
        "meta": {"request_id": request_id, **(extra_meta or {})},
    }

def _sanitize_list(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    if not values: return out
    seen = set()
    for v in values:
        s = (v or "").strip()
        if not s or s in seen: continue
        if ".." in s or "\x00" in s: continue  # path traversal guard
        seen.add(s); out.append(s)
    return out

mcp_cb = CircuitBreaker(fail_max=5, reset_timeout=30)

# ---------- Endpoints ----------
@router.get("/ping")
async def mcp_ping() -> Dict[str, str]:
    return {"status": "ok"}

@router.post("/run")
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    req_id = x_request_id or getattr(request.state, "corr_id", None) or uuid4().hex
    start = time.time()

    role = (body.role or "planner").strip() or "planner"
    files = _sanitize_list(body.files)
    topics = _sanitize_list(body.topics)
    timeout_s = int(body.timeout_s)
    debug = bool(body.debug)

    log_event("mcp_run_received", {
        "request_id": req_id,
        "role": role,
        "files_count": len(files),
        "topics_count": len(topics),
        "timeout_s": timeout_s,
        "debug": debug,
    })

    span_cm = tracer.start_as_current_span("mcp.run") if tracer else None
    if span_cm:
        span = span_cm.__enter__()  # type: ignore
        try:
            span.set_attribute("request.id", req_id)
            span.set_attribute("mcp.role", role)
            span.set_attribute("mcp.files_count", len(files))
            span.set_attribute("mcp.topics_count", len(topics))
            span.set_attribute("mcp.timeout_s", timeout_s)
        except Exception:  # pragma: no cover
            pass

    async def _invoke_once():
        try:
            return await run_mcp(
                query=body.query,
                files=files,
                topics=topics,
                role=role,
                user_id=None,          # inject real user if you have auth/session
                debug=debug,
                timeout_s=timeout_s,   # hint to downstream
                max_context_tokens=body.max_context_tokens,
                request_id=req_id,
            )
        except TypeError:
            # Back-compat signature
            return await run_mcp(
                query=body.query, files=files, topics=topics, role=role, user_id=None, debug=debug
            )

    attempts = 0
    try:
        async with asyncio.timeout(timeout_s):
            while True:
                try:
                    attempts += 1
                    result = await mcp_cb.call(_invoke_once)
                    break
                except CircuitBreakerError as cbe:
                    if span_cm:
                        try: span.record_exception(cbe); span.set_status(Status(StatusCode.ERROR))  # type: ignore
                        except Exception: pass
                    return _stable_error("Dependency unavailable (circuit open)", "CIRCUIT_OPEN", req_id)
                except Exception as e:
                    status = getattr(e, "status_code", None)
                    transient = status in (408, 423, 425, 429, 500, 502, 503, 504)
                    if not transient or attempts >= 3:
                        raise
                    await asyncio.sleep(_jitter_backoff(attempts))
    except asyncio.TimeoutError:
        if span_cm:
            try: span.set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception: pass
        return _stable_error("Operation timed out", "TIMEOUT", req_id)
    except Exception:
        if span_cm:
            try: span.set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception: pass
        return _stable_error("Unhandled server error", "UNHANDLED", req_id)

    # Finalize & stamp
    envelope = finalize_envelope(result or {})
    envelope.setdefault("meta", {}).update({"request_id": req_id})

    latency_ms = int((time.time() - start) * 1000)
    rr = envelope.get("routed_result") or {}
    log_event("mcp_run_completed", {
        "request_id": req_id,
        "role": role,
        "latency_ms": latency_ms,
        "attempts": attempts,
    })
    log_event("reply_summary", {
        "request_id": req_id,
        "route": (envelope.get("meta") or {}).get("route"),
        "origin": (envelope.get("meta") or {}).get("origin"),
        "plan_id": (envelope.get("meta") or {}).get("plan_id"),
        "final_len": len(envelope.get("final_text") or ""),
        "rr_has_answer": bool((rr or {}).get("answer")),
    })

    if span_cm:
        try: span.set_status(Status(StatusCode.OK))  # type: ignore
        except Exception: pass
        finally:
            span_cm.__exit__(None, None, None)  # type: ignore

    return envelope
