# File: agents/memory_agent.py
"""
MemoryAgent for Relay

Manages persistent memory using vector store + session logs.
Supports:
- Storing interaction data
- Retrieving context-relevant memories
- Summarization and cleanup via JanitorAgent
"""

from typing import List, Dict
import os

# Placeholder: swap in real vector DB client
class SimpleMemoryStore:
    def __init__(self):
        self.records = []

    def add(self, session_id: str, entry: Dict):
        entry["session_id"] = session_id
        self.records.append(entry)

    def query(self, session_id: str, top_k: int = 5) -> List[Dict]:
        # naive LRU return
        return [r for r in self.records if r["session_id"] == session_id][-top_k:]

# Agent class
class MemoryAgent:
    def __init__(self):
        # In-memory store; replace with Redis/Faiss/etc.
        self.store = SimpleMemoryStore()

    def add_memory(self, session_id: str, memory: Dict) -> None:
        """
        Adds a new memory entry for a session.
        """
        self.store.add(session_id, memory)

    def get_memory(self, session_id: str, top_k: int = 5) -> List[Dict]:
        """
        Retrieves last `top_k` memories for a session.
        """
        return self.store.query(session_id, top_k)

    def summarize_memory(self, session_id: str) -> Dict:
        """
        Returns a merged summary of memory entries for that session.
        Handy for context window pruning or continuity.
        """
        memories = self.get_memory(session_id, top_k=20)
        combined = " ".join(m.get("text", "") for m in memories)
        return {"session_id": session_id, "summary": combined[:1000]}

# Usage example
if __name__ == "__main__":
    ma = MemoryAgent()
    ma.add_memory("sess123", {"text": "User asked about X"})
    ma.add_memory("sess123", {"text": "Saw code diff applied"})
    print(ma.get_memory("sess123", top_k=2))
    print(ma.summarize_memory("sess123"))
