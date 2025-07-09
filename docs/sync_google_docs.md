# `sync_google_docs.py`

**Directory**: `frontend/sync`
**Purpose**: # Purpose: Synchronize documents from Google Docs to local storage, handling authentication and document retrieval.

## Upstream
- ENV: GOOGLE_TOKEN_JSON, ENV, GOOGLE_CREDS_JSON
- Imports: os, json, base64, pathlib, google.oauth2.credentials, google_auth_oauthlib.flow, googleapiclient.discovery, googleapiclient.errors, markdownify, google.auth.transport.requests

## Downstream
- —

## Contents
- `fetch_and_save_doc()`
- `find_folder_id()`
- `get_docs_in_folder()`
- `get_google_service()`
- `sync_google_docs()`