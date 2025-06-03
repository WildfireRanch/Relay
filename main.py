from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# === Route modules ===
from routes import ask, status, control, docs

app = FastAPI()

# === Enable CORS so Vercel frontend can call this backend ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock this down to your Vercel domain if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register API route groups ===
app.include_router(ask.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(docs.router)  # ✅ Add /docs/list and /docs/view

# === Root heartbeat ===
@app.get("/")
def root():
    return {"message": "Relay Agent is Online"}

# === Entry point for local dev ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
