# File: test_admin_routes.py
# Directory: tests
# Purpose: # Purpose: Provides test cases for verifying the functionality and security of administrative routes within the application.
#
# Upstream:
#   - ENV: —
#   - Imports: json, routes, subprocess
#
# Downstream:
#   - —
#
# Contents:
#   - Dummy()
#   - fake_run()
#   - test_generate_auto_context_runs_correct_script()







import json
import subprocess
from routes import admin_routes


def test_generate_auto_context_runs_correct_script(monkeypatch):
    called = {}

    class Dummy:
        stdout = "ok"

    def fake_run(cmd, capture_output=True, text=True, check=True):
        called["cmd"] = cmd
        return Dummy()

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = admin_routes.generate_auto_context()
    assert called["cmd"] == ["python", "scripts/generate_global_context.auto.py"]
    assert json.loads(response.body) == {"status": "success", "output": "ok"}
