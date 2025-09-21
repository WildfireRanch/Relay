# ──────────────────────────────────────────────────────────────────────────────
# File: services/summarizer.py
# Purpose: Concurrency-limited doc summarization helpers (async, anyio-based)
#
# Contract:
#   - summarize_doc(llm, doc) -> str | dict | Any (whatever llm.summarize returns)
#   - summarize_all(llm, docs: list) -> list of results (stable order)
#
# Notes:
#   - Limits concurrent summarize() calls to avoid hammering chat models.
#   - Uses anyio to safely run blocking llm.summarize in threads.
#   - Limit is configured by KB_SUMMARIZER_CONCURRENCY (default: 3).
#   - This module is standalone; import and use where needed.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from typing import Any, Iterable, List

import anyio

# Narrow concurrency by default; adjustable via env
_SUMMARIZER_LIMIT = int(os.getenv("KB_SUMMARIZER_CONCURRENCY", "3") or "3")
_SEM = anyio.Semaphore(_SUMMARIZER_LIMIT)


async def summarize_doc(llm: Any, doc: Any) -> Any:
    """
    Run a single llm.summarize(doc) call with a shared concurrency cap.

    llm.summarize is treated as a blocking function and offloaded to a thread.
    """
    async with _SEM:
        return await anyio.to_thread.run_sync(lambda: llm.summarize(doc))


async def summarize_all(llm: Any, docs: Iterable[Any]) -> List[Any]:
    """
    Summarize multiple docs concurrently with a shared limit. Preserves input order.
    """
    doc_list = list(docs)
    results: List[Any] = [None] * len(doc_list)

    async def _worker(i: int, d: Any) -> None:
        results[i] = await summarize_doc(llm, d)

    async with anyio.create_task_group() as tg:
        for i, d in enumerate(doc_list):
            tg.start_soon(_worker, i, d)

    return results

