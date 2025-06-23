# File: services/memory.py
# Purpose: Format and persist summarized memory entries for /ask endpoint

import os
import json
import datetime

SESSION_DIR = "./logs/sessions"

def summarize_memory_entry(prompt, response, context=None, actions=None, user_id="anonymous"):
    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "user": user_id,
        "prompt": prompt,
        "response": response,
        "context_length": len(context) if context else 0,
        "actions": actions or []
    }

def save_memory_entry(user_id: str, summary: dict):
    os.makedirs(SESSION_DIR, exist_ok=True)
    path = os.path.join(SESSION_DIR, f"{user_id}.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(summary) + "\n")
