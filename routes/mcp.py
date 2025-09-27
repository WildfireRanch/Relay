# ──────────────────────────────────────────────────────────────────────────────
# File: routes/mcp.py
# Purpose: /mcp endpoints with lazy imports, structured errors, diagnostics,
#          and production-grade robustness (corr-id, timeouts, safe mode).
#
# Highlights
# - No module-level imports from agents/* or context to avoid circular deps.
# - Corr-ID precedence: X-Corr-Id → X-Request-Id → request.state.corr_id → uuid4
# - SAFE MODE fallback (echo agent) when mcp_agent import fails.
# - Context prebuild (GLOBAL + PROJECT_DOCS) using core.context_engine
#   with services.semantic_retriever.TieredSemanticRetriever.
# - Timeout enforcement for sync/async agents; kwargs filtered by signature.
# - Pydantic v1/v2 compatible validators.
# - Diagnostics: /mcp/diag and /mcp/diag_ctx
#
# Pylance-friendly notes
# - Use TYPE_CHECKING for optional types; avoid importing runtime-only modules
#   at top level. Dynamic imports are isolated inside route functions.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import traceback
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TYPE_CHECKING
from utils.async_helpers import maybe_await, filter_kwargs_for_callable
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    # Hints only (do not create import cycles at runtime)
    from pydantic.typing import AnyCallable

# --- Pydantic v1/v2 compatibility --------------------------------------------
try:
    from pydantic import BaseModel, Field  # type: ignore
    try:
        from pydantic import field_validator  # v2
        _PD_V2 = True
    except Exception:  # pragma: no cover
        from pydantic import validator as field_validator  # v1
        _PD_V2 = False
except Exception as _e:  # pragma: no cover
    raise RuntimeError("Pydantic is required") from _e

# --- Logging shim (uses core.logging if available) ----------------------------
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.mcp")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]

class McpRunBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    role: Optional[AllowedRole] = Field(default="planner")
    files: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    debug: bool = False
    timeout_s: int = Field(default=45, ge=1, le=180)

    if _PD_V2:
        @field_validator("query")
        @classmethod
        def _strip_query(cls, v: str) -> str:
            v = (v or "").strip()
            if not v:
                raise ValueError("query must be non-empty")
            return v
    else:
        @field_validator("query")
        def _strip_query(cls, v: str) -> str:  # type: ignore[no-redef]
            v = (v or "").strip()
            if not v:
                raise ValueError("query must be non-empty")
            return v

class ErrorEnvelope(BaseModel):
    error: str
    corr_id: str
    message: Optional[str] = None
    hint: Optional[str] = None

class McpEnvelope(BaseModel):
    plan: Optional[Dict[str, Any]] = None
    routed_result: Optional[Dict[str, Any] | str] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str = ""
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    final_text: str = ""

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

SAFE_MODE_ENV = "MCP_SAFE_MODE"

def _as_float(val: Any, default: float) -> float:
    try:
        return float(val) if val is not None else float(default)
    except Exception:
        return float(default)

def _as_int(val: Any, default: int) -> int:
    try:
        return int(val) if val is not None else int(default)
    except Exception:
        return int(default)


def _json_safe(obj: Any) -> Any:
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_safe(x) for x in obj]
        # Pydantic v1/v2 models
        if hasattr(obj, "model_dump"):
            return obj.model_dump()  # type: ignore[attr-defined]
        if hasattr(obj, "dict"):
            return obj.dict()  # type: ignore[attr-defined]
        return str(obj)
    except Exception:
        return "[unserializable]"

def _final_text_from(plan: Any, rr: Any, root_final: Optional[str] = None) -> str:
    # 1) explicit final_text at root
    if isinstance(root_final, str) and root_final.strip():
        return root_final
    # 2) routed_result fields
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
    # 3) plan fallback
    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa
    return ""


