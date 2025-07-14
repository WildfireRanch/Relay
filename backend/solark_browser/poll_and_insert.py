"""
File: backend/solark_browser/poll_and_insert.py
Purpose: Load SolArk plant snapshot from plant_flow.json and insert it
         into Postgres table  solark.plant_flow.
         Must be run after `node fetch_plant_flow.js`.

Environment (Railway or local):
  PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE, PLANT_ID
"""

from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json

# ---------------------------------------------------------------------
# 1.  Verify required ENV vars (fail fast if any are missing)
# ---------------------------------------------------------------------
NEEDED = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PLANT_ID"]
missing = [k for k in NEEDED if k not in os.environ]
if missing:
    sys.exit(f"❌ Missing ENV vars: {', '.join(missing)}")

PGHOST      = os.environ["PGHOST"]
PGPORT      = int(os.environ["PGPORT"])
PGUSER      = os.environ["PGUSER"]
PGPASSWORD  = os.environ["PGPASSWORD"]
PGDATABASE  = os.environ["PGDATABASE"]
PLANT_ID    = int(os.environ["PLANT_ID"])

# ---------------------------------------------------------------------
# 2.  Load snapshot JSON written by fetch_plant_flow.js
# ---------------------------------------------------------------------
SNAP_PATH = "plant_flow.json"
try:
    with open(SNAP_PATH, "r") as f:
        snap = json.load(f)
except FileNotFoundError:
    sys.exit(f"❌ {SNAP_PATH} not found – run fetch_plant_flow.js first.")
except Exception as e:
    sys.exit(f"❌ Could not parse {SNAP_PATH}: {e}")

# ---------------------------------------------------------------------
# 3.  Build row dict (UTC timestamp)
# ---------------------------------------------------------------------
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
    "raw_json":            Json(snap),        # store whole payload for audit
}

# ---------------------------------------------------------------------
# 4.  Insert into Postgres (schema: solark, table: plant_flow)
# ---------------------------------------------------------------------
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

try:
    with psycopg2.connect(
        host=PGHOST, port=PGPORT,
        dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD
    ) as conn, conn.cursor() as cur:
        cur.execute(SQL, row)
        conn.commit()
        print(f"✅ Inserted snapshot @ {now_utc.isoformat()}")
except psycopg2.Error as db_err:
    sys.exit(f"❌ Postgres error: {db_err}")
