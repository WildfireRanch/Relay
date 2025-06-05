from dotenv import load_dotenv
load_dotenv()
import os

# ✅ Redacted API key confirmation for safety
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print("✅ OPENAI API key loaded:", openai_key[:5] + "..." + openai_key[-4:])
else:
    print("❌ OPENAI API key is missing or empty!")

from pathlib import Path  # ✅ Needed for directory setup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# === Route modules ===
from routes import ask, status, control, docs  # 'docs' now handles sync, context, view, list

# === Ensure docs directory structure exists at startup ===
PROJECT_ROOT = Path(__file__).resolve().parent
for subdir in ["docs/imported", "docs/generated"]:
    (PROJECT_ROOT / subdir).mkdir(parents=True, exist_ok=True)

app = FastAPI()

# === Enable CORS for frontend and local dev ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://relay.wildfireranch.us",
        "http://localhost:3000",
        "https://yourproject.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register all route groups ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(docs.router)

# === Global OPTIONS route to handle all CORS preflight ===
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return Response(status_code=200)

# === Heartbeat endpoint ===
@app.get("/")
def root():
    """Sanity check for load balancers, UptimeRobot, etc."""
    return {"message": "Relay Agent is Online"}

# === Entry point for local dev ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
