# ────────────────────────────────────────────────────────────────────────────
# File: main.py
# Directory: project root
# Purpose : FastAPI entrypoint for Relay backend
#           • ENV-aware CORS (incl. X-API-Key & OPTIONS)
#           • KB auto-heal on cold start
#           • Single-key security (API_KEY)
# Last Updated: 2025-06-16  (Echo – CORS hardening merge)
# ────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── .env for local dev ─────────────────────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("Loaded .env for local development")
    except ImportError:
        logging.warning("python-dotenv not installed; skipping .env load")

ENV_NAME = os.getenv("ENV", "local")

# ─── Basic env validation ──────────────────────────────────────────────────
for key in ("API_KEY", "OPENAI_API_KEY"):
    if not os.getenv(key):
        logging.error("Missing env var: %s", key)

# ─── Ensure docs dirs exist ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
for sub in ("docs/imported", "docs/generated"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ─── FastAPI app ───────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend for Relay agent: ask, status, control, docs, KB, admin",
)

# ─── CORS (ENV-aware, allows X-API-Key, forwards OPTIONS) ──────────────────
if ENV_NAME in {"staging", "preview"}:
    cors_origins = ["*"]               # open for Vercel/Netlify previews
    allow_creds = False                # '*' forces credentials → False
else:
    cors_origins = (
        [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]
        or [
            "https://relay.wildfireranch.us",
            "https://status.wildfireranch.us",
            "http://localhost:3000",
        ]
    )
    allow_creds = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "X-API-Key",
        "X-User-Id",
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
    ],
    expose_headers=["Content-Disposition"],
)
logging.info("CORS → origins=%s  creds=%s", cors_origins, allow_creds)

# ─── Router imports ────────────────────────────────────────────────────────
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router
from routes.kb import router as kb_router
from routes.search import router as search_router
from routes import admin as admin_router

# ─── Register routers ──────────────────────────────────────────────────────
app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
app.include_router(kb_router)
app.include_router(search_router)
app.include_router(admin_router.router)

# ─── KB auto-heal on startup ───────────────────────────────────────────────
from services import kb  # late import avoids circular deps

@app.on_event("startup")
def ensure_kb_index():
    """
    Rebuild KB index if:
      · directory missing   (first boot on fresh volume)
      · vector dim mismatch (model changed between deploys)
    """
    if not kb.index_is_valid():
        logging.warning("KB index invalid or missing → rebuilding…")
        logging.info(kb.api_reindex())
    else:
        logging.info("KB index valid – no rebuild needed")

# ─── Root & health endpoints ───────────────────────────────────────────────
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

# ─── Local dev entrypoint ──────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=ENV_NAME == "local",
    )
