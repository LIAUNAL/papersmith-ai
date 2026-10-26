"""Run options per stage and host: availability, the one estimate formula, advice.

``run_options.run_options(root, view)`` reads what ``get_experiments_view``
already gathered — each product's ``Results/timing.json``, the local
environment and the remote-services rows — and answers one row per stage
(``poc``, ``full``) and host family (local and the two remote services), with
an estimate from that host's own measurements only, stated as a ±20% range.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import experiments_view, remote_services, run_options, server

SCRIPT_PATH = Path(server.__file__).resolve().parent / "static" / "experiments-panel.js"
REMOTE_A, REMOTE_B = remote_services.RUN_HOSTS[1], remote_services.RUN_HOSTS[2]

TIMING = {
    "schema": 1,
    "measurements": [
        {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu", "arm": "A",
         "unit": "epoch", "secondsPerUnit": 2.0, "unitsMeasured": 1, "setupSeconds": 5.0},
        {"measuredAt": "2026-10-25T10:01:00Z", "host": "local", "device": "cpu", "arm": "A",
         "unit": "epoch", "secondsPerUnit": 4.0, "unitsMeasured": 1},
        {"measuredAt": "2026-10-25T10:02:00Z", "host": "local", "device": "cpu", "arm": "B",
         "unit": "epoch", "secondsPerUnit": 6.0, "unitsMeasured": 1},
        {"measuredAt": "2026-10-25T11:00:00Z", "host": f"{REMOTE_A}:alice", "device": "cuda:gpu",
         "arm": "A", "unit": "epoch", "secondsPerUnit": 1.0, "unitsMeasured": 2, "setupSeconds": 60.0},
    ],
    "scales": {"poc": {"arms": 2, "folds": 3, "seeds": 2, "epochs": 10},
               "full": {"arms": 2, "folds": 5, "seeds": 5, "epochs": 100}},
}


def _services(*, token: str = "active", cli: str = "active", accounts: int = 1,
              colab_cli: str = "active", members: list[dict] | None = None) -> dict:
    rows = [{"id": "token", "state": token}, {"id": "cli", "state": cli},
            {"id": "accounts", "state": "active" if accounts else "inactive", "count": accounts},
            {"id": "colab_cli", "state": colab_cli}]
    return {"rows": rows, "team": {"problem": None, "members": members if members is not None else [
        {"owner": "ana", "colab_tier": "free", "colab_config_present": True}]}}


def _local(state: str = "ready", workspace: bool = True) -> dict:
    return {"workspace": {"present": workspace, "state": "ready" if workspace else "missing"},
            "targets": [{"repo": "repo", "present": state != "missing", "state": state,
                         "missing": ["torch"] if state == "incomplete" else []}]}


def _view(timing: dict | None = TIMING, **kw) -> dict:
    parsed = run_options.parse_timing(timing) if timing is not None else None
    if parsed:
        parsed["file"] = "implementations/repo/Poc/Results/timing.json"
    products = [{"repo": "repo", "name": "Poc", "kind": "poc", "timing": parsed}]
    return {"products": products, "local_environment": kw.get("local", _local()),
            "remote_services": kw.get("services", _services())}


def _row(options: dict, stage: str, host: str) -> dict:
    return next(r for r in options["rows"] if r["stage"] == stage and r["host"] == host)


class FormulaTests(unittest.TestCase):
    def test_per_arm_mean_times_scale_plus_setup(self) -> None:
        parsed = run_options.parse_timing(TIMING)
        local = [m for m in parsed["measurements"] if m["host"] == "local"]
        # arms A (2, 4 -> 3) and B (6): mean 4.5; 4.5*10*3*2*2 + 5*3*2
        self.assertEqual(run_options.estimate_seconds(local, parsed["scales"]["poc"]), 570.0)

    def test_overall_mean_when_an_arm_is_missing(self) -> None:
        measurements = [{"host": "local", "arm": "A", "secondsPerUnit": 2.0},
                        {"host": "local", "arm": None, "secondsPerUnit": 6.0}]
        scale = {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}
        self.assertEqual(run_options.estimate_seconds(measurements, scale), 4.0)

    def test_no_measurement_is_no_estimate(self) -> None:
        self.assertIsNone(run_options.estimate_seconds([], {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}))

    def test_malformed_timing_is_rejected_or_filtered(self) -> None:
        self.assertIsNone(run_options.parse_timing({"schema": 2, "measurements": []}))
        self.assertIsNone(run_options.parse_timing(["not", "a", "dict"]))
        parsed = run_options.parse_timing({"schema": 1, "measurements": [
            {"host": "local", "unit": "epoch", "secondsPerUnit": "fast"},
            {"host": "local", "unit": "step", "secondsPerUnit": 1.0},
            {"host": "local", "unit": "epoch", "secondsPerUnit": float("nan")},
            {"host": "local", "unit": "epoch", "secondsPerUnit": 3.0, "setupSeconds": -1},
        ], "scales": {"poc": {"arms": 0, "folds": 1, "seeds": 1, "epochs": 1},
                      "full": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 2}}})
        self.assertEqual([m["secondsPerUnit"] for m in parsed["measurements"]], [3.0])
        self.assertIsNone(parsed["measurements"][0]["setupSeconds"])
        self.assertEqual(set(parsed["scales"]), {"full"})


class OptionTests(unittest.TestCase):
    def test_rows_per_stage_and_host_with_a_twenty_percent_range(self) -> None:
        options = run_options.run_options(Path("."), _view())
        self.assertEqual([(r["stage"], r["host"]) for r in options["rows"]],
                         [(s, h) for s in ("poc", "full") for h in remote_services.RUN_HOSTS])
        local = _row(options, "poc", "local")
        self.assertTrue(local["available"])
        self.assertEqual(local["estimate"]["seconds"], 570.0)
        self.assertEqual(local["estimate"]["low"], 456.0)
        self.assertEqual(local["estimate"]["high"], 684.0)
        self.assertIn("±20%", local["estimate_label"])
        self.assertIn("±20%, single-probe extrapolation", options["note"])
        remote = _row(options, "poc", REMOTE_A)
        self.assertEqual(remote["estimate"]["seconds"], 120.0 + 360.0)
        full_local = _row(options, "full", "local")
        self.assertEqual(full_local["estimate"]["seconds"], 4.5 * 100 * 5 * 5 * 2 + 5 * 25)

    def test_a_host_without_its_own_measurement_reads_unmeasured(self) -> None:
        options = run_options.run_options(Path("."), _view())
        colab = _row(options, "poc", REMOTE_B)
        self.assertIsNone(colab["estimate"])
        self.assertEqual(colab["estimate_label"], "sin medir")
        options = run_options.run_options(Path("."), _view(timing=None))
        self.assertTrue(all(r["estimate"] is None for r in options["rows"]))
        self.assertTrue(options["empty"])
        self.assertIn("timing.json", options["empty_hint"])

    def test_availability_per_host(self) -> None:
        options = run_options.run_options(Path("."), _view())
        self.assertTrue(_row(options, "poc", REMOTE_A)["available"])
        self.assertTrue(_row(options, "poc", REMOTE_B)["available"])
        self.assertFalse(_row(options, "full", REMOTE_B)["available"])
        self.assertIn("pago", _row(options, "full", REMOTE_B)["reason"])
        paid = _services(members=[{"owner": "bo", "colab_tier": "pro", "colab_config_present": True}])
        self.assertTrue(_row(run_options.run_options(Path("."), _view(services=paid)), "full", REMOTE_B)["available"])
        unsigned = _services(members=[{"owner": "bo", "colab_tier": "pro", "colab_config_present": False}])
        self.assertFalse(_row(run_options.run_options(Path("."), _view(services=unsigned)), "poc", REMOTE_B)["available"])
        for broken in (_services(token="inactive"), _services(cli="missing"), _services(accounts=0)):
            with self.subTest(broken=broken["rows"]):
                self.assertFalse(_row(run_options.run_options(Path("."), _view(services=broken)), "poc", REMOTE_A)["available"])
        no_colab_cli = _services(colab_cli="missing")
        self.assertFalse(_row(run_options.run_options(Path("."), _view(services=no_colab_cli)), "poc", REMOTE_B)["available"])
        incomplete = run_options.run_options(Path("."), _view(local=_local("incomplete")))
        self.assertFalse(_row(incomplete, "poc", "local")["available"])
        self.assertIn("torch", _row(incomplete, "poc", "local")["reason"])
        workspace_only = {"workspace": {"present": True, "state": "ready"}, "targets": []}
        self.assertTrue(_row(run_options.run_options(Path("."), _view(local=workspace_only)), "poc", "local")["available"])

    def test_recommendations(self) -> None:
        options = run_options.run_options(Path("."), _view())
        self.assertEqual(options["recommendations"]["poc"]["host"], "local")
        self.assertEqual(options["recommendations"]["full"]["host"], REMOTE_A)
        self.assertIn("ensayo", options["recommendations"]["full"]["text"])
        slow = json.loads(json.dumps(TIMING))
        for m in slow["measurements"]:
            if m["host"] == "local":
                m["secondsPerUnit"] *= 100
        options = run_options.run_options(Path("."), _view(timing=slow))
        self.assertEqual(options["recommendations"]["poc"]["host"], REMOTE_A)
        options = run_options.run_options(Path("."), _view(timing=None))
        self.assertEqual(options["recommendations"]["poc"]["host"], "local")
        self.assertIn("sonda", options["recommendations"]["poc"]["text"])
        nothing = _services(token="inactive", colab_cli="missing")
        options = run_options.run_options(Path("."), _view(timing=None, local=_local("missing", False),
                                                           services=nothing))
        self.assertIsNone(options["recommendations"]["full"]["host"])

    def test_the_placement_limits_are_reported(self) -> None:
        options = run_options.run_options(Path("."), _view())
        self.assertEqual(options["local_limit_seconds"], 1200)
        self.assertEqual(options["poc_budget_seconds"], 18000)

    def test_a_full_run_within_twenty_minutes_locally_stays_local(self) -> None:
        small = json.loads(json.dumps(TIMING))
        small["scales"]["full"] = {"arms": 2, "folds": 2, "seeds": 1, "epochs": 10}
        # local 4.5 x 10 x 2 x 1 x 2 = 180 + setup 5 x 2 x 1 = 190 s, high 228 s
        options = run_options.run_options(Path("."), _view(timing=small))
        self.assertEqual(options["recommendations"]["full"]["host"], "local")
        self.assertIn("20 min", options["recommendations"]["full"]["text"])

    def test_over_twenty_minutes_locally_without_a_cloud_measurement_asks_for_a_cloud_probe(self) -> None:
        local_only = json.loads(json.dumps(TIMING))
        local_only["measurements"] = [m for m in local_only["measurements"] if m["host"] == "local"]
        options = run_options.run_options(Path("."), _view(timing=local_only))
        full = options["recommendations"]["full"]
        # local 4.5 x 100 x 5 x 5 x 2 = 22500 s: over 20 minutes, no cloud host measured
        self.assertIn(full["host"], (REMOTE_A, REMOTE_B))
        self.assertIn("más de 20 min", full["text"])
        self.assertIn("sonda", full["text"])

    def test_a_proof_of_concept_over_five_hours_asks_to_reduce_the_design(self) -> None:
        big = json.loads(json.dumps(TIMING))
        big["scales"]["poc"] = {"arms": 2, "folds": 5, "seeds": 5, "epochs": 1000}
        # remote 1 x 1000 x 5 x 5 x 2 = 50000 + 60 x 25 = 51500 s, over 5 h
        options = run_options.run_options(Path("."), _view(timing=big))
        poc = options["recommendations"]["poc"]
        self.assertEqual(poc["host"], REMOTE_A)
        self.assertEqual(poc["poc_budget"], "exceeds")
        self.assertIn("5 h", poc["text"])
        self.assertIn("reduce", poc["text"])
        self.assertEqual(run_options.run_options(Path("."), _view())["recommendations"]["poc"]["poc_budget"],
                         "within")

    def test_never_raises_on_a_broken_view(self) -> None:
        options = run_options.run_options(Path("."), {"products": "nope", "remote_services": None})
        self.assertEqual(len(options["rows"]), 6)
        self.assertFalse(any(r["available"] for r in options["rows"]))


class ViewWiringTests(unittest.TestCase):
    def test_the_experiments_view_reads_timing_and_carries_both_tables(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        poc = root / "implementations" / "repo" / "Poc"
        (poc / "Results").mkdir(parents=True)
        (poc / "AGREED.md").write_text("ok\n", encoding="utf-8")
        (poc / "Results" / "timing.json").write_text(json.dumps(TIMING), encoding="utf-8")
        view = experiments_view.get_experiments_view(root)
        self.assertEqual(view["products"][0]["timing"]["file"], "implementations/repo/Poc/Results/timing.json")
        self.assertIn("local_environment", view)
        self.assertEqual(len(view["run_options"]["rows"]), 6)
        self.assertEqual(_row(view["run_options"], "poc", "local")["estimate"]["seconds"], 570.0)

    def test_a_failing_probe_never_breaks_the_view(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        with mock.patch.object(experiments_view, "local_environment", side_effect=RuntimeError("x")), \
                mock.patch.object(experiments_view, "run_options", side_effect=RuntimeError("y")):
            view = experiments_view.get_experiments_view(holder.name)
        self.assertEqual(view["local_environment"]["targets"], [])
        self.assertEqual(view["run_options"]["rows"], [])


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class RenderTests(unittest.TestCase):
    def render(self, view: dict) -> str:
        script = (
            "const fs=require('fs');global.window={};global.document={addEventListener(){}};"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_both_tables_render_and_escape(self) -> None:
        view = _view()
        view["local_environment"] = {
            "workspace": {"label": "Entorno micromamba", "path": ".micromamba/envs/papersmith/bin/python",
                          "present": True, "python": "3.12.4", "state": "ready", "micromamba": "/x/micromamba",
                          "detail": "ok"},
            "targets": [{"repo": "<img src=x onerror=alert(1)>", "path": "implementations/r/.venv/bin/python",
                         "present": True, "python": "3.11", "state": "incomplete",
                         "libraries": [{"name": "torch", "version": "2.4"}, {"name": "pytest", "version": None}],
                         "missing": ["pytest"], "device": "cuda:<b>GPU</b>", "detail": "falta pytest"}],
            "note": "nota"}
        view["run_options"] = run_options.run_options(Path("."), view)
        view["run_options"]["rows"][0]["reason"] = "<script>alert(2)</script>"
        out = self.render(view)
        self.assertIn("Entorno local", out)
        self.assertIn("Opciones de corrida", out)
        self.assertIn("Recomendación", out)
        self.assertIn("±20%", out)
        self.assertIn("sin medir", out)
        self.assertIn("pytest", out)
        self.assertIn("3.12.4", out)
        self.assertNotIn("<img src=x", out)
        self.assertNotIn("<script>alert(2)", out)
        self.assertNotIn("<b>GPU</b>", out)
        self.assertLess(out.index("Opciones de corrida"), out.index("Prueba de concepto"))

    def test_the_placement_rules_and_the_poc_budget_badge_render(self) -> None:
        big = json.loads(json.dumps(TIMING))
        big["scales"]["poc"] = {"arms": 2, "folds": 5, "seeds": 5, "epochs": 1000}
        view = _view(timing=big)
        view["run_options"] = run_options.run_options(Path("."), view)
        out = self.render(view)
        self.assertIn("más de 20 min corre en la nube", out)
        self.assertIn("cabe en 5 h", out)
        self.assertIn("excede 5 h", out)
        view = _view()
        view["run_options"] = run_options.run_options(Path("."), view)
        self.assertNotIn("excede 5 h", self.render(view))

    def test_the_empty_state_names_the_timing_probe(self) -> None:
        view = _view(timing=None)
        view["run_options"] = run_options.run_options(Path("."), view)
        out = self.render(view)
        self.assertIn("Results/timing.json", out)
        self.assertIn("/remote-parallelism", out)
        self.assertIn("Estimate before you scale", out)


if __name__ == "__main__":
    unittest.main()