def _err(status: int, err: str, corr_id: str, *, hint: Optional[str] = None, message: Optional[str] = None) -> JSONResponse:
    payload: Dict[str, Any] = {"error": err, "corr_id": corr_id}
    if hint:
        payload["hint"] = hint
    if message:
        payload["message"] = message
    return JSONResponse(status_code=status, content=payload)

# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/ping")
async def mcp_ping() -> Dict[str, Any]:
    return {
        "status": "ok",
        "impl": "routes.mcp v6",
        "safe_mode": str(os.getenv(SAFE_MODE_ENV, "false")).lower() in ("1", "true", "yes"),
    }

@router.get("/diag")
async def mcp_diag() -> Dict[str, Any]:
    """
    Check FS visibility and importability of key modules without running agents.
    Never raises; returns error details inline for operator visibility.
    """
    out: Dict[str, Any] = {"fs": {}, "imports": {}, "checks": {}, "env": {}}

    # File system view
    routes_dir = Path(__file__).resolve().parent
    agents_dir = routes_dir.parent / "agents"
    core_dir = routes_dir.parent / "core"
    out["fs"]["routes_listing"] = sorted([p.name for p in routes_dir.iterdir()]) if routes_dir.exists() else "missing"
    out["fs"]["agents_listing"] = sorted([p.name for p in agents_dir.iterdir()]) if agents_dir.exists() else "missing"
    out["fs"]["core_listing"] = sorted([p.name for p in core_dir.iterdir()]) if core_dir.exists() else "missing"

    # Import probes (capture errors instead of raising)
    def probe(mod: str, attr: Optional[str] = None):
        try:
            m = importlib.import_module(mod)
            res = {"ok": True}
            if attr:
                res["has_attr"] = hasattr(m, attr)
            return res
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=6)}

    out["imports"]["agents.mcp_agent"] = probe("agents.mcp_agent", "run_mcp")
    out["imports"]["agents.echo_agent"] = probe("agents.echo_agent")
    out["imports"]["core.context_engine"] = probe("core.context_engine", "build_context")
    out["imports"]["services.token_budget"] = probe("services.token_budget")
    out["imports"]["services.semantic_retriever"] = probe("services.semantic_retriever", "TieredSemanticRetriever")
    out["imports"]["core.logging"] = probe("core.logging", "log_event")

    # Quick attribute check (doesn't fail diag)
    try:
        import agents.mcp_agent as m  # type: ignore
        out["checks"]["has_run_mcp"] = hasattr(m, "run_mcp")
    except Exception as e:
        out["checks"]["has_run_mcp"] = f"ERR: {e}"

    # Env flags that affect behavior
    out["env"]["MCP_SAFE_MODE"] = os.getenv(SAFE_MODE_ENV, "false")
    out["env"]["ASK_MIN_HITS"] = os.getenv("ASK_MIN_HITS")
    out["env"]["ASK_MIN_MAX_SCORE"] = os.getenv("ASK_MIN_MAX_SCORE")
    out["env"]["MAX_CONTEXT_TOKENS"] = os.getenv("MAX_CONTEXT_TOKENS")
    out["env"]["TOPK_GLOBAL"] = os.getenv("TOPK_GLOBAL")
    out["env"]["TOPK_PROJECT_DOCS"] = os.getenv("TOPK_PROJECT_DOCS")
    out["env"]["RERANK_MIN_SCORE_GLOBAL"] = os.getenv("RERANK_MIN_SCORE_GLOBAL")
    out["env"]["RERANK_MIN_SCORE_PROJECT_DOCS"] = os.getenv("RERANK_MIN_SCORE_PROJECT_DOCS")

    return out

