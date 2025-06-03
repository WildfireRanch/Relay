# main.py (bulletproof version)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# === Route modules ===
from routes import ask, status, control, docs  # docs now handles sync, context, view, list

# === Ensure docs directory structure exists at startup ===
Path("/workspaces/codespaces-blank/docs/imported").mkdir(parents=True, exist_ok=True)
Path("/workspaces/codespaces-blank/docs/generated").mkdir(parents=True, exist_ok=True)

app = FastAPI()

# === Enable CORS for frontend (lock to production domain) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://relay.wildfireranch.us"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register API route groups ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(docs.router)

# === Root heartbeat ===
@app.get("/")
def root():
    return {"message": "Relay Agent is Online"}

# === Entry point for local dev ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
