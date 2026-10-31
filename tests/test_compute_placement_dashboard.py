"""The dashboard's run options per candidate (compute-placement S6).

A schema 2 timing record gives the Experimentos tab one row per candidate,
measured or not: each measured candidate with its device, processes, fastest
measured settings and serial estimate, and every candidate the record or the
recorded plan names as unmeasured. The host-family rows keep their shape and
read each family's fastest candidate instead of pooling a CPU with an
accelerator. The pick shown is the latest recorded `plan`'s recommendation,
with its reason; with no plan recorded the tab says how to record one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view, remote_services, run_options
from tests.test_command_center_run_options import SCRIPT_PATH, _local, _services

REMOTE_A, REMOTE_B = remote_services.RUN_HOSTS[1], remote_services.RUN_HOSTS[2]


def _m(candidate: str, seconds: float, device: str = "cpu", **extra) -> dict:
    host = "local" if candidate.startswith("local-") else candidate.split("/", 1)[0]
    item = {"measuredAt": "2026-10-29T10:00:00Z", "host": host, "candidate": candidate, "device": device,
            "arm": "A", "unit": "epoch", "secondsPerUnit": seconds, "unitsMeasured": 1}
    item.update(extra)
    return item


TIMING2 = {
    "schema": 2,
    "hosts": {"local": {"cpuCount": 8, "ramGB": 16.0, "mps": True, "cuda": False}},
    "measurements": [
        _m("local-cpu-1", 69.5, threads=8),
        _m("local-cpu-8", 12.0, processes=8, threads=1, batchSize=64, loadSeconds=2.0, computeSeconds=10.0),
        _m("local-cpu-8", 30.0, processes=8, threads=1, batchSize=16),
        _m(f"{REMOTE_A}:ana/T4", 8.0, device="cuda:Tesla T4", setupSeconds=420.0),
    ],
    "scales": {"poc": {"arms": 2, "folds": 4, "seeds": 2, "epochs": 2},
               "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 30}},
}

PLAN = {"plans": {"poc": {
    "recommended": {"option": "local-cpu-8", "kind": "local", "device": "cpu", "settings": {"batchSize": 64},
                    "processes": 8, "accounts": [], "makespanSeconds": {"seconds": 53, "low": 42.4, "high": 63.6},
                    "reason": "local-cpu-8 has the smallest measured makespan upper bound (63.6 s)"},
    "options": [{"option": f"{REMOTE_A}:ana/T4", "status": "eligible", "device": "cuda:Tesla T4"}],
    "lost": [{"option": f"{REMOTE_A}:ana/T4", "status": "eligible",
              "reason": "slower: makespan upper bound 811.2 s against local-cpu-8's 63.6 s"}],
    "unmeasured": [{"candidate": f"{REMOTE_A}:ana/cpu", "measureWith": "a rehearsal ... --accelerator-kind cpu"}],
}}, "recordedOn": "2026-10-29"}


def _view(timing: dict | None = TIMING2, plan: dict | None = None) -> dict:
    parsed = run_options.parse_timing(timing) if timing is not None else None
    if parsed:
        parsed["file"] = "implementations/repo/Poc/Results/timing.json"
    product = {"repo": "repo", "name": "Poc", "kind": "poc", "timing": parsed}
    if plan is not None:
        product["placement_plan"] = dict(run_options.parse_plan(plan),
                                         file="implementations/repo/Poc/.remote-parallelism/plan-2026-10-29.json")
    return {"products": [product], "local_environment": _local(), "remote_services": _services()}


class CandidateRowTests(unittest.TestCase):
    def test_schema_2_is_read_and_each_family_reads_its_fastest_candidate(self) -> None:
        options = run_options.run_options(Path("."), _view())
        local = next(r for r in options["rows"] if r["stage"] == "poc" and r["host"] == "local")
        # local-cpu-8 at its fastest setting: 12 s x 2 epochs x 4 folds x 2 seeds x 2 arms.
        self.assertEqual(local["estimate"]["seconds"], 384.0)
        self.assertEqual(local["estimate"]["candidate"], "local-cpu-8")

    def test_one_row_per_candidate_measured_or_not(self) -> None:
        options = run_options.run_options(Path("."), _view())
        poc = {r["candidate"]: r for r in options["candidates"] if r["stage"] == "poc"}
        self.assertEqual(poc["local-cpu-8"]["status"], "measured")
        self.assertEqual(poc["local-cpu-8"]["device"], "cpu")
        self.assertEqual(poc["local-cpu-8"]["processes"], 8)
        self.assertEqual(poc["local-cpu-8"]["settings"], {"threads": 1, "batchSize": 64})
        self.assertEqual(poc["local-cpu-8"]["load_share"], 0.17)
        self.assertEqual(poc[f"{REMOTE_A}:ana/T4"]["kind"], "accelerator")
        self.assertEqual(poc["local-mps"]["status"], "unmeasured")
        self.assertEqual(poc[REMOTE_B]["status"], "unmeasured")
        self.assertIsNone(poc[REMOTE_B]["estimate"])
        self.assertIsNone(options["plan_picks"]["poc"])
        self.assertIn("plan", options["plan_hint"])

    def test_the_recorded_plan_s_pick_and_its_unmeasured_candidates_are_shown(self) -> None:
        options = run_options.run_options(Path("."), _view(plan=PLAN))
        pick = options["plan_picks"]["poc"]
        self.assertEqual((pick["option"], pick["device"]), ("local-cpu-8", "cpu"))
        self.assertIn("smallest measured makespan", pick["reason"])
        self.assertIn("42 s – 64 s", pick["label"])
        poc = {r["candidate"]: r for r in options["candidates"] if r["stage"] == "poc"}
        self.assertEqual(poc[f"{REMOTE_A}:ana/cpu"]["status"], "unmeasured")
        self.assertIn("--accelerator-kind cpu", poc[f"{REMOTE_A}:ana/cpu"]["reason"])
        self.assertEqual(poc["local-cpu-8"]["plan"], "recommended")
        self.assertIn("slower", poc[f"{REMOTE_A}:ana/T4"]["plan"])
        self.assertIsNone(options["plan_picks"]["full"])

    def test_a_schema_1_record_keeps_its_rows_and_lists_hosts_as_candidates(self) -> None:
        from tests.test_command_center_run_options import TIMING
        options = run_options.run_options(Path("."), _view(timing=TIMING))
        local = next(r for r in options["rows"] if r["stage"] == "poc" and r["host"] == "local")
        self.assertEqual(local["estimate"]["seconds"], 570.0)
        self.assertNotIn("candidate", local["estimate"])
        poc = {r["candidate"] for r in options["candidates"] if r["stage"] == "poc"}
        self.assertIn("local", poc)


class ViewWiringTests(unittest.TestCase):
    def test_the_view_reads_schema_2_and_the_latest_recorded_plan(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        poc = root / "implementations" / "repo" / "Poc"
        (poc / "Results").mkdir(parents=True)
        (poc / ".remote-parallelism").mkdir()
        (poc / "AGREED.md").write_text("ok\n", encoding="utf-8")
        (poc / "Results" / "timing.json").write_text(json.dumps(TIMING2), encoding="utf-8")
        older = json.loads(json.dumps(PLAN))
        older["plans"]["poc"]["recommended"]["option"] = "local-cpu-1"
        (poc / ".remote-parallelism" / "plan-2026-10-29.json").write_text(json.dumps(older), encoding="utf-8")
        (poc / ".remote-parallelism" / "plan-2026-10-29-2.json").write_text(json.dumps(PLAN), encoding="utf-8")
        view = experiments_view.get_experiments_view(root)
        product = view["products"][0]
        self.assertEqual(product["timing"]["schema"], 2)
        self.assertEqual(product["placement_plan"]["file"],
                         "implementations/repo/Poc/.remote-parallelism/plan-2026-10-29-2.json")
        self.assertEqual(view["run_options"]["plan_picks"]["poc"]["option"], "local-cpu-8")


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class RenderTests(unittest.TestCase):
    def render(self, view: dict) -> str:
        # Labels come from the i18n catalogues, so load them and ask for Spanish
        # the way the sibling run-options render test does.
        i18n_js = SCRIPT_PATH.parent / "i18n.js"
        en_js = SCRIPT_PATH.parent / "i18n" / "en.js"
        es_js = SCRIPT_PATH.parent / "i18n" / "es.js"
        script = (
            "const fs=require('fs');"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[]};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_the_candidates_and_the_plan_pick_render_and_escape(self) -> None:
        view = _view(plan=PLAN)
        view["run_options"] = run_options.run_options(Path("."), view)
        view["run_options"]["plan_picks"]["poc"]["reason"] = "<script>alert(3)</script>"
        out = self.render(view)
        self.assertIn("Candidatos", out)
        self.assertIn("local-cpu-8", out)
        self.assertIn("Plan:", out)
        self.assertIn("recomendado", out)
        self.assertIn("sin medir", out)
        self.assertNotIn("<script>alert(3)", out)
        view = _view()
        view["run_options"] = run_options.run_options(Path("."), view)
        out = self.render(view)
        # The badge is catalogue text; the hint is the server's own (English
        # here, localized by localize.py only when the request asks for Spanish).
        self.assertIn("sin plan", out)
        self.assertIn(view["run_options"]["plan_hint"].replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;"), out)


if __name__ == "__main__":
    unittest.main()