@router.get("/diag_ctx")
async def mcp_diag_ctx(q: str = "Relay Command Center") -> Dict[str, Any]:
    """
    Lightweight diagnostics for context engine wiring. Does not build context.
    Returns stable engine_config values and cache status snapshot.
    """
    try:
        engine_config = {
            "topk_global": int(os.getenv("TOPK_GLOBAL", "4")),
            "topk_project_docs": int(os.getenv("TOPK_PROJECT_DOCS", "6")),
            "topk_code": int(os.getenv("TOPK_CODE", "6")),
            "rerank_min_score": float(os.getenv("RERANK_MIN_SCORE_GLOBAL", os.getenv("SEMANTIC_SCORE_THRESHOLD", "0.25"))),
            "max_context_tokens": int(os.getenv("MAX_CONTEXT_TOKENS", "4000")),
        }
    except Exception:
        engine_config = {}

    try:
        ctx = importlib.import_module("core.context_engine")
        cache = getattr(ctx, "cache_status")()
    except Exception as e:
        cache = {"ok": False, "error": str(e)}

    import time as _time
    return {
        "ok": True,
        "query": q,
        "impl": "routes.mcp.diag_ctx v1",
        "ts": int(_time.time()),
        "engine_config": engine_config,
        "cache_status": cache,
    }

