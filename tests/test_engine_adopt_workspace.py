"""`adopt`'s survey reaches its workspace check without a `NameError` (#52).

`_adopt_workspace_target` read a `WORKSPACE` the engine never imported, so
every survey crashed before it copied anything, and the crash recorder then
treated an operator's first `adopt` as a forge defect. The workspace rule
now lives once, in `impl_guards`, which reads it from `impl_layout`.

Runs `impl.main` in-process against a temporary workspace
(`impl_guards.WORKSPACE` patched), never the checkout's `implementations/`.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)
import impl_guards  # noqa: E402


class AdoptSurveyWorkspaceTests(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="adopt-workspace-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.workspace = self.root / "implementations"
        self.workspace.mkdir()
        patcher = unittest.mock.patch.object(impl_guards, "WORKSPACE", self.workspace)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = self.root / "prior-work"
        (self.source / "src").mkdir(parents=True)
        (self.source / "src" / "model.py").write_text("VALUE = 1\n", encoding="utf-8")

    def main(self, argv: list[str]) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = impl.main(argv)
        return code, json.loads(buf.getvalue())

    def test_adopt_valid_source_reaches_workspace_target(self):
        target = self.workspace / "Demo"
        code, payload = self.main(["adopt", "--target", str(target), "--name", "Demo",
                                   "--source", str(self.source)])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "surveyed")
        self.assertEqual(payload["target"], str(target))
        plan = json.loads(Path(payload["plan"]).read_text(encoding="utf-8"))
        self.assertEqual((plan["command"], plan["mode"], plan["name"]),
                         ("adopt", "survey", "Demo"))
        self.assertEqual((target / "src" / "model.py").read_text(encoding="utf-8"),
                         "VALUE = 1\n")
        head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(payload["commit"], head)
        self.assertEqual(sorted(p.name for p in self.source.rglob("*")), ["model.py", "src"])

    def test_adopt_outside_the_workspace_still_refuses(self):
        target = self.root / "elsewhere" / "Demo"
        code, payload = self.main(["adopt", "--target", str(target), "--name", "Demo",
                                   "--source", str(self.source)])
        self.assertEqual((code, payload["code"]), (2, "OUTSIDE_WORKSPACE"))
        self.assertIn(str(self.workspace), payload["detail"])
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
