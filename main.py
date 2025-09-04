# File: main.py
# Purpose: FastAPI entrypoint for Relay Command Center (ask, control, status, docs, webhooks, integrations)
# Notes:
#   - /health, /live: pure liveness (always 200) — use one of these for Railway healthcheck
#   - /ready: strict readiness (503 until required env/dirs exist)
#   - Creates LOG_ROOT/SESSIONS_DIR/AUDIT_DIR on boot; safe fallback to /tmp if needed
#   - OpenTelemetry: OTLP/HTTP exporter enabled when OTEL_EXPORTER_OTLP_ENDPOINT is set
#   - OTel instrumentation is idempotent and happens AFTER app creation
#   - Router imports are guarded; missing optional routes won't crash startup

from __future__ import annotations

import os
import sys
import logging
import time
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

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

# ── Paths, ENV, logging ──────────────────────────────────────────────────────
ENV_NAME = os.getenv("ENV", "local")
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("relay.main")

# ── Safe directory provisioning (with /tmp fallback) ─────────────────────────
def _ensure_dir(path_str: str) -> Path:
    p = Path(path_str)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        # Last-resort fallback so we never crash on writes
        fallback = Path("/tmp") / p.name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

LOG_ROOT = os.getenv("LOG_ROOT", str(PROJECT_ROOT / "logs"))
SESSIONS_DIR = _ensure_dir(os.getenv("SESSIONS_DIR", f"{LOG_ROOT}/sessions"))
AUDIT_DIR = _ensure_dir(os.getenv("AUDIT_DIR", f"{LOG_ROOT}/audit"))
# Common project dirs used by routes/services
_ = [_ensure_dir(str(PROJECT_ROOT / sub)) for sub in ("docs/imported", "docs/generated", "data/index")]

# ── log_event: prefer core.logging; fallback to local shim ───────────────────
try:
    from core.logging import log_event  # type: ignore
except Exception:
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:  # type: ignore
        log.info("event=%s data=%s", event, (data or {}))

# ── OpenTelemetry (OTLP/HTTP) init (best-effort) ─────────────────────────────
OTEL_ENABLED = False
try:
    from opentelemetry import trace  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore

    SERVICE = os.getenv("OTEL_SERVICE_NAME", "relay-backend")
    OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    if OTLP_ENDPOINT:
        resource = Resource.create({"service.name": SERVICE})
        tp = TracerProvider(resource=resource)
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tp)
        OTEL_ENABLED = True
        log.info("🟣 OpenTelemetry enabled → %s", OTLP_ENDPOINT)
    else:
        log.info("OTel not enabled (no OTEL_EXPORTER_OTLP_ENDPOINT)")
except Exception as ex:
    log.warning("OTel init failed (%s: %s)", ex.__class__.__name__, ex)
    OTEL_ENABLED = False

# Lazy import instrumentors so missing deps don't crash
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
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            status = response.status_code
        except Exception as e:
            status = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.info("req method=%s path=%s rid=%s status=%s dur_ms=%d",
                     request.method, request.url.path, rid, status, duration_ms)
        # echo back request id
        try:
            response.headers[REQUEST_ID_HEADER] = rid
        except Exception:
            pass
        return response

# ── Security headers middleware (lightweight) ────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if ENV_NAME != "local" and os.getenv("ENABLE_HSTS", "0").lower() in ("1", "true", "yes"):
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

# ── Lifespan: startup/shutdown (replaces on_event) ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warmers (best effort; never crash startup)
    try:
        from services import kb  # type: ignore
        if hasattr(kb, "index_is_valid") and not kb.index_is_valid():
            log.warning("📚 KB index missing/invalid — triggering rebuild…")
            if hasattr(kb, "api_reindex"):
                log.info("Reindex result: %s", kb.api_reindex())
        else:
            log.info("✅ KB index validated on startup")
    except Exception as ex:
        log.warning("KB warmup skipped: %s", ex)
    yield
    # graceful shutdown hooks could go here

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version=os.getenv("RELay_VERSION", "1.0.0"),
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
allow_creds = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("1", "true", "yes")

if cors_origins:
    log.info("🔒 CORS allow_origins: %s (credentials=%s)", cors_origins, allow_creds)
elif origin_regex:
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

# ── Routers (guarded import/registration) ────────────────────────────────────
def _include(router_path: str, name: str) -> None:
    try:
        module = __import__(router_path, fromlist=["router"])
        app.include_router(module.router)
        log.info("🔌 Router enabled: %s", name)
    except Exception as ex:
        log.warning("⏭️  Router skipped (%s): %s", name, ex)

# Order: proxies first, core next, then webhooks/integrations
_include("routes.github_proxy", "github_proxy")
_include("routes.ask", "ask")
_include("routes.status", "status")
_include("routes.control", "control")
_include("routes.docs", "docs")
_include("routes.oauth", "oauth")
_include("routes.debug", "debug")
_include("routes.kb", "kb")
_include("routes.search", "search")
_include("routes.codex", "codex")
_include("routes.mcp", "mcp")
_include("routes.logs", "logs")
_include("routes.webhooks_github", "github_webhooks")
_include("routes.integrations_github", "integrations_github")

if os.getenv("ENABLE_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes"):
    _include("routes.admin", "admin")
else:
    log.info("Admin tools disabled")

# ── Exception handlers (structured, with request id) ─────────────────────────
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
    return {"message": "Relay Agent is Online", "env": ENV_NAME}

@app.get("/live")
def live():
    # Liveness: always 200. Good for Docker/Railway healthchecks.
    return {"status": "ok", "env": ENV_NAME}

@app.get("/health")
def health():
    # Alias to /live for platforms expecting /health
    return {"status": "ok"}

@app.get("/ready")
def ready():
    # Readiness: 503 until required env + dirs exist.
    ok = True
    details: Dict[str, Any] = {}

    # OpenAI optional via REQUIRE_OPENAI
    require_openai = os.getenv("REQUIRE_OPENAI", "1").lower() in ("1", "true", "yes")
    required_env = ["API_KEY"] + (["OPENAI_API_KEY"] if require_openai else [])

    for key in required_env:
        present = bool(os.getenv(key))
        details[key] = present if ENV_NAME == "local" else "set" if present else "missing"
        ok &= present

    for sub in ("docs/imported", "docs/generated", "data/index", SESSIONS_DIR.as_posix(), AUDIT_DIR.as_posix()):
        exists = Path(sub).exists()
        details[sub] = exists if ENV_NAME == "local" else "ok" if exists else "missing"
        ok &= exists

    return JSONResponse(
        {"status": "ok" if ok else "error", "details": details if ENV_NAME == "local" else {}},
        status_code=200 if ok else 503,
    )

@app.options("/test-cors")
def test_cors():
    return {"message": "CORS preflight success"}

@app.get("/version")
def version():
    commit = os.getenv("GIT_SHA", "unknown")
    if commit == "unknown":
        try:
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
    os.environ.setdefault("FORWARDED_ALLOW_IPS", "*")  # respect proxy headers if behind one
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),  # Railway sets $PORT
        reload=(ENV_NAME == "local"),
    )
