Relay Command Center – Version 1
Overview
Relay Command Center is a modular, full-stack AI-enabled backend and frontend platform designed to control, synchronize, and observe your solar-powered infrastructure, miner operations, and external documents via GPT-based interactions and automation.
This document summarizes Version 1 (V1) of the system, covering all features implemented across the project folder, including backend API, frontend controls, OAuth integration, and document synchronization logic.
✅ Backend (FastAPI)
Core API Endpoints
GET / – Health check endpoint
POST /ask – GPT-4-powered agent Q&A endpoint (Relay Agent)
POST /control/queue\_action – Allows the agent to propose and queue actions
GET /status/summary – Provides system health/status insights
POST /docs/sync\_google – Syncs Google Docs from COMMAND\_CENTER folder and converts them to Markdown
GET /docs/list – Lists all imported Markdown files
GET /docs/view?path=... – Returns contents of a specific document
GET /debug/env – Diagnostic endpoint to verify environment variable loading (like GOOGLE\_CREDS\_JSON)
OAuth Flow
GET /google/auth – Launches Google OAuth using credentials in GOOGLE\_CREDS\_JSON
GET /google/callback – Finalizes OAuth and writes token.json to frontend/sync/token.json
Infrastructure
Auto-creates required folders (docs/imported, docs/generated)
Modular routing structure with ask, status, control, docs, oauth, debug
CORS-enabled for frontend origins:
https://relay.wildfireranch.us
https://status.wildfireranch.us
http://localhost:3000
✅ Google Docs Sync
Environment Variables
GOOGLE\_CREDS\_JSON – base64-encoded client\_secret.json
GOOGLE\_TOKEN\_JSON – base64-encoded token.json after successful auth (optional, used for persistent access)
Sync Logic
Uses google-auth, googleapiclient, and markdownify
Pulls files from folder: COMMAND\_CENTER in Google Drive
Converts content to Markdown
Saves as .md files in docs/imported
Token-based auth is triggered automatically unless token.json is missing or invalid (then triggers browser flow)
✅ Frontend (Next.js + React)
Docs Viewer UI
Displays document list and contents
Two-panel layout: sidebar (doc list) and content viewer
Scrollable and responsive
Sync Button
🔄 Sync Google Docs button in the UI
Triggers POST to /docs/sync\_google
Refreshes doc list after completion
Handles sync status and error feedback inline
🧠 Intelligence
GPT-backed agent available via /ask
Supports knowledge base lookups across synced Markdown docs
Preloaded with GOOGLE\_CREDS\_JSON and OPENAI\_API\_KEY
Smart routing, debug logging, and error feedback
🧪 Developer Support
.env-ready variable structure (with base64-encoded credentials)
.env.local used for frontend local overrides (e.g. NEXT\_PUBLIC\_RELAY\_KEY)
Supports local testing and live Railway/Vercel deployment
🚀 Deployment Targets
Backend (FastAPI): Railway – https://relay.wildfireranch.us
Frontend (Next.js): Vercel – https://status.wildfireranch.us
🏁 Version 1 Milestone Complete
Next steps (future versions): frontend action queue, miner controls, agent decision visualizer, and token bootstrap tool.
Version: Relay Command Center V1Date: 2025-06-06Lead: Bret WestwoodBuilt with Echo 💬