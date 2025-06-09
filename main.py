# File: main.py
# Directory: project root
# Purpose: Relay backend FastAPI application
#  - Loads environment variables
#  - Validates critical configs
#  - Applies CORS for dev and production origins
#  - Mounts modular route groups (ask, status, control, docs, oauth, debug)
#  - Provides health and preflight endpoints
#  - Ensures required directories exist for docs import/generation
#  - Supports both local (uvicorn) and Railway deployment

from dotenv import load_dotenv
import os
from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

# === Load environment configuration ===
load_dotenv()  # load .env into os.environ

# === Validate essential environment variables ===
required_env = ["API_KEY", "OPENAI_API_KEY", "GOOGLE_CREDS_JSON"]
missing = [key for key in required_env if not os.getenv(key)]
if missing:
    logging.error(f"Missing required env vars: {missing}")
    # In production, you might want to raise or exit
    # raise RuntimeError(f"Missing required env vars: {missing}")
else:
    logging.info("✅ All required environment variables are present.")

# === Ensure docs directories exist ===
PROJECT_ROOT = Path(__file__).resolve().parent
for sub in ["docs/imported", "docs/generated"]:
    path = PROJECT_ROOT / sub
    path.mkdir(parents=True, exist_ok=True)
    logging.debug(f"Ensured directory: {path}")

# === Initialize FastAPI app ===
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend for Relay agent: routes for ask, status, control, docs, oauth, and debug"
)

# === Configure CORS ===
# In production, replace wildcard or list with env-driven ORIGINS
frontend_origins = [
    os.getenv("PROD_ORIGIN", "https://relay.wildfireranch.us"),
    "http://localhost:3000"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.info(f"CORS configured for origins: {frontend_origins}")

# === Mount route modules ===
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router

app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
logging.info("✅ Registered all route modules.")

# === Global preflight handler ===
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    """Return 200 for all OPTIONS requests."""
    return Response(status_code=200)

# === Health check endpoint ===
@app.get("/", summary="Health check")
def root():
    """Basic sanity check for load balancers and uptime monitoring."""
    return JSONResponse({"message": "Relay Agent is Online"})

# === Production-ready validation endpoint ===
@app.get("/health", summary="Readiness and liveness probe")
def health_check():
    """Check service readiness: verifies docs dirs and key env vars."""
    ok = True
    details = {}
    # Env var check
    for key in required_env:
        present = bool(os.getenv(key))
        details[key] = present
        ok = ok and present
    # Directory check
    for sub in ["docs/imported", "docs/generated"]:
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok = ok and exists
    status = 200 if ok else 503
    return JSONResponse({"status": "ok" if ok else "error", "details": details}, status_code=status)

# === Running locally with uvicorn ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))