# main.py (bulletproof version)
from dotenv import load_dotenv
load_dotenv()
import os
print("OPENAI KEY IN USE:", os.getenv("OPENAI_API_KEY"))

from pathlib import Path  # ✅ Needed for directory setup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# === Route modules ===
from routes import ask, status, control, docs  # 'docs' now handles sync, context, view, list

# === Ensure docs directory structure exists at startup ===
PROJECT_ROOT = Path(__file__).resolve().parent
for subdir in ["docs/imported", "docs/generated"]:
    (PROJECT_ROOT / subdir).mkdir(parents=True, exist_ok=True)

app = FastAPI()

# === Enable CORS for frontend (locked to production domain) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://relay.wildfireranch.us"],  # Change this if you have more trusted origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register all route groups ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(docs.router)

# === Heartbeat endpoint ===
@app.get("/")
def root():
    """Sanity check for load balancers, UptimeRobot, etc."""
    return {"message": "Relay Agent is Online"}

# === Entry point for local dev ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