# ──────────────────────────────────────────────────────────────────────────────
# /mcp/run
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/run",
    response_model=McpEnvelope,
    response_model_exclude_none=True,
    responses={400: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}, 504: {"model": ErrorEnvelope}},
)
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id"),
):
    """
    Execute MCP pipeline. If importing agents.mcp_agent fails and SAFE MODE is enabled
    (MCP_SAFE_MODE=true/1/yes), fallback to echo agent to keep the system responsive.
    Always tries to prebuild context so we can attach kb stats + grounding even when
    downstream agents don't.
    """
    corr_id = (
        (x_corr_id or "").strip()
        or (x_request_id or "").strip()
        or getattr(request.state, "corr_id", None)
        or uuid4().hex
    )

    # ── Prebuild context (GLOBAL + PROJECT_DOCS via SemanticRetriever) ────────
    context_text: str = ""
    files_used: List[Dict[str, Any]] = []
    kb_meta: Dict[str, Any] = {"hits": 0, "max_score": 0.0, "sources": []}
    grounding_from_ctx: List[Dict[str, Any]] = []

    try:
        ctx_mod = importlib.import_module("core.context_engine")
        build_context = getattr(ctx_mod, "build_context")
        ContextRequest = getattr(ctx_mod, "ContextRequest")
        EngineConfig = getattr(ctx_mod, "EngineConfig")
        RetrievalTier = getattr(ctx_mod, "RetrievalTier")

        sem = importlib.import_module("services.semantic_retriever")
        TieredSemanticRetriever = getattr(sem, "TieredSemanticRetriever")

        score_thresh_env = os.getenv("RERANK_MIN_SCORE_GLOBAL") or os.getenv("SEMANTIC_SCORE_THRESHOLD")
        score_thresh = float(score_thresh_env) if score_thresh_env else None

        retrievers = {
            RetrievalTier.GLOBAL:       TieredSemanticRetriever("global",        score_threshold=score_thresh),
            RetrievalTier.PROJECT_DOCS: TieredSemanticRetriever("project_docs",  score_threshold=score_thresh),
        }

        cfg = EngineConfig(retrievers=retrievers)
        ctx = build_context(ContextRequest(query=body.query, corr_id=corr_id), cfg)

        context_text = str(ctx.get("context") or "")
        _files = ctx.get("files_used") or []
        files_used = [{"path": p} for p in _files if isinstance(p, str)]

        kb = (ctx.get("meta") or {}).get("kb") or {}
        kb_meta = {
            "hits": int(kb.get("hits") or 0),
            "max_score": float(kb.get("max_score") or 0.0),
            "sources": list(kb.get("sources") or []),
        }

        grounding_from_ctx = [
            {"path": m.get("path"), "score": float(m.get("score", 0.0)), "tier": m.get("tier")}
            for m in (ctx.get("matches") or [])
            if isinstance(m, dict) and m.get("path")
        ]
    except Exception as e:
        # Context is optional; log and continue with empty stats.
        log_event("mcp_context_build_skipped", {"corr_id": corr_id, "error": str(e), "trace": traceback.format_exc(limit=6)})

    # ── Import agent lazily; if it fails, decide safe-mode or error ───────────
    try:
        mcp_agent = importlib.import_module("agents.mcp_agent")
        run_mcp = getattr(mcp_agent, "run_mcp")
    except Exception as e:
        log_event("mcp_import_error", {"corr_id": corr_id, "error": str(e), "trace": traceback.format_exc(limit=6)})

        # Router-level SAFE MODE (echo fallback) if enabled
        if str(os.getenv(SAFE_MODE_ENV, "false")).lower() in ("1", "true", "yes"):
            try:
                echo_agent = importlib.import_module("agents.echo_agent")
                echo_invoke = getattr(echo_agent, "invoke", None)
                text: str = ""
                if echo_invoke:
                    text = await maybe_await(
                        echo_invoke,
                        query=body.query,
                        context=context_text,
                        user_id="anonymous",
                        corr_id=corr_id,
                        timeout_s=body.timeout_s,
                    ) or ""
            except Exception as e2:
                log_event("mcp_safe_mode_echo_error", {"corr_id": corr_id, "error": str(e2)})
                text = ""

            return McpEnvelope(
                plan={"route": "echo", "_diag": {"safe_mode": True}},
                routed_result={"response": text, "route": "echo", "grounding": grounding_from_ctx},
                critics=None,
                context=context_text,
                files_used=files_used,
                meta={"request_id": corr_id, "route": "echo", "kb": kb_meta},
                final_text=text or "",
            )

        # No safe mode → structured 500
        return _err(
            500,
            "mcp_failed",
            corr_id,
            hint="Import agents.mcp_agent.run_mcp failed; see mcp_import_error",
            message=str(e),
        )

    # ── Normal path: run the agent with enforced timeout ──────────────────────
    log_event(
        "mcp_run_received",
        {
            "corr_id": corr_id,
            "role": (body.role or "planner"),
            "files_count": len(body.files or []),
            "topics_count": len(body.topics or []),
            "debug": body.debug,
        },
    )

    # Log the agent signature + what we plan to pass (helps quickly debug)
    try:
        import inspect as _inspect  # local import to avoid top-level weight
        _sig = str(_inspect.signature(run_mcp))
        log_event("mcp_run_sig", {"corr_id": corr_id, "signature": _sig})
    except Exception:
        pass

    try:
        # Build intended kwargs and filter to agent signature to avoid TypeError
        provided = dict(
            query=body.query,
            role=(body.role or "planner"),
            files=body.files or [],
            topics=body.topics or [],
            user_id="anonymous",
            debug=body.debug,
            corr_id=corr_id,
            context=context_text,
        )
        filtered = filter_kwargs_for_callable(run_mcp, **provided)
        log_event("mcp_run_call_args", {"corr_id": corr_id, "args": list(filtered.keys())})

        # Execute with timeout (works for sync/async agents)
        result = await maybe_await(run_mcp, **filtered, timeout_s=body.timeout_s)

        # Normalize common return types before any further use
        try:
            if hasattr(result, "model_dump"):
                result = result.model_dump()  # pydantic v2
            elif hasattr(result, "dict"):
                result = result.dict()        # pydantic v1
        except Exception as _e:
            log_event("mcp_result_normalize_warn", {"corr_id": corr_id, "error": str(_e)})

        if not isinstance(result, dict):
            result = {"routed_result": _json_safe(result)}

    except HTTPException:
        raise  # FastAPI-generated; bubble up
    except asyncio.TimeoutError:
        log_event("mcp_run_timeout", {"corr_id": corr_id, "timeout_s": body.timeout_s})
        return _err(504, "mcp_timeout", corr_id, hint="Agent exceeded timeout", message=f"{body.timeout_s}s")
    except Exception as e:
        trace = traceback.format_exc(limit=6)
        log_event("mcp_run_exception", {"corr_id": corr_id, "error": str(e), "trace": trace})
        return _err(
            500,
            "mcp_failed",
            corr_id,
            hint="agents.mcp_agent.run_mcp raised; see logs for 'mcp_run_exception'",
            message=str(e),
        )


    # Normalize possible Pydantic/custom objects
    try:
        if hasattr(result, "model_dump"):
            result = result.model_dump()  # pydantic v2
        elif hasattr(result, "dict"):
            result = result.dict()        # pydantic v1
    except Exception:
        pass
    if not isinstance(result, dict):
        result = {"routed_result": _json_safe(result)}

    plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
    rr = result.get("routed_result")
    critics = result.get("critics")

    # Prefer agent-provided context/files if present; otherwise fallback to ours
    context_out = str(result.get("context") or context_text or "")
    files_out = result.get("files_used") or files_used
    if isinstance(files_out, list) and files_out and isinstance(files_out[0], str):
        # normalize to list[dict] for UI consistency
        files_out = [{"path": p} for p in files_out]  # type: ignore[assignment]

    meta_in = result.get("meta")
    meta_in = meta_in if isinstance(meta_in, dict) else {}

    kb_from_agent = meta_in.get("kb")
    kb_from_agent = kb_from_agent if isinstance(kb_from_agent, dict) else {}

    hits = _as_int(kb_from_agent.get("hits"), kb_meta.get("hits", 0))
    max_score = _as_float(kb_from_agent.get("max_score"), kb_meta.get("max_score", 0.0))

