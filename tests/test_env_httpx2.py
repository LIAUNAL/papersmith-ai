"""The dashboard's test client dependency is `httpx2`, locked on every platform (issue #58).

starlette 1.x's `testclient` imports `httpx2` first (`import httpx2 as httpx`) and
falls back to the deprecated `httpx`; `smith ui --export-snapshot` and
`--publish-pages` need it. `env/environment.yml` names `httpx2`, and every lock
must carry it for each platform it covers, so a solve that dropped it fails here.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / "env"


class Httpx2LockTests(unittest.TestCase):
    def test_every_lock_carries_httpx2_for_each_of_its_platforms(self) -> None:
        record = json.loads((ENV / "locks.json").read_text(encoding="utf-8"))
        for variant, entry in record["variants"].items():
            text = (ENV / entry["lockfile"]).read_text(encoding="utf-8")
            entries = text.count("\n- name: httpx2\n")
            with self.subTest(variant=variant):
                self.assertEqual(entries, len(entry["platforms"]), entry["platforms"])
        self.assertIn("httpx2>=2.0", (ENV / "environment.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
