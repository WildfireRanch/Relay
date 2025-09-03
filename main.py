# File: main.py
# Purpose: FastAPI entrypoint for Relay Command Center (ask, control, status, docs, webhooks, integrations)
# Notes:
#   - /health: pure liveness (always 200) — good for Railway healthcheck
#   - /ready: strict readiness (503 until required env/dirs exist)
#   - OpenTelemetry: OTLP/HTTP exporter enabled when OTEL_EXPORTER_OTLP_ENDPOINT is set
#   - OTel instrumentation is idempotent and happens AFTER app creation
#   - No import-time instrumentation to avoid "already instrumented" warnings

from __future__ import annotations

import os
import sys
import logging
import time
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# ── Local dev: load .env (no-op in prod) ─────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        logging.info("✅ Loaded .env for local development")
    except Exception:
        logging.warning("⚠️ python-dotenv not installed or failed; skipping .env load")

# ── Paths & ENV ──────────────────────────────────────────────────────────────
ENV_NAME = os.getenv("ENV", "local")
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# ── Basic logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("relay.main")

# ── Ensure working dirs exist (before readiness checks) ──────────────────────
for sub in ("docs/imported", "docs/generated", "logs/sessions", "data/index"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ── OpenTelemetry (OTLP/HTTP) best-effort init (no instrumentation yet) ─────
#     Enable by setting:
#       OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example:4318
#     Optional:
#       OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>"
#       OTEL_RESOURCE_ATTRIBUTES="service.version=1.0.0,deployment.environment=prod"
OTEL_ENABLED = False
try:
    from opentelemetry import trace, metrics  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
        OTLPSpanExporter,
    )

    # Optional metrics wiring (disabled by default)
    # from opentelemetry.sdk.metrics import MeterProvider  # type: ignore
    # from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # type: ignore
    # from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # type: ignore

    SERVICE = os.getenv("OTEL_SERVICE_NAME", "relay-backend")
    OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    if OTLP_ENDPOINT:
        resource = Resource.create({"service.name": SERVICE})
        tp = TracerProvider(resource=resource)
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tp)

        # Metrics example (uncomment to enable)
        # mp = MeterProvider(
        #     resource=resource,
        #     metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        # )
        # metrics.set_meter_provider(mp)

        OTEL_ENABLED = True
        log.info("🟣 OpenTelemetry enabled → %s", OTLP_ENDPOINT)
    else:
        log.info("OTel not enabled (no OTEL_EXPORTER_OTLP_ENDPOINT)")

except Exception as ex:
    log.warning("OTel init failed (%s: %s)", ex.__class__.__name__, ex)
    OTEL_ENABLED = False

# We import instrumentation classes lazily later to avoid NameError if not installed
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
except Exception:
    FastAPIInstrumentor = None  # type: ignore
try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore
except Exception:
    HTTPXClientInstrumentor = None  # type: ignore
try:
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor  # type: ignore
except Exception:
    AioHttpClientInstrumentor = None  # type: ignore

# ── Request ID + timing middleware ───────────────────────────────────────────
REQUEST_ID_HEADER = "X-Request-Id"

class RequestIDAndTimingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or os.urandom(8).hex()
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.info(
                "req: method=%s path=%s rid=%s status=500 dur_ms=%d err=%s",
                request.method, request.url.path, rid, duration_ms, e.__class__.__name__,
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers[REQUEST_ID_HEADER] = rid
        log.info(
            "req: method=%s path=%s rid=%s status=%d dur_ms=%d",
            request.method, request.url.path, rid, response.status_code, duration_ms,
        )
        return response

# ── Security headers middleware (lightweight) ────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        # HSTS only if behind TLS and not in local
        if ENV_NAME != "local" and os.getenv("ENABLE_HSTS", "0").lower() in ("1", "true", "yes"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

# ── Lifespan: startup/shutdown (replaces on_event) ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.logging import log_event
    from services import kb

    # Warmers (best-effort; don’t block too long)
    try:
        from services.semantic_retriever import get_retriever  # if available
        get_retriever()
        log_event("startup_semantic_ready", {})
    except Exception as ex:
        log.warning("❌ Semantic index warmup failed: %s", ex)

    try:
        if hasattr(kb, "index_is_valid") and not kb.index_is_valid():
            log.warning("📚 KB index missing/invalid — triggering rebuild…")
            if hasattr(kb, "api_reindex"):
                log.info("Reindex result: %s", kb.api_reindex())
        else:
            log.info("✅ KB index validated on startup")
    except Exception as ex:
        log.error("KB index check failed: %s", ex)

    yield
    # (optional) add graceful shutdown here

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend API for Relay agent – ask, control, status, docs, admin",
    lifespan=lifespan,
)

# Middlewares
app.add_middleware(RequestIDAndTimingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ---- OTel auto-instrumentation (idempotent; after app exists) --------------
if OTEL_ENABLED:
    try:
        if not getattr(app, "_otel_instrumented", False):
            if FastAPIInstrumentor:
                FastAPIInstrumentor().instrument_app(app)
            if HTTPXClientInstrumentor:
                HTTPXClientInstrumentor().instrument()
            if AioHttpClientInstrumentor:
                AioHttpClientInstrumentor().instrument()
            app._otel_instrumented = True  # type: ignore[attr-defined]
            log.info("🟣 OTel instrumentation applied")
    except Exception as ex:
        log.warning("OTel instrumentation skipped: %s", ex)

# ── CORS ─────────────────────────────────────────────────────────────────────
def _parse_origins(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    for s in (",", ";", " "):
        raw = raw.replace(s, ",")
    return [o.strip() for o in raw.split(",") if o.strip()]

origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX")
override_origin = os.getenv("FRONTEND_ORIGIN")
cors_origins: List[str] = _parse_origins(override_origin)

if cors_origins:
    allow_creds = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("1", "true", "yes")
    log.info("🔒 CORS allow_origins: %s (credentials=%s)", cors_origins, allow_creds)
elif origin_regex:
    allow_creds = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("1", "true", "yes")
    log.info("🔒 CORS allow_origin_regex: %s (credentials=%s)", origin_regex, allow_creds)
else:
    cors_origins = ["*"]
    allow_creds = False
    log.warning("🔓 CORS DEBUG: allow_origins='*' (set FRONTEND_ORIGIN or FRONTEND_ORIGIN_REGEX in prod)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not origin_regex else [],
    allow_origin_regex=origin_regex,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Request-Id"],
)

# ── Routers (import after app init to avoid circulars) ───────────────────────
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router
from routes.kb import router as kb_router
from routes.search import router as search_router
from routes.admin import router as admin_router
from routes.codex import router as codex_router
from routes.mcp import router as mcp_router
from routes.logs import router as logs_router
from routes.webhooks_github import router as gh_webhooks
from routes.github_proxy import router as gh_proxy_router
from routes.integrations_github import router as gh_router

# Register routers (proxy first; then app core; then webhooks/integrations)
app.include_router(gh_proxy_router)
app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
app.include_router(kb_router)
app.include_router(search_router)
app.include_router(codex_router)
app.include_router(mcp_router)
app.include_router(logs_router)
app.include_router(gh_webhooks)
app.include_router(gh_router)

if os.getenv("ENABLE_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes"):
    app.include_router(admin_router)
    log.info("🛠️ Admin tools enabled")
else:
    log.info("Admin tools disabled")

# ── Global exception handlers ────────────────────────────────────────────────
from core.logging import log_event

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = request.headers.get(REQUEST_ID_HEADER)
    log_event("http_exception", {"rid": rid, "code": exc.status_code, "detail": exc.detail, "path": request.url.path})
    return JSONResponse(
        {"status": "error", "code": exc.status_code, "detail": exc.detail, "request_id": rid},
        status_code=exc.status_code,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = request.headers.get(REQUEST_ID_HEADER)
    log_event("validation_error", {"rid": rid, "errors": exc.errors(), "path": request.url.path})
    return JSONResponse({"status": "error", "code": 422, "detail": exc.errors(), "request_id": rid}, status_code=422)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = request.headers.get(REQUEST_ID_HEADER)
    log.exception("Unhandled error at %s %s", request.method, request.url.path)
    log_event("unhandled_exception", {"rid": rid, "path": request.url.path, "error": str(exc)})
    return JSONResponse({"status": "error", "code": 500, "detail": "Internal server error", "request_id": rid}, status_code=500)

# ── Health & misc endpoints ──────────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})

@app.get("/live")
def live():
    # Liveness: always 200. Use this path for Railway healthcheck.
    return JSONResponse({"status": "ok", "env": ENV_NAME})

@app.get("/ready")
def ready():
    # Readiness: 503 until required env + dirs exist.
    ok = True
    details: Dict[str, Any] = {}

    # Make OpenAI optional by env if desired.
    require_openai = os.getenv("REQUIRE_OPENAI", "1").lower() in ("1", "true", "yes")
    required_env = ["API_KEY"] + (["OPENAI_API_KEY"] if require_openai else [])

    if ENV_NAME == "local":
        for key in required_env:
            present = bool(os.getenv(key))
            details[key] = present
            ok &= present
    else:
        for key in required_env:
            ok &= bool(os.getenv(key))

    for sub in ("docs/imported", "docs/generated", "data/index"):
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists if ENV_NAME == "local" else "ok"
        ok &= exists

    return JSONResponse(
        {"status": "ok" if ok else "error", "details": details if ENV_NAME == "local" else {}},
        status_code=200 if ok else 503,
    )

@app.get("/health")
def health():
    # Pure liveness (distinct from readiness)
    return JSONResponse({"status": "ok"})

@app.options("/test-cors")
def test_cors():
    return JSONResponse({"message": "CORS preflight success"})

@app.get("/version")
def version():
    commit = os.getenv("GIT_SHA", "unknown")
    if commit == "unknown":
        try:
            # Short timeout to avoid blocking containers lacking git
            commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], timeout=0.5).decode().strip()
        except Exception:
            pass
    return {"git_commit": commit, "env": ENV_NAME}

@app.get("/debug/routes")
def debug_routes():
    return [{"path": r.path, "name": r.name} for r in app.router.routes]

# ── Dev entrypoint ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # Respect proxy headers if running behind one (optional)
    os.environ.setdefault("FORWARDED_ALLOW_IPS", "*")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),  # Railway sets $PORT
        reload=(ENV_NAME == "local"),
    )
