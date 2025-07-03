# File: main.py
# Directory: project root
# Purpose: Relay backend entrypoint for FastAPI with CORS, startup validation, router mounting, ENV awareness, and bulletproof OpenTelemetry tracing

from __future__ import annotations

import os
import logging
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── Load local environment (only in dev) ─────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("✅ Loaded .env for local development")
    except ImportError:
        logging.warning("⚠️ python-dotenv not installed; skipping .env load")

ENV_NAME = os.getenv("ENV", "local")
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# ─── OpenTelemetry Tracing Setup (Bulletproof, Inserted Here) ─────────────────
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter

    SERVICE = "relay-backend"
    JAEGER_HOST = os.getenv("JAEGER_HOST", "localhost")
    JAEGER_PORT = int(os.getenv("JAEGER_PORT", 6831))

    # Initialize the tracer provider with service name for full context
    trace.set_tracer_provider(
        TracerProvider(
            resource=Resource.create({SERVICE_NAME: SERVICE})
        )
    )

    # Configure Jaeger exporter for trace data
    jaeger_exporter = JaegerExporter(
        agent_host_name=JAEGER_HOST,
        agent_port=JAEGER_PORT,
    )
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )

    tracer = trace.get_tracer(__name__)
    logging.info(f"🟣 OpenTelemetry tracing enabled for service: {SERVICE} (Jaeger: {JAEGER_HOST}:{JAEGER_PORT})")
except ImportError as e:
    logging.warning(f"⚠️ OpenTelemetry tracing not enabled (missing packages): {e}")
except Exception as ex:
    logging.error(f"❌ OpenTelemetry setup failed: {ex}")

# ─── Validate required ENV vars ──────────────────────────────────────────────
for key in ("API_KEY", "OPENAI_API_KEY"):
    if not os.getenv(key):
        logging.error(f"❌ Missing required env var: {key}")

# ─── Ensure working directories exist ────────────────────────────────────────
for sub in ("docs/imported", "docs/generated"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ─── Initialize FastAPI ──────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend API for Relay agent – ask, control, status, docs, admin",
)

# ─── Instrument FastAPI with OpenTelemetry (All Requests Become Traces) ──────
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor().instrument_app(app)
    logging.info("🟣 OpenTelemetry FastAPI instrumentation active")
except ImportError:
    logging.warning("⚠️ opentelemetry-instrumentation-fastapi not installed; API traces will NOT be captured")
except Exception as ex:
    logging.error(f"❌ FastAPI OTel instrumentation failed: {ex}")

# ─── Configure CORS (support static or regex origin) ─────────────────────────
cors_origins = []
origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX")
override_origin = os.getenv("FRONTEND_ORIGIN")

if override_origin:
    cors_origins = [o.strip() for o in override_origin.split(",") if o.strip()]
    allow_creds = True
    logging.info(f"🔒 CORS restricted to: {cors_origins}")
elif origin_regex:
    allow_creds = True
    logging.info(f"🔒 CORS regex restriction: {origin_regex}")
else:
    cors_origins = ["*"]
    allow_creds = False
    logging.warning("🔓 CORS DEBUG MODE ENABLED: allow_origins='*', allow_credentials=False")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not origin_regex else [],
    allow_origin_regex=origin_regex,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ─── Import and mount routes ─────────────────────────────────────────────────
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

if os.getenv("ENABLE_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes"):
    app.include_router(admin_router)
    logging.info("🛠️ Admin tools enabled")
else:
    logging.info("Admin tools disabled (ENABLE_ADMIN_TOOLS not set)")

# ─── Startup: validate knowledge base ─────────────────────────────────────────
from services import kb

@app.on_event("startup")
def ensure_kb_index():
    if not kb.index_is_valid():
        logging.warning("📚 KB index missing or invalid — triggering rebuild…")
        logging.info("Reindex result: %s", kb.api_reindex())
    else:
        logging.info("✅ KB index validated on startup")

# ─── Health & CORS test routes ───────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})

@app.get("/health")
def health_check():
    ok = True
    details: dict[str, bool] = {}

    for key in ("API_KEY", "OPENAI_API_KEY"):
        present = bool(os.getenv(key))
        details[key] = present
        ok &= present

    for sub in ("docs/imported", "docs/generated"):
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok &= exists

    return JSONResponse(
        {"status": "ok" if ok else "error", "details": details},
        status_code=200 if ok else 503,
    )

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

# ─── Dev entrypoint ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=ENV_NAME == "local",
    )
