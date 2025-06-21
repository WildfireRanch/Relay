# File: cron/cron_generate_auto_context.py
# Purpose: Scheduled job to generate global_context.auto.md daily

import time
import subprocess
from datetime import datetime

INTERVAL_SECONDS = 86400  # 12 hours

def run():
    while True:
        print(f"[CRON] Running generate_global_context_auto.py at {datetime.utcnow().isoformat()}Z")
        subprocess.run(["python", "scripts/generate_global_context_auto.py"])
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run()
