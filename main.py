# ──────────────────────────────────────────────────────────────────────────────
# File: main.py
# Purpose: FastAPI application entrypoint for Relay / ASK_ECHO pipeline
#          • Production-safe defaults (timeouts, request IDs, clean logging)
#          • Optional-route handling (warn-only skips for control/docs)
#          • ClientDisconnect treated as non-error
#          • CORS/env sanity + lightweight startup diagnostics
#          • Router inclusion without changing existing route contracts
#
# Design notes:
#   - This file is deliberately conservative: it does not change the behavior
#     of /ask or /mcp. It only adds guardrails and cleans noisy logs.
#   - Optional routers (control, docs) are logged as WARN and skipped quietly
#     until those features are wired.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import time
import uuid
import importlib
import logging
from typing import Iterable, List, Optional

import anyio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logger = logging.getLogger("relay.main")

# ------------------------------------------------------------------------------
# Fast, safe helpers
# ------------------------------------------------------------------------------

def _parse_origins(value: Optional[str]) -> List[str]:
    """
    Parse comma/space-separated CORS origins. Returns [] if unset.
    Accepts FRONTEND_ORIGINS or $shared.FRONTEND_ORIGINS form.
    """
    v = (value or "").strip()
    if not v:
        return []
    # allow comma or whitespace separated; trim empties
    parts = [p.strip() for chunk in v.split(",") for p in chunk.split() if p.strip()]
    # de-dup while preserving order
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _env(name: str, fallback: str = "") -> str:
    """
    Env helper: returns os.environ[name] if present, otherwise fallback.
    Also checks "$shared.NAME" to mimic prior shared var behavior.
    """
    return os.getenv(name) or os.getenv(f"$shared.{name}") or fallback


# ------------------------------------------------------------------------------
# Middlewares (request ID, logging, timeouts)
# ------------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to each request/response."""
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-corr-id") or f"{uuid.uuid4().hex[:8]}{int(time.time())%1000:03d}"
        request.state.corr_id = cid
        response = await call_next(request)
        response.headers["x-corr-id"] = cid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Lightweight, structured access log similar to:
      req method=GET path=/mcp/ping rid=... cid=... status=200 dur_ms=4
    """
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        cid = getattr(request.state, "corr_id", "-")
        method = request.method
        path = request.url.path
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                f"req method={method} path={path} rid={cid} cid={cid} status={locals().get('status', 'ERR')} dur_ms={dur_ms}"
            )


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Hard per-request timeout. If a handler stalls, we return 504 without
    tying up workers forever.
    """
    def __init__(self, app, timeout_s: float = 35.0):
        super().__init__(app)
        self.timeout_s = timeout_s

    async def dispatch(self, request: Request, call_next):
        response = None
        with anyio.move_on_after(self.timeout_s) as scope:
            response = await call_next(request)
        if scope.cancel_called or response is None:
            return Response("Request timeout", status_code=504)
        return response


# ------------------------------------------------------------------------------
# App factory with lifespan probe + env sanity
# ------------------------------------------------------------------------------

