# File: services/gmail.py
# Directory: services/
# Purpose: Gmail read/write utility using Google OAuth creds (Relay control/email ops)

import os
from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64
from pathlib import Path
from google.oauth2.service_account import Credentials

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly']
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")  # Path to service account JSON

def get_gmail_service():
    """Build a Gmail API client using service account credentials."""
    creds = Credentials.from_service_account_file(
        GOOGLE_CREDS_JSON,
        scopes=GMAIL_SCOPES,
    )
    delegated_email = os.getenv("NOTIFY_FROM_EMAIL")
    if delegated_email:
        creds = creds.with_subject(delegated_email)
    return build('gmail', 'v1', credentials=creds)

def send_email(to_email, subject, body):
    """Send an email via Gmail API."""
    service = get_gmail_service()
    message = MIMEText(body)
    message['to'] = to_email
    message['from'] = os.getenv("NOTIFY_FROM_EMAIL")
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={'raw': raw}).execute()

def list_emails(query="", max_results=10):
    """List email messages in the inbox (by search query)."""
    service = get_gmail_service()
    results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    messages = results.get('messages', [])
    emails = []
    for m in messages:
        msg = service.users().messages().get(userId='me', id=m['id'], format='metadata').execute()
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        snippet = msg.get('snippet', '')
        emails.append({
            "id": m['id'],
            "snippet": snippet,
            "from": headers.get("From"),
            "subject": headers.get("Subject"),
            "date": headers.get("Date"),
        })
    return emails

def get_email(email_id):
    """Fetch full content of a given email by ID."""
    service = get_gmail_service()
    msg = service.users().messages().get(userId='me', id=email_id, format='full').execute()
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    body = ""
    if 'parts' in msg['payload']:
        for part in msg['payload']['parts']:
            if part['mimeType'] == 'text/plain':
                body = base64.urlsafe_b64decode(part['body']['data']).decode()
    else:
        body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode()
    return {
        "id": email_id,
        "from": headers.get("From"),
        "subject": headers.get("Subject"),
        "date": headers.get("Date"),
        "body": body
    }
