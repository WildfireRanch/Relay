# File: agents/mcp_agent.py
# Purpose: Normalize multi-agent orchestration for MCP with strong guarantees:
#   - Stable envelope and stringification for routed results
#   - Per-phase timeouts and limited retries with exponential backoff + jitter
#   - Graceful degradation to 'echo' when planner/route fails
#   - Connectivity observability: OpenTelemetry spans + metrics per dependency
#
# Contract (consumed by routes/mcp.py):
#   run_mcp(query, files, topics, role, user_id, debug, timeout_s, max_context_tokens, request_id) -> dict:
#     {
#       "plan": { "route": <str>, "plan_id": <str|None>, "final_answer": <str|None>, ... },
#       "routed_result": { "text": <str>, "answer": <str>, "response": <obj|str|None>, "error": <str|None> },
#       "meta": {
#         "origin": "mcp",
#         "route": <str>,
#         "plan_id": <str|None>,
#         "request_id": <str|None>,
#         "timings_ms": { "total": <int>, "planner": <int>, "routed": <int> },
#         "details": { "reply_head": <str|None> }  # mirrors planner.final_answer
#       }
#     }
#
# Telemetry:
#   - Spans: "mcp.planner", "mcp.echo", "mcp.docs", "mcp.codex", "mcp.control"
#     Attributes: dep, request.id, {files.count, topics.count} where relevant
#   - Metrics (services/telemetry): relay_connectivity_calls_total, relay_connectivity_latency_ms (Histogram),
#                                   relay_connectivity_errors_total, relay_connectivity_circuit_state
#
# Safety & performance:
#   - No unbounded strings (truncate very large serialized objects)
#   - Retry only on likely transient classes (408/429/5xx, etc.)
#   - Legacy agent signatures supported via adapters
#
# Dependencies expected in your repo:
#   - agents.planner_agent, agents.echo_agent, agents.docs_agent, agents.codex_agent, agents.control_agent
#   - core.logging.log_event
#   - OPTIONAL: services.telemetry.{tracer, record_dep_call, set_circuit_state}

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Dict, Optional, Callable, Awaitable

from core.logging import log_event
from agents import planner_agent, echo_agent, docs_agent, codex_agent, control_agent

# Optional telemetry helper (no-op safe)
try:
    from services.telemetry import tracer as _otel_tracer, record_dep_call, set_circuit_state
    from opentelemetry.trace.status import Status, StatusCode  # type: ignore
except Exception:  # pragma: no cover - keeps import optional
    def _otel_tracer():
        return None
    def record_dep_call(*args, **kwargs):
        return None
    def set_circuit_state(*args, **kwargs):
        return None
    class StatusCode:  # type: ignore
        OK = "OK"
        ERROR = "ERROR"
    class Status:  # type: ignore
        def __init__(self, *_args, **_kwargs):
            pass

# ------------------------------- Utilities -------------------------------------

_TRANSIENT_STATUS = {408, 423, 425, 429, 500, 502, 503, 504}
_MAX_JSON_LEN = 20000  # guardrail for stringifying bulky objects


def _now_ms() -> int:
    return int(time.time() * 1000)


def _jitter_backoff_sec(attempt: int, base: float = 0.25, cap: float = 2.5) -> float:
    """Exponential backoff with full jitter (AWS style)."""
    # min(cap, base * 2^attempt) * random[0,1)
    return min(cap, base * (2 ** attempt)) * random.random()


def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _safe_json(obj: Any) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(obj)
    return s if len(s) <= _MAX_JSON_LEN else s[:_MAX_JSON_LEN] + "…"


def _as_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (bytes, bytearray)):
        try:
            return x.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return _safe_json(x)


def _best_string(payload: Any) -> str:
    """
    Choose a human-readable string from a wide variety of payload shapes.
    Priority: 'text' → 'answer' → response.text/content/summary → response → compact JSON.
    """
    if payload is None:
        return ""
    if isinstance(payload, dict):
        for k in ("text", "answer"):
            v = payload.get(k)
            if _is_str(v) and v.strip():
                return v.strip()
        resp = payload.get("response")
        if _is_str(resp) and resp.strip():
            return resp.strip()
        if isinstance(resp, dict):
            for k in ("text", "content", "message", "summary", "recommendation"):
                v = resp.get(k)
                if _is_str(v) and v.strip():
                    return v.strip()
        return _as_str(payload)
    return _as_str(payload)


