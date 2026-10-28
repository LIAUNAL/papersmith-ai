"""Remote runs per worker in the Experiments tab (S6, parallel campaigns).

Each product's ``remote_workers`` folds its ``.remote-execution/ledger.jsonl``
into one row per worker, with that worker's lanes (one per entrypoint and
concurrent slot) grouped under it. The existing ``runs`` fold is unchanged.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view, remote_services, server

SCRIPT_PATH = Path(server.__file__).resolve().parent / "static" / "experiments-panel.js"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _submitted(sid: str, worker: str, ts: str, entrypoint: str = "tools/full/job/run.py", **extra) -> dict:
    event = {"kind": "submitted", "ts": ts, "entrypoint": entrypoint, "sourceDigest": "d",
             "submissionId": sid, "worker": worker, "requestedCapacity": 2, "grantedCapacity": 2}
    event.update(extra)
    return event


LEDGER = [
    _submitted("k1", "alice", "2026-10-01T00:00:00Z"),
    _submitted("k2", "alice", "2026-10-01T00:00:01Z", slot=2, units=["seed-2", "seed-4"]),
    _submitted("c1", "colab:ana", "2026-10-01T00:00:02Z"),
    {"kind": "returned", "ts": "2026-10-01T02:00:00Z", "submissionId": "k1", "artifactPath": "out",
     "observedConcurrency": 2},
    {"kind": "errored", "ts": "2026-10-01T03:00:00Z", "submissionId": "c1", "reason": "quota exhausted"},
    # A resubmission of the same lane supersedes the older one.
    _submitted("c2", "colab:ana", "2026-10-02T00:00:00Z"),
]


def _workspace(case: unittest.TestCase, events: list[dict]) -> Path:
    holder = tempfile.TemporaryDirectory()
    case.addCleanup(holder.cleanup)
    root = Path(holder.name)
    product = root / "implementations" / "repo" / "FullModel"
    _write(product / "Experimental_AGREED.md", "agreed\n")
    _write(product / ".remote-execution" / "ledger.jsonl",
           "\n".join(json.dumps(e) for e in events) + "\n")
    return root


def _product(root: Path) -> dict:
    return experiments_view.get_experiments_view(root)["products"][0]


class RemoteWorkersViewTests(unittest.TestCase):
    def test_runs_are_grouped_per_worker_with_their_slots(self) -> None:
        workers = _product(_workspace(self, LEDGER))["remote_workers"]
        self.assertEqual([w["worker"] for w in workers], ["colab:ana", "alice"])
        alice = workers[1]
        self.assertEqual(alice["service"], "kaggle")
        self.assertEqual([(lane["slot"], lane["state"], lane["submission_id"]) for lane in alice["lanes"]],
                         [(1, "returned", "k1"), (2, "submitted", "k2")])
        self.assertEqual(alice["lanes"][0]["ts"], "2026-10-01T02:00:00Z")
        self.assertEqual(alice["by_state"], {"returned": 1, "submitted": 1})
        ana = workers[0]
        self.assertEqual(ana["service"], "colab")
        self.assertEqual([(lane["submission_id"], lane["state"], lane["reason"]) for lane in ana["lanes"]],
                         [("c2", "submitted", "")])
        self.assertEqual(ana["last_update"], "2026-10-02T00:00:00Z")

    def test_units_come_from_the_event_and_are_absent_otherwise(self) -> None:
        alice = _product(_workspace(self, LEDGER))["remote_workers"][1]
        self.assertIsNone(alice["lanes"][0]["units"])
        self.assertEqual(alice["lanes"][1]["units"], ["seed-2", "seed-4"])
        self.assertEqual(alice["lanes"][1]["granted"], 2)

    def test_service_is_derived_from_the_worker_id_prefix(self) -> None:
        self.assertEqual(remote_services.service_of_worker("colab:ana"), "colab")
        self.assertEqual(remote_services.service_of_worker("colab"), "colab")
        self.assertEqual(remote_services.service_of_worker("alice"), "kaggle")
        self.assertEqual(remote_services.service_of_worker(""), "")

    def test_the_worker_list_is_bounded(self) -> None:
        events = [_submitted(f"s{i}", f"user{i}", f"2026-10-01T00:{i // 60:02d}:{i % 60:02d}Z")
                  for i in range(experiments_view.MAX_REMOTE_WORKERS + 5)]
        events += [_submitted(f"e{i}", "user0", "2026-10-03T00:00:00Z", entrypoint=f"tools/e{i}/run.py")
                   for i in range(experiments_view.MAX_WORKER_LANES + 5)]
        workers = _product(_workspace(self, events))["remote_workers"]
        self.assertEqual(len(workers), experiments_view.MAX_REMOTE_WORKERS)
        self.assertEqual(workers[0]["worker"], "user0")
        self.assertEqual(len(workers[0]["lanes"]), experiments_view.MAX_WORKER_LANES)
        self.assertEqual(workers[0]["lane_count"], experiments_view.MAX_WORKER_LANES + 6)

    def test_the_existing_runs_fold_is_unchanged(self) -> None:
        runs = _product(_workspace(self, LEDGER))["runs"]
        self.assertEqual(runs, {
            "count": 1,
            "by_state": {"submitted": 1},
            "latest": [{"entrypoint": "tools/full/job/run.py", "state": "submitted", "worker": "colab:ana",
                        "submission_id": "c2", "ts": "2026-10-02T00:00:00Z", "reason": ""}],
        })

    def test_a_product_without_a_ledger_has_no_workers(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        _write(Path(holder.name) / "implementations" / "repo" / "Poc" / "AGREED.md", "agreed\n")
        self.assertEqual(_product(Path(holder.name))["remote_workers"], [])


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class RemoteWorkersRenderTests(unittest.TestCase):
    def render(self, view: dict) -> str:
        script = (
            "const fs=require('fs');global.window={};global.document={addEventListener(){}};"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_renders_the_per_worker_table_escaped(self) -> None:
        events = LEDGER + [_submitted("x<1>", "<img src=x onerror=alert(1)>", "2026-10-03T00:00:00Z",
                                      units=["<b>u</b>"])]
        out = self.render(experiments_view.get_experiments_view(_workspace(self, events)))
        self.assertIn("Ejecuciones remotas por worker", out)
        self.assertIn("colab:ana", out)
        self.assertIn("kaggle", out)
        self.assertIn("seed-2, seed-4", out)
        self.assertIn("slot 2", out)
        self.assertIn("k2", out)
        self.assertNotIn("<img src=x", out)
        self.assertNotIn("<b>u</b>", out)
        self.assertIn("&lt;b&gt;u&lt;/b&gt;", out)

    def test_no_table_without_workers(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        _write(Path(holder.name) / "implementations" / "repo" / "Poc" / "AGREED.md", "agreed\n")
        out = self.render(experiments_view.get_experiments_view(holder.name))
        self.assertNotIn("Ejecuciones remotas por worker", out)


if __name__ == "__main__":
    unittest.main()