# sources can be list[str] or list[dict]; normalize to list[str]
    sources_raw = kb_from_agent.get("sources")
    if isinstance(sources_raw, list):
        _srcs: List[str] = []
        for s in sources_raw:
            if isinstance(s, str):
                _srcs.append(s)
            elif isinstance(s, dict) and s.get("path"):
                _srcs.append(str(s["path"]))
            else:
                try:
                    _srcs.append(str(s))
                except Exception:
                    continue
        sources = _srcs or kb_meta.get("sources", [])
    else:
        sources = kb_meta.get("sources", [])

    kb_final = {"hits": hits, "max_score": max_score, "sources": sources}


    # Ensure envelope carries grounding; prefer agent, fallback to ctx
    grounding: List[Dict[str, Any]] = []
    if isinstance(rr, dict):
        grounding = rr.get("grounding") or []
    if not grounding:
        grounding = grounding_from_ctx

    final_text = _final_text_from(plan, rr, root_final=result.get("final_text"))

    envelope = McpEnvelope(
        plan=_json_safe(plan) if plan else None,
        routed_result=_json_safe(rr) if isinstance(rr, (dict, str)) else {},
        critics=_json_safe(critics) if critics is not None else None,
        context=context_out,
        files_used=_json_safe(files_out) if isinstance(files_out, list) else [],
        meta={**_json_safe(meta_in), "request_id": corr_id, "kb": kb_final},
        final_text=final_text or "",
    )

    log_event(
        "mcp_run_completed",
        {
            "corr_id": corr_id,
            "route": envelope.meta.get("route"),
            "kb_hits": ((envelope.meta.get("kb") or {}).get("hits")),
            "kb_max_score": ((envelope.meta.get("kb") or {}).get("max_score")),
            "final_len": len(envelope.final_text or ""),
        },
    )
    return envelope

# ──────────────────────────────────────────────────────────────────────────────
# Recommendations (next PRs)
# - Keep MCP_SAFE_MODE=true in prod until agents are fully stable; false in CI.
# - Add PYTHONPATH=. in Railway if imports of services/* ever fail.
# - Add circuit breaker: on repeated mcp_run failures, auto-enable SAFE MODE briefly.
# - Add unit tests for:
#   • diag imports ok
#   • safe mode on agent import failure
#   • context prebuild attaches kb with tiered retrievers
# ──────────────────────────────────────────────────────────────────────────────
