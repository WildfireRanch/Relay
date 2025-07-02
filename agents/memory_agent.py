# File: agents/memory_agent.py
# Purpose: Relay MemoryAgent — summarizes recent user sessions from local memory logs.
# Directory: agents/

import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from core.logging import log_event

SESSION_DIR = "./logs/sessions"

class MemoryAgent:
    def __init__(self, log_dir: str = SESSION_DIR):
        self.log_dir = Path(log_dir)

    def _load_entries(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Load recent memory entries for the user.
        """
        path = self.log_dir / f"{user_id}.jsonl"
        if not path.exists():
            return []

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            entries = [json.loads(line) for line in lines if line.strip()]
            return entries[-limit:]  # Most recent entries
        except Exception as e:
            log_event("memory_agent_load_error", {"error": str(e)})
            return []

    def _summarize_entries(self, entries: List[Dict]) -> str:
        """
        Convert log entries into a readable memory summary.
        """
        summary = []
        for entry in entries:
            query = entry.get("query", "")
            response = entry.get("summary", "")[:200].replace("\n", " ")
            timestamp = entry.get("timestamp", "")
            summary.append(f"- [{timestamp}] `{query}` → {response}...")
        return "\n".join(summary) if summary else "No memory entries found."

# === Shared instance ===
memory_agent = MemoryAgent()

# === Relay-compatible route handler ===
async def run(message: str, context: str, user_id: str = "anonymous") -> Dict:
    """
    Returns a summary of the most recent memory logs for the user.
    """
    try:
        entries = memory_agent._load_entries(user_id=user_id, limit=10)
        summary = memory_agent._summarize_entries(entries)

        log_event("memory_agent_summary", {
            "user": user_id,
            "entries": len(entries)
        })

        return {
            "user": user_id,
            "entry_count": len(entries),
            "summary": summary
        }

    except Exception as e:
        log_event("memory_agent_error", {"error": str(e)})
        return {"error": f"Failed to load memory: {str(e)}"}
