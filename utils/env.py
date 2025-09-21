# ──────────────────────────────────────────────────────────────────────────────
# File: utils/env.py   (NEW)
# Purpose: Safe env readers that ignore malformed values (e.g., "35=") and
#          provide stable defaults. Keep tiny and dependency-free.
# ──────────────────────────────────────────────────────────────────────────────
# File: utils/env.py
from __future__ import annotations
import os, re
from typing import List

_NUM_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*$")

def get_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if not v: return float(default)
    m = _NUM_RE.match(v)
    return float(m.group(1)) if m else float(default)

def get_list(name: str, default: List[str]) -> List[str]:
    v = os.getenv(name)
    if not v: return list(default)
    return [s.strip() for s in v.split(",") if s.strip()]