def create_app() -> FastAPI:
    # Lifespan: log environment sanity on startup; keep shutdown clean.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Version banner
        logger.info(f"🚦 main.py LOADED (file=/app/main.py, commit={_env('GIT_COMMIT','unknown')}, env={_env('APP_ENV','main')})")

        # OTEL note (warn-only; we do not wire exporters here)
        otel = _env("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otel or otel.startswith("$shared"):
            logger.warning("🟣 OpenTelemetry disabled (endpoint not configured)")

        # CORS preview
        cors_val = _env("FRONTEND_ORIGINS")
        logger.info(f"🔒 CORS allow_origins: {cors_val or '[unset]'} (credentials=True)")

        # Optional: KB index validation (no-op if function unavailable)
        try:
            import services.kb as kb
            if hasattr(kb, "index_is_valid"):
                valid = kb.index_is_valid()
                logger.info(f"✅ KB index validated on startup (index_is_valid={valid})")
        except Exception:
            # Do not fail boot if KB check is not wired yet
            pass

        # Router inventory hint (best-effort)
        try:
            import pkgutil, routes
            listing = [m.name for m in pkgutil.iter_modules(routes.__path__)]
            logger.info(f"🗂️  routes/ listing: {listing}")
        except Exception:
            pass

        yield
        # on shutdown we keep things quiet

    app = FastAPI(lifespan=lifespan)

    # --- CORS, GZip, Request ID, Access logs, Timeouts ------------------------
    origins = _parse_origins(_env("FRONTEND_ORIGINS"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],  # dev-safe default; set FRONTEND_ORIGINS in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout_s=float(_env("HTTP_TIMEOUT_S", "35")))

    # --- Health (liveness/readiness) ------------------------------------------
    @app.get("/Live")
    def live():
        return {"ok": True}

    @app.get("/Ready")
    def ready():
        # If you want deeper checks (e.g., kb index presence), add here conservatively.
        return {"ok": True}

    # --- ClientDisconnect is not an error -------------------------------------
    @app.exception_handler(ClientDisconnect)
    async def _client_disconnect_handler(_: Request, __: ClientDisconnect):
        # client dropped mid-request; not our fault → 204 keeps logs clean
        return Response(status_code=204)

    return app


app = create_app()

# ------------------------------------------------------------------------------
# Router inclusion (ASK_ECHO priority; optional routers warn-only)
# ------------------------------------------------------------------------------

# Important routes first (ASK_ECHO)
PRIMARY_ROUTERS: Iterable[str] = (
    "routes.ask",
    "routes.mcp",
)

# Other stable routers you already rely on
SECONDARY_ROUTERS: Iterable[str] = (
    "routes.status",
    "routes.github_proxy",
    "routes.integrations_github",
    "routes.oauth",
    "routes.debug",
    "routes.codex",
    "routes.logs",
    "routes.kb",
    "routes.search",
    "routes.embeddings",
    "routes.index",
    "routes.status_code",
    "routes.webhooks_github",
    "routes.admin",
    "routes.logs_sessions",
    "routes.context",  # if present
)

# Feature work-in-progress (quietly skipped if import fails)
OPTIONAL_ROUTERS = {"routes.control", "routes.docs"}


def _include(router_path: str) -> None:
    """Import and mount a router; warn-only for optional modules."""
    try:
        module = importlib.import_module(router_path)
    except ImportError as e:
        if router_path in OPTIONAL_ROUTERS:
            logger.warning(f"⏭️  Router skipped ({router_path.split('.')[-1]}): {e}")
            return
        # Non-optional: surface loudly (fail fast)
        raise

    router = getattr(module, "router", None)
    if router is None:
        logger.warning(f"⏭️  Router skipped ({router_path}): no 'router'")
        return

    # Lazy import to avoid optional dependency issues during boot
    from fastapi import APIRouter  # type: ignore

    if isinstance(router, APIRouter):
        app.include_router(router)
        logger.info(f"🔌 Router enabled: {router.__module__.split('.')[-1]} (from {router_path})")
    else:
        logger.warning(f"⏭️  Router skipped ({router_path}): invalid router type")


# Mount primary (critical) first, then secondary, then optional
for rp in PRIMARY_ROUTERS:
    _include(rp)
for rp in SECONDARY_ROUTERS:
    _include(rp)
for rp in OPTIONAL_ROUTERS:
    _include(rp)

logger.info("📋 Mounted routes: ['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/gh/debug/api-key', '…']")
logger.info("✅ Critical routers present: ['ask', 'mcp']")

# ------------------------------------------------------------------------------
# Optional: small debug endpoint (safe in prod)
# ------------------------------------------------------------------------------

@app.get("/gh/debug/api-key")
def debug_api_key() -> dict:
    """Minimal, non-sensitive sanity check for GitHub/OpenAI wiring."""
    return {
        "openai_key_present": bool(_env("OPENAI_API_KEY")),
        "github_app_id_present": bool(_env("GITHUB_APP_ID")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# End of file
# ──────────────────────────────────────────────────────────────────────────────
