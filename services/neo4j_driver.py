# File: services/neo4j_driver.py
# Purpose: Shared async Neo4j driver for query and ingestion

import os
from neo4j import AsyncGraphDatabase, AsyncDriver
from contextlib import asynccontextmanager
from core.logging import log_event

# === Config from ENV ===
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# === Initialize internal driver (hidden) ===
_driver: AsyncDriver = AsyncGraphDatabase.driver(
    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# ✅ Exported handle for direct import
neo4j_driver = _driver

# === Async context manager to open sessions ===
@asynccontextmanager
async def get_session():
    async with _driver.session(database="neo4j") as session:
        yield session

# === Execute a read-only query ===
async def execute_read(query: str, parameters: dict = {}) -> list[dict]:
    try:
        async with get_session() as session:
            result = await session.execute_read(lambda tx: tx.run(query, parameters))
            return [record.data() async for record in result]
    except Exception as e:
        log_event("neo4j_read_fail", {"error": str(e), "query": query})
        return []

# === Execute a write query ===
async def execute_write(query: str, parameters: dict = {}) -> None:
    try:
        async with get_session() as session:
            await session.execute_write(lambda tx: tx.run(query, parameters))
    except Exception as e:
        log_event("neo4j_write_fail", {"error": str(e), "query": query})
