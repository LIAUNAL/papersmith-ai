"""Stands in for journal_cli.py in the endpoint tests.

Reads STUB_JOURNAL_RESPONSE (a JSON file) and prints it, exits with
STUB_JOURNAL_EXIT, and appends the argv it received to STUB_JOURNAL_ARGV.
STUB_JOURNAL_SLEEP delays the answer (seconds) to exercise the deadline.
"""
import json
import os
import sys
import time

log = os.environ.get("STUB_JOURNAL_ARGV")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")
time.sleep(float(os.environ.get("STUB_JOURNAL_SLEEP", "0")))
with open(os.environ["STUB_JOURNAL_RESPONSE"], encoding="utf-8") as handle:
    print(handle.read().strip())
sys.exit(int(os.environ.get("STUB_JOURNAL_EXIT", "0")))
