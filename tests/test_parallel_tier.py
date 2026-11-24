"""The parallel Python tier: `npm run test:py:par`.

Measured on this suite: `--dist loadfile` is safe (about 1.9x with 8 workers),
while `load` and `loadscope` race on the shared `implementations/` directory.
These tests pin the pieces that make the script runnable and keep it on the
safe distribution mode.
"""

import json
import unittest
from pathlib import Path

from papersmith.core import manifest

REPO = Path(__file__).resolve().parents[1]


def _environment_specs():
    """`env/environment.yml`'s dependencies (`name` + constraint), the source
    `scripts/setup_env.py` builds the environment from through its locks."""
    return [name + constraint for name, constraint, _ in
            manifest.conda_dependencies(REPO / "env" / "environment.yml")]


class ParallelTierTests(unittest.TestCase):
    def setUp(self):
        self.scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]

    def test_the_parallel_script_uses_the_safe_distribution_mode(self):
        script = self.scripts.get("test:py:par", "")
        self.assertIn("--dist loadfile", script)
        self.assertIn("-n ", script)

    def test_the_parallel_script_runs_the_interpreter_the_serial_tier_names(self):
        serial = self.scripts["test:py"]
        self.assertTrue(self.scripts["test:py:par"].startswith(serial))

    def test_the_provisioned_environment_carries_xdist(self):
        self.assertTrue(any(spec.startswith("pytest-xdist") for spec in _environment_specs()))

    def test_the_manifest_names_xdist(self):
        lines = (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(line.startswith("pytest-xdist") for line in lines))
