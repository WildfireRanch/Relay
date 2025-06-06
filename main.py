# File: main.py
# Purpose: Relay backend FastAPI app
# - Loads .env config
# - Applies full CORS policy
# - Mounts modular route groups (ask, status, control, docs, oauth, debug)
# - Handles frontend sync + Google OAuth redirect support
# - Deploys cleanly via Railway or runs locally with uvicorn

from dotenv import load_dotenv
load_dotenv()
import os

# ✅ Confirm OpenAI key presence
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print("✅ OPENAI API key loaded:", openai_key[:5] + "..." + openai_key[-4:])
else:
    print("❌ OPENAI API key is missing or empty!")

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# === Route modules ===
from routes import ask, status, control, docs, oauth, debug

# === Ensure required directories exist ===
PROJECT_ROOT = Path(__file__).resolve().parent
for subdir in ["docs/imported", "docs/generated"]:
    (PROJECT_ROOT / subdir).mkdir(parents=True, exist_ok=True)

app = FastAPI()

# === CORS configuration for Next.js frontend, local dev, and wildcard relay ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://wildfireranch.us",
        "https://relay.wildfireranch.us",
        "https://status.wildfireranch.us",  # ✅ Added for frontend sync button
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register route modules ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(docs.router)
app.include_router(oauth.router)
app.include_router(debug.router)

# === CORS preflight fallback ===
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return Response(status_code=200)

# === Health check ===
@app.get("/")
def root():
    """Sanity check for UptimeRobot, load balancers, and CLI tools."""
    return {"message": "Relay Agent is Online"}

# === Local dev launch point ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
