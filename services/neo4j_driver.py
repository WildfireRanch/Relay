# File: services/neo4j_driver.py
# Purpose: Shared async Neo4j driver for Relay agent memory graph
# Notes:
#   - Supports async read/write using Neo4j Aura
#   - Uses single internal driver instance (AsyncGraphDatabase)
#   - Logs errors and can be safely imported from anywhere in the app

import os
from neo4j import AsyncGraphDatabase, AsyncDriver
from contextlib import asynccontextmanager
from core.logging import log_event

# === Load Neo4j credentials from environment ===
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# === Initialize Neo4j driver (singleton) ===
# Aura users: DO NOT include `database="neo4j"` in session()
_driver: AsyncDriver = AsyncGraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# Optional export if needed elsewhere
neo4j_driver = _driver

# === Async context manager for clean session usage ===
@asynccontextmanager
async def get_session():
    async with _driver.session() as session:
        yield session

# === Execute a read query and return results ===
async def execute_read(query: str, parameters: dict = {}) -> list[dict]:
    try:
        async with get_session() as session:
            result = await session.execute_read(lambda tx: tx.run(query, parameters))
            return [record.data() async for record in result]
    except Exception as e:
        print("❌ Neo4j read error:", e)
        log_event("neo4j_read_fail", {"error": str(e), "query": query})
        return []

# === Execute a write query with debug logging ===
async def execute_write(query: str, parameters: dict = {}) -> None:
    try:
        print("🚀 Neo4j write executing...")
        print("🧾 Cypher:", query[:120] + "..." if len(query) > 120 else query)
        print("📦 Params:", parameters)
        async with get_session() as session:
            await session.execute_write(lambda tx: tx.run(query, parameters))
    except Exception as e:
        print("❌ Neo4j write error:", e)
        log_event("neo4j_write_fail", {"error": str(e), "query": query})
