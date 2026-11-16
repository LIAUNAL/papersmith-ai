"""Stands in for paper_cli.py in the translation endpoint tests.

Reads STUB_PAPER_RESPONSE (a JSON file) and prints it, exits with
STUB_PAPER_EXIT, and appends the argv it received to STUB_PAPER_ARGV.
STUB_PAPER_SLEEP delays the answer (seconds) to exercise the deadline.
"""
import json
import os
import sys
import time

log = os.environ.get("STUB_PAPER_ARGV")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")
time.sleep(float(os.environ.get("STUB_PAPER_SLEEP", "0")))
with open(os.environ["STUB_PAPER_RESPONSE"], encoding="utf-8") as handle:
    print(handle.read().strip())
sys.exit(int(os.environ.get("STUB_PAPER_EXIT", "0")))
