# ─────────────────────────────────────────────────────────────────────────────
# File: memory.py
# Directory: services
# Purpose: # Purpose: Manage and log memory-related data entries for debugging and tracking purposes.
#
# Upstream:
#   - ENV: —
#   - Imports: datetime, json, os
#
# Downstream:
#   - agents.janitor_agent
#
# Contents:
#   - debug_log_entry()
#   - save_memory_entry()
#   - summarize_memory_entry()
# ─────────────────────────────────────────────────────────────────────────────

import os
import json
import datetime

SESSION_DIR = "./logs/sessions"

def summarize_memory_entry(
    prompt: str,
    response: str,
    context: str = "",
    actions: list = None,
    user_id: str = "anonymous",
    topics: list = None,
    files: list = None,
    context_files: list = None,
    used_global_context: bool = False,
    fallback: bool = False,
    prompt_length: int = None,
    response_length: int = None
):
    """
    Build a detailed memory entry for each session event.
    Includes advanced context diagnostics for frontend insight.
    """
    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": user_id,
        "query": prompt,
        "topics": topics or [],
        "files": files or [],
        "context_files": context_files or [],
        "context_length": len(context or ""),
        "prompt_length": prompt_length or (len(prompt) + len(context or "")),
        "response_length": response_length or len(response or ""),
        "used_global_context": used_global_context,
        "fallback": fallback,
        "actions": actions or [],
        "summary": response  # Optionally replace with GPT summary if you want
    }

def save_memory_entry(user_id: str, summary: dict):
    """
    Write a single memory entry to the per-user log file as JSONL.
    """
    os.makedirs(SESSION_DIR, exist_ok=True)
    path = os.path.join(SESSION_DIR, f"{user_id}.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(summary) + "\n")

# === Utility: For debugging/logging what gets stored ===
def debug_log_entry(entry: dict):
    print("[Memory] Log Entry Debug:")
    print(json.dumps(entry, indent=2)[:1200], "...\n")  # Print first 1200 chars
