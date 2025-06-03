# services/settings.py
import os
from dotenv import load_dotenv
from pathlib import Path

# === Load .env file automatically at app startup ===
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# === Centralized environment variables ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/callback")

# === Validation helper ===
def assert_env(var, hint=""):
    value = os.getenv(var)
    if not value:
        raise RuntimeError(f"Missing required env var: {var}. {hint}")
    return value

# Example usage:
# assert_env("OPENAI_API_KEY", "Set in .env or as system environment variable")