# `gmail.py`

**Directory**: `services`
**Purpose**: # Purpose: Provides utility functions for interacting with the Gmail API, including sending emails and managing email listings.

## Upstream
- ENV: GOOGLE_CREDS_JSON, NOTIFY_FROM_EMAIL, NOTIFY_FROM_EMAIL
- Imports: os, googleapiclient.discovery, email.mime.text, base64, pathlib, google.oauth2.service_account

## Downstream
- —

## Contents
- `get_email()`
- `get_gmail_service()`
- `list_emails()`
- `send_email()`