from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import ask, status, control

app = FastAPI()

# === Enable CORS so Vercel frontend can call this backend ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Optional: restrict to ["https://your-vercel-app.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],   # Accept GET, POST, OPTIONS, etc.
    allow_headers=["*"],   # Accept headers like X-API-Key
)

# === Include route files ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)

@app.get("/")
def root():
    return {"message": "Relay Agent is Online"}

# === Run only when executed directly (e.g. for local testing) ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
