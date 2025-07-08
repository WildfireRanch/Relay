# `oauth.py`

**Directory**: `routes`
**Purpose**: # Purpose: Handle OAuth authentication flow for the application, including initiating authentication and processing callbacks.

## Upstream
- ENV: OAUTH_REDIRECT_URI, POST_AUTH_REDIRECT_URI, GOOGLE_CREDS_JSON
- Imports: os, base64, pathlib, fastapi, fastapi.responses, google_auth_oauthlib.flow

## Downstream
- main

## Contents
- `oauth_callback()`
- `start_oauth()`