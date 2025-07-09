# ──────────────────────────────────────────────────────────────────────────────
# File: kb.py
# Directory: routes
# Purpose: Provides the backend functionality for knowledge base search and management, including API endpoints and data validation models.
# Upstream:
#   - ENV: —
#   - Imports: fastapi, os, pydantic, services, typing
#
# Downstream:
#   - main
#
# Contents:
#   - SearchQuery()
#   - get_summary()
#   - reindex_kb()
#   - require_api_key()
#   - search_kb()
#   - search_kb_get()

# ──────────────────────────────────────────────────────────────────────────────