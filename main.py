# File: main.py

from dotenv import load_dotenv
load_dotenv()
import os

# ✅ Redacted API key confirmation for safety
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
from routes import ask, status, control, docs, oauth, debug  # ✅ Added debug

# === Ensure docs directory structure exists at startup ===
PROJECT_ROOT = Path(__file__).resolve().parent
for subdir in ["docs/imported", "docs/generated"]:
    (PROJECT_ROOT / subdir).mkdir(parents=True, exist_ok=True)

app = FastAPI()

# === CORS configuration for Relay frontend & public domain ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://wildfireranch.us",
        "https://relay.wildfireranch.us",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register all route groups ===
app.include_router(ask.router)
app.inclu
