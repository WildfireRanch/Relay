# File: main.py
# Directory: project root
# Purpose: Relay backend FastAPI application (runtime‑only indexing, unified KB search, admin endpoints)
# Notes:
#   • Loads `.env` **only** when ENV=local
#   • CORS: prod uses explicit list; staging/preview allow "*" (x‑api‑key still required)
#   • Removes legacy embeddings route; all search goes through routes.search → services.kb
#   • Registers /admin/reindex (API‑key protected) for on‑demand KB rebuild
# Last Updated: 2025‑06‑13

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── Optional .env loading (local‑only) ────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("Loaded .env for local development")
    except ImportError:
        logging.warning("python‑dotenv not installed; skipping .env load")

ENV_NAME = os.getenv("ENV", "local")

# ─── Validate essential env vars ───────────────────────────────────────────
required_env = [
    "API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_CREDS_JSON",
]
missing = [k for k in required_env if not os.getenv(k)]
if missing:
    logging.error("Missing required env vars: %s", missing)
else:
    logging.info("✅ Required environment variables present")

# ─── Ensure docs directories exist ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
for sub in ["docs/imported", "docs/generated"]:
    path = PROJECT_ROOT / sub
    path.mkdir(parents=True, exist_ok=True)
    logging.debug("Ensured directory %s", path)

# ─── FastAPI application setup ─────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend for Relay agent: ask, status, control, docs, oauth, KB, admin",
)

# ─── CORS ──────────────────────────────────────────────────────────────────
frontend_origin_env = os.getenv("FRONTEND_ORIGIN", "").strip()

if ENV_NAME in {"staging", "preview"}:  # allow any origin during dev previews
    cors_origins = ["*"]
    allow_creds = False  # '*' not allowed with credentials=True
else:
    if frontend_origin_env:
        cors_origins = [o.strip() for o in frontend_origin_env.split(",") if o.strip()]
    else:
        cors_origins = [
            "https://relay.wildfireranch.us",
            "https://status.wildfireranch.us",
            "https://relay.staging.wildfireranch.us",
            "https://status.staging.wildfireranch.us",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    allow_creds = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.info("CORS origins=%s creds=%s", cors_origins, allow_creds)

# ─── Router imports ───────────────────────────────────────────────────────
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router
from routes.kb import router as kb_router
from routes.search import router as search_router
from routes import admin as admin_router

# ─── Register routers ─────────────────────────────────────────────────────
app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
app.include_router(kb_router)
app.include_router(search_router)
app.include_router(admin_router.router)

# ─── Health & root endpoints ───────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})


@app.get("/health")
def health_check():
    ok = True
    details: dict[str, bool] = {}
    for key in required_env:
        present = bool(os.getenv(key))
        details[key] = present
        ok = ok and present
    for sub in ["docs/imported", "docs/generated"]:
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok = ok and exists
    return JSONResponse({"status": "ok" if ok else "error", "details": details}, status_code=(200 if ok else 503))

# ─── Local dev entrypoint ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=ENV_NAME == "local",
    )