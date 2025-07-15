"""
File  : backend/solark_browser/poll_and_insert.py
Purpose: Read SolArk plant_flow.json and INSERT into solark.plant_flow.

Works in three modes
────────────────────
1. Railway cron / shell  → uses injected PG* variables  OR  DATABASE_URL.
2. Local dev            → loads .env automatically via python-dotenv.
3. Any CI/CD            → provide DATABASE_URL + PLANT_ID secrets.

Env required
────────────
• DATABASE_URL           (preferred) -or- PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
• PLANT_ID               e.g. 146453
"""

from __future__ import annotations
import json, os, sys, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

# ── 0. Optional .env loader (ignored in prod image) ─────────────────────
try:
    from dotenv import load_dotenv

    dotenv_file = Path(__file__).resolve().parent / ".env"
    if dotenv_file.exists():
        load_dotenv(dotenv_file)
except ModuleNotFoundError:
    pass

# ── 1. Validate environment ─────────────────────────────────────────────
if "PLANT_ID" not in os.environ:
    sys.exit("❌ Missing PLANT_ID env var")

# Option A: full DSN
DSN = os.environ.get("DATABASE_URL")

# Option B: parts
PG_VARS = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"]
have_parts = all(v in os.environ for v in PG_VARS)

if not DSN and not have_parts:
    vars_needed = "DATABASE_URL  or  " + " ".join(PG_VARS)
    sys.exit(f"❌ Missing Postgres connection vars: {vars_needed}")

PLANT_ID = int(os.environ["PLANT_ID"])

# ── 2. Build connect parameters (DSN wins) ──────────────────────────────
if DSN:
    connect_kwargs: dict[str, object] = {"dsn": DSN}
else:
    connect_kwargs = dict(
        host=os.environ["PGHOST"],
        port=int(os.environ["PGPORT"]),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        dbname=os.environ["PGDATABASE"],
    )

# ── 3. Load snapshot JSON ───────────────────────────────────────────────
SNAP_PATH = "plant_flow.json"
try:
    with open(SNAP_PATH, "r") as f:
        snap = json.load(f)
except FileNotFoundError:
    sys.exit(f"❌ {SNAP_PATH} not found – run fetch_plant_flow.js first.")
except Exception as e:
    sys.exit(f"❌ Could not parse {SNAP_PATH}: {e}")

# ── 4. Assemble row dict ────────────────────────────────────────────────
now_utc = datetime.now(timezone.utc)
row = {
    "plant_id":            PLANT_ID,
    "ts":                  now_utc,
    "pv_power":            snap.get("pvPower"),
    "batt_power":          snap.get("battPower"),
    "grid_power":          snap.get("gridOrMeterPower"),
    "load_power":          snap.get("loadOrEpsPower"),
    "gen_power":           snap.get("genPower"),
    "min_power":           snap.get("minPower"),
    "soc":                 snap.get("soc"),
    "pv_to":               snap.get("pvTo"),
    "to_load":             snap.get("toLoad"),
    "to_grid":             snap.get("toGrid"),
    "to_bat":              snap.get("toBat"),
    "bat_to":              snap.get("batTo"),
    "grid_to":             snap.get("gridTo"),
    "gen_to":              snap.get("genTo"),
    "min_to":              snap.get("minTo"),
    "exists_gen":          snap.get("existsGen"),
    "exists_min":          snap.get("existsMin"),
    "gen_on":              snap.get("genOn"),
    "micro_on":            snap.get("microOn"),
    "exists_meter":        snap.get("existsMeter"),
    "bms_comm_fault_flag": snap.get("bmsCommFaultFlag"),
    "pv":                  snap.get("pv"),
    "exist_think_power":   snap.get("existThinkPower"),
    "raw_json":            Json(snap),   # JSONB column
}

# ── 5. SQL (schema solark) ──────────────────────────────────────────────
SQL = """
INSERT INTO solark.plant_flow (
    plant_id, ts,
    pv_power, batt_power, grid_power, load_power,
    gen_power, min_power, soc,
    pv_to, to_load, to_grid, to_bat, bat_to, grid_to, gen_to, min_to,
    exists_gen, exists_min, gen_on, micro_on, exists_meter, bms_comm_fault_flag,
    pv, exist_think_power, raw_json
) VALUES (
    %(plant_id)s, %(ts)s,
    %(pv_power)s, %(batt_power)s, %(grid_power)s, %(load_power)s,
    %(gen_power)s, %(min_power)s, %(soc)s,
    %(pv_to)s, %(to_load)s, %(to_grid)s, %(to_bat)s, %(bat_to)s,
    %(grid_to)s, %(gen_to)s, %(min_to)s,
    %(exists_gen)s, %(exists_min)s, %(gen_on)s, %(micro_on)s,
    %(exists_meter)s, %(bms_comm_fault_flag)s,
    %(pv)s, %(exist_think_power)s, %(raw_json)s
);
"""

# ── 6. Execute insert ───────────────────────────────────────────────────
try:
    with psycopg2.connect(**connect_kwargs) as conn, conn.cursor() as cur:
        cur.execute(SQL, row)
        conn.commit()
        print(f"✅ Inserted snapshot @ {now_utc.isoformat()}")
except psycopg2.Error as err:
    sys.exit(f"❌ Postgres error: {err}")