def _normalize_routed_result(raw: Any) -> Dict[str, Any]:
    """
    Normalize routed result to a stable UI-friendly shape.
    Ensures 'text' and/or 'answer' are present and that original payload is accessible as 'response'.
    """
    if raw is None:
        return {"text": "", "answer": "", "response": None, "error": None}

    if isinstance(raw, dict):
        text = _as_str(raw.get("text")) if raw.get("text") is not None else ""
        answer = _as_str(raw.get("answer")) if raw.get("answer") is not None else ""
        if not (text or answer):
            derived = _best_string(raw)
            if derived:
                text = derived
        response = raw if raw.get("response") is None else raw.get("response")
        err = raw.get("error")
        if err is not None and not _is_str(err):
            err = _as_str(err)
        return {
            "text": (text or "").strip(),
            "answer": (answer or "").strip(),
            "response": response,
            "error": err if err else None,
        }

    s = _best_string(raw)
    return {"text": s, "answer": s, "response": raw, "error": None}


def _looks_transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS:
        return True
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in _TRANSIENT_STATUS:
        return True
    msg = str(exc).lower()
    return any(t in msg for t in ("timed out", "timeout", "rate limit", "temporar", "unavailable", "try again"))


async def _call_with_deadline_and_retries(
    func: Callable[..., Awaitable[Any]],
    transient_pred: Callable[[Exception], bool],
    timeout_s: int,
    attempts: int = 3,
    *args,
    **kwargs,
) -> Any:
    """
    Run func with a hard per-call deadline and limited retries for transient failures.
    """
    last_exc: Optional[Exception] = None
    for i in range(1, attempts + 1):
        try:
            async with asyncio.timeout(timeout_s):
                return await func(*args, **kwargs)
        except asyncio.TimeoutError:
            # Immediate fail if phase deadline exceeded
            raise
        except Exception as e:
            last_exc = e
            if i >= attempts or not transient_pred(e):
                raise
            await asyncio.sleep(_jitter_backoff_sec(i))
    if last_exc:
        raise last_exc


# ------------------------------ Agent adapters ----------------------------------

async def _planner_plan(
    query: str,
    files: list[str],
    topics: list[str],
    *,
    debug: bool,
    timeout_s: int,
    max_context_tokens: Optional[int],
    request_id: Optional[str],
) -> Dict[str, Any]:
    """
    Adapter for planner_agent. Adds telemetry and tolerates legacy signatures.
    """
    async def _call_pref(**kw):
        return await planner_agent.plan(**kw)  # type: ignore[attr-defined]

    tr = _otel_tracer()
    t0 = _now_ms()
    if tr:
        with tr.start_as_current_span("mcp.planner") as span:  # connectivity span
            span.set_attribute("dep", "planner")
            span.set_attribute("request.id", request_id or "")
            span.set_attribute("files.count", len(files))
            span.set_attribute("topics.count", len(topics))
            try:
                res = await _call_with_deadline_and_retries(
                    _call_pref, _looks_transient, timeout_s,
                    query=query, files=files, topics=topics, debug=debug,
                    timeout_s=timeout_s, max_context_tokens=max_context_tokens, request_id=request_id
                )
                record_dep_call("planner", "planner", _now_ms() - t0, True, {"status": "ok"})
                span.set_status(Status(StatusCode.OK))
                return res or {}
            except TypeError:
                # legacy signature
                try:
                    res = await _call_with_deadline_and_retries(
                        lambda **kw: planner_agent.plan(**kw), _looks_transient, timeout_s,
                        query=query, files=files, topics=topics, debug=debug
                    )
                    record_dep_call("planner", "planner", _now_ms() - t0, True, {"status": "ok_legacy"})
                    span.set_status(Status(StatusCode.OK))
                    return res or {}
                except Exception as e:
                    record_dep_call("planner", "planner", _now_ms() - t0, False, {"error": type(e).__name__})
                    span.record_exception(e); span.set_status(Status(StatusCode.ERROR))
                    raise
            except Exception as e:
                record_dep_call("planner", "planner", _now_ms() - t0, False, {"error": type(e).__name__})
                span.record_exception(e); span.set_status(Status(StatusCode.ERROR))
                raise

    # Fallback without tracer
    try:
        return await _call_with_deadline_and_retries(
            _call_pref, _looks_transient, timeout_s,
            query=query, files=files, topics=topics, debug=debug,
            timeout_s=timeout_s, max_context_tokens=max_context_tokens, request_id=request_id
        ) or {}
    except TypeError:
        return await _call_with_deadline_and_retries(
            lambda **kw: planner_agent.plan(**kw), _looks_transient, timeout_s,
            query=query, files=files, topics=topics, debug=debug
        ) or {}


