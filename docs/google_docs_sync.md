# `google_docs_sync.py`

**Directory**: `services`
**Purpose**: # Purpose: Synchronize documents from Google Docs to local storage, handling authentication, retrieval, and conversion to markdown.

## Upstream
- ENV: GOOGLE_CREDS_JSON, GOOGLE_TOKEN_JSON, GOOGLE_TOKEN_JSON, ENV
- Imports: os, base64, pathlib, google.oauth2.credentials, google_auth_oauthlib.flow, google.auth.transport.requests, googleapiclient.discovery, markdownify

## Downstream
- routes.context
- routes.docs

## Contents
- `fetch_and_save_doc()`
- `find_folder_id()`
- `get_docs_in_folder()`
- `get_google_service()`
- `sync_google_docs()`