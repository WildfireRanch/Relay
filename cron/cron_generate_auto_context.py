# File: cron_generate_auto_context.py
# Directory: cron
# Purpose: # Purpose: Automates the generation of context data at scheduled intervals using system cron jobs.
#
# Upstream:
#   - ENV: —
#   - Imports: datetime, subprocess, time
#
# Downstream:
#   - —
#
# Contents:
#   - run()









import time
import subprocess
from datetime import datetime

INTERVAL_SECONDS = 86400  # 12 hours

def run():
    while True:
        print(f"[CRON] Running generate_global_context.auto.py at {datetime.utcnow().isoformat()}Z")
        subprocess.run(["python", "scripts/generate_global_context.auto.py"])
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run()
