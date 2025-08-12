# File: main.py
# Purpose: FastAPI entrypoint for Relay Command Center (ask, control, status, docs, webhooks)
# Notes:
# - Loads .env in local dev
# - Sets up CORS (static OR regex)
# - Optional OpenTelemetry tracing to Jaeger
# - Registers all routers, including GitHub webhooks (/webhooks/github)
# - Validates KB index on startup
# - Adds health, version, and CORS test endpoints

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Local dev: load .env ─────────────────────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("✅ Loaded .env for local development")
    except ImportError:
        logging.warning("⚠️ python-dotenv not installed; skipping .env load")

# ── Paths & ENV ──────────────────────────────────────────────────────────────
ENV_NAME = os.getenv("ENV", "local")
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# ── Basic logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ── Optional: OpenTelemetry → Jaeger ─────────────────────────────────────────
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
    logging.info(f"🟣 OpenTelemetry on → Jaeger {JAEGER_HOST}:{JAEGER_PORT}")
except Exception as ex:
    OTEL_ENABLED = False
    logging.warning(f"OTel disabled ({ex.__class__.__name__}: {ex})")

# ── Ensure working dirs exist ────────────────────────────────────────────────
for sub in ("docs/imported", "docs/generated", "logs/sessions"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend API for Relay agent – ask, control, status, docs, admin",
)

if OTEL_ENABLED:
    try:
        FastAPIInstrumentor().instrument_app(app)
    except Exception as ex:
        logging.warning(f"OTel FastAPI instrumentation failed: {ex}")

# ── CORS (prefer FRONTEND_ORIGIN; fallback to regex; dev='*') ────────────────
cors_origins: list[str] = []
origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX")
override_origin = os.getenv("FRONTEND_ORIGIN")

if override_origin:
    cors_origins = [o.strip() for o in override_origin.split(",") if o.strip()]
    allow_creds = True
    logging.info(f"🔒 CORS allow_origins: {cors_origins}")
elif origin_regex:
    allow_creds = True
    logging.info(f"🔒 CORS allow_origin_regex: {origin_regex}")
else:
    cors_origins = ["*"]
    allow_creds = False
    logging.warning("🔓 CORS DEBUG: allow_origins='*' (set FRONTEND_ORIGIN in prod)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not origin_regex else [],
    allow_origin_regex=origin_regex,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
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

if os.getenv("ENABLE_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes"):
    app.include_router(admin_router)
    logging.info("🛠️ Admin tools enabled")
else:
    logging.info("Admin tools disabled")

# ── Startup: validate KB index (non‑blocking) ────────────────────────────────
from services import kb

@app.on_event("startup")
def ensure_kb_index():
    try:
        if not kb.index_is_valid():
            logging.warning("📚 KB index missing/invalid — triggering rebuild…")
            logging.info("Reindex result: %s", kb.api_reindex())
        else:
            logging.info("✅ KB index validated on startup")
    except Exception as ex:
        logging.error(f"KB index check failed: {ex}")

# ── Health & misc endpoints ──────────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})

@app.get("/health")
def health_check():
    ok = True
    details: dict[str, bool | str] = {}

    for key in ("API_KEY", "OPENAI_API_KEY"):
        present = bool(os.getenv(key))
        details[key] = present
        ok &= present

    for sub in ("docs/imported", "docs/generated"):
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok &= exists

    details["env"] = ENV_NAME
    return JSONResponse({"status": "ok" if ok else "error", "details": details}, status_code=200 if ok else 503)

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

# ── Dev entrypoint ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=(ENV_NAME == "local"),
    )