async def _echo_answer(
    query: str, context: Dict[str, Any], *, debug: bool, timeout_s: int, request_id: Optional[str]
) -> Any:
    async def _call(**kw):
        if hasattr(echo_agent, "answer"):
            return await echo_agent.answer(**kw)  # type: ignore[attr-defined]
        return await echo_agent.respond(**kw)     # type: ignore[attr-defined]

    tr = _otel_tracer(); t0 = _now_ms()
    if tr:
        with tr.start_as_current_span("mcp.echo") as span:
            span.set_attribute("dep", "echo")
            span.set_attribute("request.id", request_id or "")
            try:
                res = await _call_with_deadline_and_retries(
                    _call, _looks_transient, timeout_s,
                    query=query, context=context, debug=debug, request_id=request_id
                )
                record_dep_call("echo", "echo", _now_ms() - t0, True, {"status": "ok"})
                span.set_status(Status(StatusCode.OK))
                return res
            except Exception as e:
                record_dep_call("echo", "echo", _now_ms() - t0, False, {"error": type(e).__name__})
                span.record_exception(e); span.set_status(Status(StatusCode.ERROR)); raise

    return await _call_with_deadline_and_retries(
        _call, _looks_transient, timeout_s, query=query, context=context, debug=debug, request_id=request_id
    )


async def _docs_summarize(
    query: str, files: list[str], *, debug: bool, timeout_s: int, request_id: Optional[str]
) -> Any:
    async def _call(**kw):
        for name in ("summarize", "analyze", "run", "answer"):
            if hasattr(docs_agent, name):
                return await getattr(docs_agent, name)(**kw)  # type: ignore[misc]
        raise RuntimeError("docs agent has no callable entrypoint")

    tr = _otel_tracer(); t0 = _now_ms()
    if tr:
        with tr.start_as_current_span("mcp.docs") as span:
            span.set_attribute("dep", "docs")
            span.set_attribute("request.id", request_id or "")
            try:
                res = await _call_with_deadline_and_retries(
                    _call, _looks_transient, timeout_s,
                    query=query, files=files, debug=debug, request_id=request_id
                )
                record_dep_call("docs", "docs", _now_ms() - t0, True, {"status": "ok"})
                span.set_status(Status(StatusCode.OK)); return res
            except Exception as e:
                record_dep_call("docs", "docs", _now_ms() - t0, False, {"error": type(e).__name__})
                span.record_exception(e); span.set_status(Status(StatusCode.ERROR)); raise

    return await _call_with_deadline_and_retries(
        _call, _looks_transient, timeout_s, query=query, files=files, debug=debug, request_id=request_id
    )


async def _codex_run(
    query: str, files: list[str], topics: list[str], *, debug: bool, timeout_s: int, request_id: Optional[str]
) -> Any:
    async def _call(**kw):
        for name in ("run", "answer", "execute"):
            if hasattr(codex_agent, name):
                return await getattr(codex_agent, name)(**kw)  # type: ignore[misc]
        raise RuntimeError("codex agent has no callable entrypoint")

    tr = _otel_tracer(); t0 = _now_ms()
    if tr:
        with tr.start_as_current_span("mcp.codex") as span:
            span.set_attribute("dep", "codex")
            span.set_attribute("request.id", request_id or "")
            try:
                res = await _call_with_deadline_and_retries(
                    _call, _looks_transient, timeout_s,
                    query=query, files=files, topics=topics, debug=debug, request_id=request_id
                )
                record_dep_call("codex", "codex", _now_ms() - t0, True, {"status": "ok"})
                span.set_status(Status(StatusCode.OK)); return res
            except Exception as e:
                record_dep_call("codex", "codex", _now_ms() - t0, False, {"error": type(e).__name__})
                span.record_exception(e); span.set_status(Status(StatusCode.ERROR)); raise

    return await _call_with_deadline_and_retries(
        _call, _looks_transient, timeout_s, query=query, files=files, topics=topics, debug=debug, request_id=request_id
    )


async def _control_run(
    query: str, topics: list[str], *, debug: bool, timeout_s: int, request_id: Optional[str]
) -> Any:
    async def _call(**kw):
        for name in ("run", "answer", "execute"):
            if hasattr(control_agent, name):
                return await getattr(control_agent, name)(**kw)  # type: ignore[misc]
        raise RuntimeError("control agent has no callable entrypoint")

    tr = _otel_tracer(); t0 = _now_ms()
    if tr:
        with tr.start_as_current_span("mcp.control") as span:
            span.set_attribute("dep", "control")
            span.set_attribute("request.id", request_id or "")
            try:
                res = await _call_with_deadline_and_retries(
                    _call, _looks_transient, timeout_s,
                    query=query, topics=topics, debug=debug, request_id=request_id
                )
                record_dep_call("control", "control", _now_ms() - t0, True, {"status": "ok"})
                span.set_status(Status(StatusCode.OK)); return res
            except Exception as e:
                record_dep_call("control", "control", _now_ms() - t0, False, {"error": type(e).__name__})
                span.record_exception(e); span.set_status(Status(StatusCode.ERROR)); raise

    return await _call_with_deadline_and_retries(
        _call, _looks_transient, timeout_s, query=query, topics=topics, debug=debug, request_id=request_id
    )


