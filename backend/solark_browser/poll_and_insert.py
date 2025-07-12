# File: backend/solark_browser/poll_and_insert.py
# Purpose: Robustly load SolArk plant-level snapshot from plant_flow.json and insert ALL fields into Railway Postgres
# Usage: Run after `node fetch_plant_flow.js` (which creates plant_flow.json)
# Table: solark_plant_metrics (one column per metric, plus raw_json for future-proofing)

import json
from datetime import datetime, timezone
import psycopg2
import sys
import os

# === CONFIG: Use public connection from Railway "Connect" tab ===
PGHOST = os.getenv("PGHOST", "trolley.proxy.rlwy.net")
PGPORT = int(os.getenv("PGPORT", "31385"))
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "ZURcdqOrTWwRDAAkGgAaKKKFxWtZiiVm")
PGDATABASE = os.getenv("PGDATABASE", "railway")


# === 1. Verify plant_flow.json exists and is readable ===
JSON_PATH = 'plant_flow.json'
if not os.path.isfile(JSON_PATH):
    print(f"❌ File not found: {JSON_PATH}")
    sys.exit(1)

try:
    with open(JSON_PATH, 'r') as f:
        snap = json.load(f)
except Exception as e:
    print(f"❌ Failed to read or parse {JSON_PATH}: {e}")
    sys.exit(1)

# === 2. Compose the DB row, use a UTC timestamp ===
ts = datetime.now(timezone.utc)

row = {
    'ts': ts,
    'inverter_id': 'plant',
    'pv_power': snap.get('pvPower'),
    'batt_power': snap.get('battPower'),
    'grid_power': snap.get('gridOrMeterPower'),
    'load_power': snap.get('loadOrEpsPower'),
    'gen_power': snap.get('genPower'),
    'min_power': snap.get('minPower'),
    'soc': snap.get('soc'),
    'pv_to': snap.get('pvTo'),
    'to_load': snap.get('toLoad'),
    'to_grid': snap.get('toGrid'),
    'to_bat': snap.get('toBat'),
    'bat_to': snap.get('batTo'),
    'grid_to': snap.get('gridTo'),
    'gen_to': snap.get('genTo'),
    'min_to': snap.get('minTo'),
    'exists_gen': snap.get('existsGen'),
    'exists_min': snap.get('existsMin'),
    'gen_on': snap.get('genOn'),
    'micro_on': snap.get('microOn'),
    'exists_meter': snap.get('existsMeter'),
    'bms_comm_fault_flag': snap.get('bmsCommFaultFlag'),
    'pv': snap.get('pv'),
    'exist_think_power': snap.get('existThinkPower'),
    'raw_json': json.dumps(snap)
}

# === 3. Insert into Railway Postgres, handle all exceptions ===
try:
    conn = psycopg2.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD
    )
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO solark_plant_metrics (
        ts, inverter_id, pv_power, batt_power, grid_power, load_power,
        gen_power, min_power, soc,
        pv_to, to_load, to_grid, to_bat, bat_to, grid_to, gen_to, min_to,
        exists_gen, exists_min, gen_on, micro_on, exists_meter, bms_comm_fault_flag,
        pv, exist_think_power, raw_json
    ) VALUES (
        %(ts)s, %(inverter_id)s, %(pv_power)s, %(batt_power)s, %(grid_power)s, %(load_power)s,
        %(gen_power)s, %(min_power)s, %(soc)s,
        %(pv_to)s, %(to_load)s, %(to_grid)s, %(to_bat)s, %(bat_to)s, %(grid_to)s, %(gen_to)s, %(min_to)s,
        %(exists_gen)s, %(exists_min)s, %(gen_on)s, %(micro_on)s, %(exists_meter)s, %(bms_comm_fault_flag)s,
        %(pv)s, %(exist_think_power)s, %(raw_json)s
    )
    """, row)
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Inserted plant_flow snapshot at {ts.isoformat()} :")
    print(json.dumps(row, indent=2, default=str))
except psycopg2.OperationalError as oe:
    print(f"❌ Database connection failed: {oe}")
    sys.exit(2)
except Exception as e:
    print(f"❌ Insert failed: {e}")
    sys.exit(3)
