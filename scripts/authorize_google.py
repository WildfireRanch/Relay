# scripts/authorize_google.py (manual fallback for any environment)
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# === Google OAuth config ===
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly"
]

CREDENTIALS_PATH = Path("frontend/sync/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")

# === Manual OAuth flow ===
flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
auth_url, _ = flow.authorization_url(prompt='consent')

print("Please go to this URL to authorize this application:")
print(auth_url)
print()

code = input("Paste the authorization code here: ")
flow.fetch_token(code=code)
creds = flow.credentials

# === Save the token ===
with open(TOKEN_PATH, "w") as token:
    token.write(creds.to_json())

print("✅ token.json saved successfully.")
