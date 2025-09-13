"""
Entry point for the Relay/ASK_ECHO FastAPI application.

This version consolidates configuration into a single factory, properly
configures CORS, adds Prometheus metrics, structured logging and a
correlation ID, and provides comprehensive error handling.  Health
checks and router mounting are explicitly defined to make the app
production‑ready and easier to maintain.
"""
from __future__ import annotations

import importlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Iterable, List, Optional, AsyncIterator

import anyio
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect

# ----------------------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------------------
logger = logging.getLogger("relay.main")

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _parse_origins(value: Optional[str]) -> List[str]:
    """Parse comma/space‑separated CORS origins into a list."""
    v = (value or "").strip()
    if not v:
        return []
    parts = [p.strip() for chunk in v.split(",") for p in chunk.split() if p.strip()]
    # De‑duplicate while preserving order
    seen: set[str] = set()
    out: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _env(name: str, fallback: str = "") -> str:
    """Return environment variable `name` if present, else fallback.

    Also checks `$shared.NAME` to mimic prior shared variable behaviour.
    """
    return os.getenv(name) or os.getenv(f"$shared.{name}") or fallback

# ----------------------------------------------------------------------------
# Middleware definitions
# ----------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique correlation ID to each request and propagate it.

    A correlation ID aids in tracing a single request through the system.
    It is sent back to the client via the `x-corr-id` header.
    """
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-corr-id") or f"{uuid.uuid4().hex[:8]}{int(time.time())%1000:03d}"
        request.state.corr_id = cid
        response = await call_next(request)
        response.headers["x-corr-id"] = cid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log basic access information for each request at INFO level."""

    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        cid = getattr(request.state, "corr_id", "-")
        method = request.method
        path = request.url.path
        status: str | int = "ERR"
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                f"req method={method} path={path} rid={cid} cid={cid} status={status} dur_ms={dur_ms}"
            )


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Abort requests that exceed a configurable time limit.

    If a handler stalls for longer than `timeout_s` seconds, a 504 response
    is returned.  This prevents hung connections from tying up worker
    threads indefinitely.
    """
    def __init__(self, app: FastAPI, timeout_s: float = 35.0):
        super().__init__(app)
        self.timeout_s = timeout_s

    async def dispatch(self, request: Request, call_next):
        response: Optional[Response] = None
        # Use AnyIO's cancel scope for timeouts
        with anyio.move_on_after(self.timeout_s) as scope:
            response = await call_next(request)
        if scope.cancel_called or response is None:
            return Response("Request timeout", status_code=504)
        return response


# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect metrics for each request using Prometheus counters and histograms."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path
        with REQUEST_LATENCY.labels(method, endpoint).time():
            response = await call_next(request)
        REQUEST_COUNT.labels(method, endpoint, str(getattr(response, "status_code", 500))).inc()
        return response

# ----------------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This factory encapsulates all setup: middleware, CORS, metrics, error
    handlers, health endpoints and router inclusion.  It returns a
    configured `FastAPI` instance ready to run in production.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan context manager for startup and shutdown hooks."""
        # Log version banner on startup
        logger.info(
            f"\U0001F6A6 main.py LOADED (file=/app/main.py, commit={_env('GIT_COMMIT','unknown')}, env={_env('APP_ENV','main')})"
        )

        # Warn if OpenTelemetry is disabled
        otel = _env("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otel or otel.startswith("$shared"):
            logger.warning("\U0001F7E3 OpenTelemetry disabled (endpoint not configured)")

        # Log intended CORS origins
        cors_val = _env("FRONTEND_ORIGINS")
        logger.info(f"\U0001F512 CORS allow_origins: {cors_val or '[unset]'}")

        # Validate KB index on startup if available
        try:
            import services.kb as kb  # type: ignore
            if hasattr(kb, "index_is_valid"):
                valid = kb.index_is_valid()
                logger.info(f"✅ KB index validated on startup (index_is_valid={valid})")
        except Exception:
            pass

        # List available routes for debugging
        try:
            import pkgutil, routes  # type: ignore
            listing = [m.name for m in pkgutil.iter_modules(routes.__path__)]
            logger.info(f"\U0001F5C2 routes/ listing: {listing}")
        except Exception:
            pass

        yield
        # Shutdown: nothing special needed at the moment

    # Create application with lifespan hooks
    app = FastAPI(lifespan=lifespan)

    # ----------------------------------------------------------------------
    # Configure CORS
    # ----------------------------------------------------------------------
    origins_raw = _env("FRONTEND_ORIGINS")  # e.g. "https://status.wildfireranch.us"
    origins = _parse_origins(origins_raw)
    if origins:
        cors_allow_origins = origins  # explicit list
        cors_allow_credentials = True
    else:
        cors_allow_origins = ["*"]  # development fallback
        cors_allow_credentials = False  # cannot use credentials with wildcard

    # ----------------------------------------------------------------------
    # Middleware registration (order matters)
    # ----------------------------------------------------------------------
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    timeout_s = float(_env("HTTP_TIMEOUT_S", "35"))
    app.add_middleware(TimeoutMiddleware, timeout_s=timeout_s)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(
        f"CORS configured: origins={cors_allow_origins} credentials={cors_allow_credentials}"
    )

    # ----------------------------------------------------------------------
    # Built‑in endpoints
    # ----------------------------------------------------------------------
    @app.get("/live", tags=["health"])
    def live() -> dict[str, bool]:
        """Liveness probe: returns OK immediately."""
        return {"ok": True}

    @app.get("/ready", tags=["health"])
    def ready() -> dict[str, bool]:
        """Readiness probe: extend here to check DB or other dependencies."""
        # Insert deeper checks (e.g., DB connectivity) as needed
        return {"ok": True}

    @app.get("/debug/routes", tags=["debug"])
    def debug_routes() -> List[dict[str, object]]:
        """Return a list of mounted routes for debugging."""
        return [
            {
                "path": r.path,
                "name": getattr(r, "name", None),
                "methods": sorted(list((r.methods or set()))),
            }
            for r in app.router.routes
        ]

    @app.exception_handler(ClientDisconnect)
    async def client_disconnect_handler(
        _: Request, __: ClientDisconnect
    ) -> Response:
        """Return HTTP 204 when the client disconnects mid‑request (not an error)."""
        return Response(status_code=204)

    # Expose Prometheus metrics
    @app.get("/metrics", tags=["metrics"])
    def metrics() -> Response:
        """Return Prometheus metrics in the text exposition format."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Custom error handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Return structured JSON responses for HTTP exceptions with correlation ID."""
        cid = getattr(request.state, "corr_id", "-")
        return JSONResponse(
            {"detail": exc.detail, "status_code": exc.status_code, "corr_id": cid},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all handler for unhandled exceptions.

        Logs the exception and returns a generic 500 response containing the
        correlation ID.
        """
        cid = getattr(request.state, "corr_id", "-")
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            {"detail": "Internal server error", "status_code": 500, "corr_id": cid},
            status_code=500,
        )

    # ----------------------------------------------------------------------
    # Router inclusion logic
    # ----------------------------------------------------------------------
    PRIMARY_ROUTERS: Iterable[str] = (
        "routes.ask",
        "routes.mcp",
    )

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
        "routes.context",
    )

    OPTIONAL_ROUTERS = {"routes.control", "routes.docs"}
    _mounted: set[str] = set()

    def _include(router_path: str) -> None:
        """Import and mount a router.

        If the router is optional and missing, log a warning. If it is mandatory
        and missing, re‑raise the ImportError. Duplicate imports are skipped.
        """
        if router_path in _mounted:
            return
        try:
            module = importlib.import_module(router_path)
        except ImportError as e:
            if router_path in OPTIONAL_ROUTERS:
                logger.warning(
                    f"\U000023ED️ Router skipped ({router_path.split('.')[-1]}): {e}"
                )
                return
            # Non‑optional: surface the error
            raise

        router = getattr(module, "router", None)
        if not isinstance(router, APIRouter):
            logger.warning(
                f"\U000023ED️ Router skipped ({router_path}): no/invalid 'router'"
            )
            return

        app.include_router(router)
        _mounted.add(router_path)
        logger.info(
            f"🔌 Router enabled: {router.__module__.split('.')[-1]} (from {router_path})"
        )

    # Mount routers in order: critical first, then secondary, then optional
    for rp in PRIMARY_ROUTERS:
        _include(rp)
    for rp in SECONDARY_ROUTERS:
        _include(rp)
    for rp in OPTIONAL_ROUTERS:
        _include(rp)

    logger.info("✅ Critical routers present: ['ask', 'mcp']")

    # Small debug endpoint for GitHub/OpenAI wiring
    @app.get("/gh/debug/api-key", tags=["debug"])
    def debug_api_key() -> dict[str, bool]:
        """Return a minimal sanity check for GitHub and OpenAI credentials."""
        return {
            "openai_key_present": bool(_env("OPENAI_API_KEY")),
            "github_app_id_present": bool(_env("GITHUB_APP_ID")),
        }

    return app


# Instantiate the application
app = create_app()
