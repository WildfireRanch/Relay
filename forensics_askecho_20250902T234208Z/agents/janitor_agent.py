# File: janitor_agent.py
# Directory: agents
# Purpose: Manages the cleanup and maintenance of system resources and temporary files.
#
# Upstream:
#   - ENV: —
#   - Imports: json, os, pathlib, services.memory
#
# Downstream:
#   - agents.mcp_agent
#
# Contents:
#   - run()

# agents/janitor_agent.py

async def run(query: str, context: str, user_id: str = "system") -> dict:
    """
    Summarizes memory logs, detects duplicates, removes noise, and compresses the log footprint.
    """
    from services.memory import summarize_memory_entry
    import os, json
    from pathlib import Path

    path = Path(f"./logs/sessions/{user_id}.jsonl")
    if not path.exists():
        return {"status": "no memory log found"}

    lines = path.read_text().splitlines()
    entries = [json.loads(line) for line in lines[-100:] if line.strip()]
    
    seen = set()
    compressed = []

    for entry in entries:
        key = (entry["query"], entry["summary"][:50])
        if key not in seen:
            seen.add(key)
            compressed.append(entry)

    return {
        "status": "ok",
        "original_count": len(entries),
        "deduplicated": len(compressed),
        "example": compressed[-1] if compressed else {}
    }