# ------------------------------ Public entrypoint -------------------------------

async def run_mcp(
    *,
    query: str,
    files: Optional[list[str]] = None,
    topics: Optional[list[str]] = None,
    role: Optional[str] = "planner",
    user_id: Optional[str] = None,   # reserved
    debug: bool = False,
    timeout_s: int = 45,
    max_context_tokens: Optional[int] = 120_000,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Orchestrate planner → routed agent, normalize outputs, attach meta & connectivity telemetry.
    Routes should still call finalize_envelope(...) to guarantee final_text.
    """
    t0 = _now_ms()
    files = files or []
    topics = topics or []

    # --- Phase 1: Planner (unless role override provided)
    do_planner = role in (None, "planner")
    plan: Dict[str, Any] = {}
    route: str = role or "planner"
    plan_id: Optional[str] = None
    reply_head: Optional[str] = None

    # Budget split: ~45% planner, remainder routed (ensures both phases have time)
    planner_budget = max(1, int(timeout_s * 0.45))
    routed_budget = max(1, timeout_s - planner_budget)

    if do_planner:
        pt0 = _now_ms()
        try:
            plan = await _planner_plan(
                query, files, topics,
                debug=debug,
                timeout_s=planner_budget,
                max_context_tokens=max_context_tokens,
                request_id=request_id
            )
        except asyncio.TimeoutError:
            plan = {"route": "echo", "final_answer": None, "error": "planner_timeout"}
        except Exception as e:
            plan = {"route": "echo", "final_answer": None, "error": f"planner_error:{type(e).__name__}"}
        pt1 = _now_ms()
        route = plan.get("route") or "echo"
        plan_id = plan.get("plan_id")
        reply_head = (plan.get("final_answer") or "") or None
    else:
        pt0 = pt1 = _now_ms()

    # Explicit role override (docs/codex/control/echo)
    if role and role not in ("planner",):
        route = role

    # --- Phase 2: Routed agent
    rt0 = _now_ms()
    routed_raw: Any = None
    try:
        phase_budget = max(1, routed_budget)
        if route == "echo":
            ctx = {"plan": plan, "files": files, "topics": topics}
            routed_raw = await _echo_answer(query, ctx, debug=debug, timeout_s=phase_budget, request_id=request_id)
        elif route == "docs":
            routed_raw = await _docs_summarize(query, files, debug=debug, timeout_s=phase_budget, request_id=request_id)
        elif route == "codex":
            routed_raw = await _codex_run(query, files, topics, debug=debug, timeout_s=phase_budget, request_id=request_id)
        elif route == "control":
            routed_raw = await _control_run(query, topics, debug=debug, timeout_s=phase_budget, request_id=request_id)
        else:
            # Unknown route → echo fallback with context note
            ctx = {"plan": plan, "files": files, "topics": topics, "note": f"unknown route '{route}'"}
            routed_raw = await _echo_answer(query, ctx, debug=debug, timeout_s=phase_budget, request_id=request_id)
            route = "echo"
    except asyncio.TimeoutError:
        routed_raw = {"error": f"{route}_timeout", "text": f"{route} timed out while processing."}
    except Exception as e:
        routed_raw = {"error": f"{route}_error:{type(e).__name__}", "text": f"{route} failed: {str(e)}"}
    rt1 = _now_ms()

    # --- Normalization & meta
    routed_result = _normalize_routed_result(routed_raw)
    meta = {
        "origin": "mcp",
        "route": route,
        "plan_id": plan_id,
        "request_id": request_id,
        "timings_ms": {
            "total": _now_ms() - t0,
            "planner": max(0, pt1 - pt0),
            "routed": max(0, rt1 - rt0),
        },
        "details": {"reply_head": reply_head},
    }

    log_event("mcp_orchestrated", {
        "route": route,
        "plan_id": plan_id,
        "planner_has_final": bool(reply_head),
        "routed_has_answer": bool((routed_result.get("answer") or routed_result.get("text") or "").strip()),
        "timings_ms": meta["timings_ms"],
        "request_id": request_id,
    })

    return {"plan": plan, "routed_result": routed_result, "meta": meta}
