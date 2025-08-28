# File: main.py
# Purpose: FastAPI entrypoint for Relay Command Center (ask, control, status, docs, webhooks, integrations)
# Notes:
# - Loads .env in local dev
# - Hardened CORS (list and/or regex), strips stray delimiters
# - Optional OpenTelemetry → Jaeger (best-effort, never blocks)
# - Global JSON error handlers (prevents opaque 502s)
# - GZip compression
# - Startup: warm semantic index; validate KB index
# - Health: /live (liveness), /ready (readiness), /health (legacy), /version, /debug/routes

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── Local dev: load .env ─────────────────────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
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

# ── Optional: OpenTelemetry → Jaeger (best-effort) ───────────────────────────
OTEL_ENABLED = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    SERVICE = "relay-backend"
    JAEGER_HOST = os.getenv("JAEGER_HOST", "localhost")
    JAEGER_PORT = int(os.getenv("JAEGER_PORT", 6831))

    trace.set_tracer_provider(
        TracerProvider(resource=Resource.create({SERVICE_NAME: SERVICE}))
    )
    jaeger_exporter = JaegerExporter(agent_host_name=JAEGER_HOST, agent_port=JAEGER_PORT)
    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))
    OTEL_ENABLED = True
    log.info("🟣 OpenTelemetry on → Jaeger %s:%s", JAEGER_HOST, JAEGER_PORT)
except Exception as ex:
    log.warning("OTel disabled (%s: %s)", ex.__class__.__name__, ex)

# ── Ensure working dirs exist ────────────────────────────────────────────────
for sub in ("docs/imported", "docs/generated", "logs/sessions", "data/index"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend API for Relay agent – ask, control, status, docs, admin",
)

# GZip large responses (safe default)
app.add_middleware(GZipMiddleware, minimum_size=1024)

if OTEL_ENABLED:
    try:
        FastAPIInstrumentor().instrument_app(app)
    except Exception as ex:
        log.warning("OTel FastAPI instrumentation failed: %s", ex)

# ── CORS (prefer FRONTEND_ORIGIN; fallback to regex; dev='*') ────────────────
def _parse_origins(raw: Optional[str]) -> List[str]:
    """
    Parse comma/space/semicolon-separated origins safely.
    """
    if not raw:
        return []
    seps = [",", ";", " "]
    val = raw
    for s in seps:
        val = val.replace(s, ",")
    origins = [o.strip() for o in val.split(",") if o.strip()]
    return origins

origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX")  # e.g. ^https://.*\.wildfireranch\.us$
override_origin = os.getenv("FRONTEND_ORIGIN")     # e.g. https://status.wildfireranch.us,http://localhost:3000
cors_origins: List[str] = _parse_origins(override_origin)

if cors_origins:
    allow_creds = True
    log.info("🔒 CORS allow_origins: %s", cors_origins)
elif origin_regex:
    allow_creds = True
    log.info("🔒 CORS allow_origin_regex: %s", origin_regex)
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
    expose_headers=["Content-Disposition"],
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

# ── Global exception handlers (clean JSON; prevents opaque 502) ──────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"status": "error", "code": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse({"status": "error", "code": 422, "detail": exc.errors()}, status_code=422)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error at %s %s", request.method, request.url.path)
    return JSONResponse({"status": "error", "code": 500, "detail": "Internal server error"}, status_code=500)

# ── Startup: warm semantic index; validate KB index (non-blocking) ───────────
from services import kb

@app.on_event("startup")
def on_startup():
    # Self-heal semantic index (never crash if missing)
    try:
        from services.semantic_retriever import get_retriever
        get_retriever()  # warm-up/build if missing
        log.info("✅ Semantic index ready")
    except Exception as ex:
        log.error("❌ Semantic index warmup failed: %s", ex)

    # Validate KB index (best-effort)
    try:
        if not kb.index_is_valid():
            log.warning("📚 KB index missing/invalid — triggering rebuild…")
            log.info("Reindex result: %s", kb.api_reindex())
        else:
            log.info("✅ KB index validated on startup")
    except Exception as ex:
        log.error("KB index check failed: %s", ex)

# ── Health & misc endpoints ──────────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})

@app.get("/live")
def live():
    # Liveness: if process is up, return OK
    return JSONResponse({"status": "ok", "env": ENV_NAME})

@app.get("/ready")
def ready():
    # Readiness: ensure basic env and dirs exist; deeper checks can be added
    ok = True
    details: Dict[str, Any] = {}

    for key in ("API_KEY", "OPENAI_API_KEY"):
        present = bool(os.getenv(key))
        details[key] = present
        ok &= present

    for sub in ("docs/imported", "docs/generated", "data/index"):
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok &= exists

    return JSONResponse({"status": "ok" if ok else "error", "details": details}, status_code=200 if ok else 503)

@app.get("/health")
def health():
    # Backward-compatible health endpoint (aggregated)
    return ready()

@app.options("/test-cors")
def test_cors():
    return JSONResponse({"message": "CORS preflight success"})

@app.get("/version")
def version():
    try:
        from subprocess import check_output
        commit = check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        commit = "unknown"
    return {"git_commit": commit, "env": ENV_NAME}

@app.get("/debug/routes")
def debug_routes():
    return [{"path": r.path, "name": r.name} for r in app.router.routes]

# ── Dev entrypoint ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=(ENV_NAME == "local"),
    )
