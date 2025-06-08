# Relay

Relay is a FastAPI backend used to sync Google Docs into Markdown files and serve them to the frontend. The project relies on Google OAuth to read documents from a Drive folder.

## Google Docs Sync

The sync service requires a Google OAuth client and (optionally) an existing token. Configuration is handled via environment variables:

- **`GOOGLE_CREDS_JSON`** – base64 encoded contents of your Google client secret JSON.
- **`GOOGLE_TOKEN_JSON`** – base64 encoded OAuth token JSON from a prior login (optional).
- **`ENV`** – set to `local` when running interactively so OAuth can open a browser.

### OAuth Flow

1. Start authentication by visiting `/google/auth` in your running instance.
2. After granting access Google redirects to `/google/callback` which stores `frontend/sync/token.json` for future requests.

### Manual Authorization

If the web flow is unavailable, run:

```bash
python scripts/authorize_google.py
```

The script prints a URL, prompts for the returned code and then writes the token to `frontend/sync/token.json`.

## Example Environment File

Create a `.env` file (or export these variables directly) following the pattern below:

```dotenv
GOOGLE_CREDS_JSON=
GOOGLE_TOKEN_JSON=
ENV=local
```
