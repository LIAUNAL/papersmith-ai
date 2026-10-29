"""Slot queues: one session runs a queue of units instead of one unit per
slot (odd/tasks/slot-queues.md).

S1 -- `distribute` and campaign `submit` place every unit: units beyond the
granted slots join per-slot queues, balanced, never duplicated; with a timing
record each queue is cut into sessions that fit the session margin, and what
does not fit is a chain of sessions on the same account.
S2 -- the runner receives a slot's whole queue in `FORGE_RUN_UNITS`, and
`remaining` reads a queue's `partial.json` exactly as a one-unit share's.
S3 -- the consent token binds a queued campaign's placement, so a launch whose
placement differs from the approved one is refused before anything is sent;
a campaign with no more units than slots keeps the v0.39.0 records byte for
byte (`fixtures/slot_queues/one_unit_per_slot_v0_39_0.json`, captured from
v0.39.0 by running this file as a script before the change).

Run with: python -m pytest -q tests/test_slot_queues.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.remote_fakes import ADAPTER, JOBFOLDER, LEDGER, REMOTE_CLI, REPOSITORY_ROOT  # noqa: E402

PACKER = sys.modules["remote_execution_packer"]
GOLDEN = REPOSITORY_ROOT / "tests/fixtures/slot_queues/one_unit_per_slot_v0_39_0.json"
PRODUCT = "FEM-TOLLA"
COMMIT = "a" * 40
DIGEST = "d" * 64
SERVICE = "svc"
ENTRYPOINT = "tools/svc/search-a/runner.ipynb"
LIMIT_SECONDS = 12 * 3600


class QueueAdapter(ADAPTER.Adapter):
    """Healthy workers with a declared capacity and, optionally, a declared
    session limit; every `submit` is recorded and answered with an id per
    worker and slot."""

    def __init__(self, workers: list[tuple[str, int]], limit: int | None = None) -> None:
        self._workers = [ADAPTER.Worker(id=name, capacity=cap) for name, cap in workers]
        self._limit = limit
        self.jobs: list = []
        self.list_active_calls: list[str] = []

    def session_limit_seconds(self, machine_shape=None):
        return self._limit

    def workers(self) -> list:
        return list(self._workers)

    def submit(self, job) -> "ADAPTER.Submission":
        self.jobs.append(job)
        slot = job.run_config.get("slot", 1)
        return ADAPTER.Submission(id=f"{job.worker}/kernel-{slot}", worker=job.worker)

    def poll(self, submission_id: str) -> "ADAPTER.Status":
        return ADAPTER.Status(state="complete", detail="fake")

    def fetch(self, submission_id: str, into: Path) -> "ADAPTER.Fetched":
        into.mkdir(parents=True, exist_ok=True)
        return ADAPTER.Fetched(path=into, complete=True, files=())

    def cancel(self, submission_id: str) -> None:
        pass

    def list_active(self, worker: str) -> list:
        self.list_active_calls.append(worker)
        return []


def _timing(folds: int) -> dict:
    """A schema 1 record on SERVICE: 450 s per epoch, 10 epochs, one arm, one
    seed, a 300 s setup. With `folds` units, one unit's work at the upper
    bound is 1.2 x 450 x 10 s = 90 minutes, and the setup, paid once per
    session, is 5 minutes: a session of 12 h (576 usable minutes) holds 6."""
    measurement = {"measuredAt": "2026-10-29T00:00:00Z", "host": f"{SERVICE}:alice",
                   "device": "cuda:T4", "arm": "a", "unit": "epoch",
                   "secondsPerUnit": 450, "unitsMeasured": 3, "setupSeconds": 300}
    scale = {"arms": 1, "folds": folds, "seeds": 1, "epochs": 10}
    return {"schema": 1, "measurements": [measurement], "scales": {"poc": scale, "full": scale}}


def _legacy(tmp: str) -> tuple[Path, Path]:
    target = Path(tmp) / "repo"
    notebooks = target / PRODUCT / "Notebooks"
    notebooks.mkdir(parents=True)
    notebook = notebooks / "a.ipynb"
    notebook.write_text("{}", encoding="utf-8")
    return target, notebook


def _job_folder(tmp: str, *, timing_folds: int | None = None) -> tuple[Path, Path]:
    """A job folder on SERVICE at COMMIT, with every worker's launch record
    (the operator's `gate` for `units` is written by `_gate`)."""
    target = Path(tmp) / "repo"
    (target / PRODUCT).mkdir(parents=True)
    job_dir = target / "tools" / SERVICE / "search-a"
    job_dir.mkdir(parents=True)
    notebook = job_dir / "runner.ipynb"
    notebook.write_text("{}", encoding="utf-8")
    run_config = {
        "schemaVersion": 1, "product": PRODUCT, "service": SERVICE, "jobName": "search-a",
        "commit": COMMIT, "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
        "clonePaths": ["src/pkg"], "run": {"module": "pkg.mod", "function": "run"},
        "runnerTemplate": [],
    }
    (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
    if timing_folds is not None:
        results = target / PRODUCT / "Results"
        results.mkdir(parents=True)
        (results / "timing.json").write_text(json.dumps(_timing(timing_folds)), encoding="utf-8")
    return target, notebook


def _gate(target: Path, units, workers) -> None:
    """The operator's `gate` record for `units` and each worker's passing
    rehearsal at COMMIT -- the records a job-folder campaign needs."""
    position = target / PRODUCT / ".implementation" / "position.jsonl"
    position.parent.mkdir(parents=True, exist_ok=True)
    with position.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "kind": "gate", "jobName": "search-a", "worker": None, "commit": COMMIT,
            "revision": "r", "revisionSha256": "f" * 64, "entrypoint": ENTRYPOINT,
            "units": list(units), "justification": "fixture", "session": "s",
            "at": "2020-01-01T00:00:00+00:00"}) + "\n")
    smoke = REMOTE_CLI._smoke_ledger_path(target.resolve(), PRODUCT)
    smoke.parent.mkdir(parents=True, exist_ok=True)
    with smoke.open("a", encoding="utf-8") as handle:
        for worker in workers:
            handle.write(json.dumps({
                "kind": REMOTE_CLI.SMOKE_RESULT_KIND, "ts": "2020-01-01T00:00:00+00:00",
                "jobName": "search-a", "result": "pass", "commit": COMMIT,
                "worker": worker, "missing": []}) + "\n")


def _distribute(target: Path, notebook: Path, adapter, units) -> dict:
    return REMOTE_CLI.cmd_distribute(target=target, entrypoint=notebook, adapter=adapter,
                                     units=units, source_digest=lambda t, n: DIGEST)


def _submit(target: Path, notebook: Path, adapter, units, consent) -> dict:
    return REMOTE_CLI.cmd_submit(target=target, entrypoint=notebook, requested=1,
                                 adapter=adapter, source_digest=lambda t, n: DIGEST,
                                 units=units, consent=consent)


def _ledger_lines(target: Path) -> list[str]:
    path = REMOTE_CLI._main_ledger_path(target.resolve(), PRODUCT)
    if not path.is_file():
        return []
    return [re.sub(r'"ts": "[^"]*"', '"ts": "<ts>"', line)
            for line in path.read_text(encoding="utf-8").splitlines()]


def _portable(value, root: Path):
    """`value` as JSON text with the temporary root spelled `<tmp>`."""
    text = json.dumps(value, default=str, sort_keys=True)
    return json.loads(text.replace(str(root.resolve()), "<tmp>"))


def _records(kind: str, workers, units, *, timing_folds: int | None = None) -> dict:
    """Everything a campaign leaves behind: the `distribute` report, the
    consent token, the `submit` result, each job's `run_config` and the ledger
    lines (timestamps elided)."""
    with tempfile.TemporaryDirectory() as tmp:
        if kind == "legacy":
            target, notebook = _legacy(tmp)
        else:
            target, notebook = _job_folder(tmp, timing_folds=timing_folds)
            _gate(target, units, [name for name, _ in workers])
        adapter = QueueAdapter(workers, limit=None if kind == "legacy" else LIMIT_SECONDS)
        report = _distribute(target, notebook, adapter, units)
        result = _submit(target, notebook, adapter, units, report["consentToken"])
        return {
            "distribute": _portable(report, Path(tmp)),
            "submit": _portable(result, Path(tmp)),
            # Each run_config as the exact text of its keys in insertion order.
            "jobs": [{"worker": job.worker,
                      "runConfig": json.dumps(dict(job.run_config), default=str)}
                     for job in adapter.jobs],
            "ledger": [line.replace(str(Path(tmp).resolve()), "<tmp>")
                       for line in _ledger_lines(target)],
        }


#: Campaigns with no more units than granted slots, as v0.39.0 launched them.
SCENARIOS = {
    "legacy-2x2-four-units": ("legacy", [("w1", 2), ("w2", 2)], ("u0", "u1", "u2", "u3"), None),
    "legacy-ragged-two-units": ("legacy", [("w1", 2), ("w2", 1)], ("u0", "u1"), None),
    "job-folder-with-timing-three-units": (
        "job", [("w1", 2), ("w2", 2)], ("f1", "f2", "f3"), 3),
}


def _scenario(name: str) -> dict:
    kind, workers, units, folds = SCENARIOS[name]
    with unittest.mock.patch.object(JOBFOLDER, "verify_pin_preconditions", return_value=None):
        return _records(kind, workers, units, timing_folds=folds)


TEN = tuple(f"u{index}" for index in range(10))

#: 10 units on w1 x 2 and w2 x 2: the four places in round-robin order are
#: w1 slot 1, w2 slot 1, w1 slot 2, w2 slot 2, and unit i joins place i mod 4.
TEN_QUEUES = {
    ("w1", 1): ["u0", "u4", "u8"], ("w1", 2): ["u2", "u6"],
    ("w2", 1): ["u1", "u5", "u9"], ("w2", 2): ["u3", "u7"],
}


def _placement_token(units, queues: dict) -> str:
    """The consent token of a queued campaign of ENTRYPOINT at COMMIT,
    spelled out by hand: the v0.39.0 payload plus `placement`, one
    `{worker, slot, units}` per slot in launch order, keys sorted."""
    import hashlib
    payload = {"entrypoint": ENTRYPOINT, "pin": COMMIT, "units": list(units),
               "placement": [{"worker": worker, "slot": slot, "units": list(queue)}
                             for (worker, slot), queue in queues.items()]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _queues_of(report: dict) -> dict:
    return {(row["worker"], row["slot"]): row["units"] for row in report["queues"]}


class QueuedDistributionTests(unittest.TestCase):
    """S1: every unit is placed, in per-slot queues balanced by count."""

    def test_ten_units_on_two_workers_of_two_slots_form_four_balanced_queues(self) -> None:
        adapter = QueueAdapter([("w1", 2), ("w2", 2)])
        result = PACKER.distribute(adapter=adapter, units=TEN, ledger_lines=[],
                                   live_digest=DIGEST)

        self.assertEqual(result.places, 4)
        self.assertEqual(result.unplaced, ())
        self.assertEqual(result.skipped, ())
        self.assertEqual({row.plan.worker: row.units for row in result.assignments},
                         {"w1": ("u0", "u2", "u4", "u6", "u8"),
                          "w2": ("u1", "u3", "u5", "u7", "u9")})
        queues = {(row.plan.worker, slot + 1): list(share)
                  for row in result.assignments
                  for slot, share in enumerate(PACKER.slot_shares(row))}
        self.assertEqual(queues, TEN_QUEUES)
        flat = [unit for queue in queues.values() for unit in queue]
        self.assertEqual(sorted(flat), sorted(TEN), "every unit is placed")
        self.assertEqual(len(flat), len(set(flat)), "no unit is placed twice")
        sizes = [len(queue) for queue in queues.values()]
        self.assertLessEqual(max(sizes) - min(sizes), 1, "queues are balanced")
        self.assertEqual(adapter.jobs, [], "distribute sends nothing")

    def test_a_pinned_continuation_joins_its_full_workers_queue(self) -> None:
        adapter = QueueAdapter([("w1", 2), ("w2", 1)])
        result = PACKER.distribute(adapter=adapter, units=("u0", "u1", "u2"),
                                   ledger_lines=[], live_digest=DIGEST,
                                   affinity={"u0": "w2", "u1": "w2"})

        self.assertEqual(result.unplaced, ())
        self.assertEqual({row.plan.worker: row.units for row in result.assignments},
                         {"w1": ("u2",), "w2": ("u0", "u1")})
        self.assertEqual([PACKER.slot_shares(row) for row in result.assignments],
                         [(("u2",),), (("u0", "u1"),)])

    def test_units_stay_unplaced_only_when_no_worker_grants_a_place(self) -> None:
        adapter = QueueAdapter([("w1", 0)])
        result = PACKER.distribute(adapter=adapter, units=("u0", "u1"), ledger_lines=[],
                                   live_digest=DIGEST)
        self.assertEqual(result.places, 0)
        self.assertEqual(result.unplaced, ("u0", "u1"))
        self.assertEqual(result.assignments, ())


class QueuedCampaignTests(unittest.TestCase):
    """S1-S3 through `distribute` and campaign `submit`."""

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(JOBFOLDER, "verify_pin_preconditions",
                                             return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ten_units_launch_four_queues_in_one_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, TEN, ["w1", "w2"])
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            report = _distribute(target, notebook, adapter, TEN)
            self.assertEqual(report["places"], 4)
            self.assertEqual(report["assigned"], 10)
            self.assertEqual(report["unplaced"], [])
            self.assertEqual(_queues_of(report), TEN_QUEUES)
            self.assertEqual({row["worker"]: row["shares"] for row in report["assignments"]},
                             {"w1": [TEN_QUEUES[("w1", 1)], TEN_QUEUES[("w1", 2)]],
                              "w2": [TEN_QUEUES[("w2", 1)], TEN_QUEUES[("w2", 2)]]})
            # No timing record: balanced by count, each queue's fit unknown.
            self.assertEqual([row["sessions"] for row in report["queues"]], [None] * 4)
            self.assertFalse(report["sessionFit"]["measured"])
            self.assertIn("timing.json", report["sessionFit"]["reason"])
            self.assertEqual(report["consentToken"], _placement_token(TEN, TEN_QUEUES))
            self.assertNotEqual(report["consentToken"], REMOTE_CLI.campaign_consent_token(
                pin_commit=COMMIT, relative_entrypoint=ENTRYPOINT, units=TEN))
            self.assertEqual(adapter.jobs, [])
            self.assertEqual(_ledger_lines(target), [])

            result = _submit(target, notebook, adapter, TEN, report["consentToken"])

            sent = {(job.worker, job.run_config.get("slot", 1)): job.run_config["units"]
                    for job in adapter.jobs}
            self.assertEqual(sent, TEN_QUEUES, "each slot's job carries its whole queue")
            self.assertEqual(len(adapter.jobs), 4)
            for job in adapter.jobs:
                self.assertEqual(job.run_config["sessionLimitSeconds"], LIMIT_SECONDS)
            self.assertEqual(result["unplaced"], [])
            self.assertEqual(_queues_of(result), TEN_QUEUES)
            self.assertEqual(
                {(row["worker"], entry["slot"]): entry["units"]
                 for row in result["assignments"] for entry in row["submissions"]},
                TEN_QUEUES)
            events = [json.loads(line) for line in _ledger_lines(target)]
            self.assertEqual([event["kind"] for event in events], ["submitted"] * 4)
            self.assertEqual({(event["worker"], event.get("slot", 1)): event["units"]
                              for event in events}, TEN_QUEUES)
            self.assertEqual({event["submissionId"] for event in events},
                             {"w1/kernel-1", "w1/kernel-2", "w2/kernel-1", "w2/kernel-2"})

    def test_with_a_timing_record_each_queue_fits_the_session_margin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp, timing_folds=10)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            report = _distribute(target, notebook, adapter, TEN)

            fit = report["sessionFit"]
            self.assertTrue(fit["measured"])
            self.assertEqual((fit["unitMinutes"], fit["setupMinutes"], fit["usableMinutes"],
                              fit["unitsPerSession"]), (90, 5, 576, 6))
            self.assertEqual(_queues_of(report), TEN_QUEUES)
            for row in report["queues"]:
                self.assertEqual(row["sessions"], [row["units"]], "one session holds it")
                self.assertLessEqual(5 + 90 * len(row["units"]), 576)
                self.assertEqual(row["minutes"], 5 + 90 * len(row["units"]))
                self.assertFalse(row["chained"])
            self.assertEqual(adapter.jobs, [])

    def test_a_queue_over_the_margin_is_chained_on_the_same_account(self) -> None:
        units = tuple(f"f{index:02d}" for index in range(28))
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp, timing_folds=28)
            _gate(target, units, ["w1", "w2"])
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            report = _distribute(target, notebook, adapter, units)

            self.assertEqual(report["unplaced"], [])
            self.assertEqual(report["sessionFit"]["unitsPerSession"], 6)
            queues = _queues_of(report)
            self.assertEqual([len(queue) for queue in queues.values()], [7, 7, 7, 7])
            for row in report["queues"]:
                self.assertEqual(row["sessions"], [row["units"][:6], row["units"][6:]])
                self.assertTrue(row["chained"])
                # Each chained session pays the setup again: 5 + 6 x 90, then 5 + 90.
                self.assertEqual(row["minutes"], 640)
            self.assertEqual(report["sessionFit"]["makespanMinutes"], 640)
            flat = [unit for queue in queues.values() for unit in queue]
            self.assertEqual(sorted(flat), sorted(units))

            result = _submit(target, notebook, adapter, units, report["consentToken"])

            # One job per slot, holding the whole chained queue: the runner's
            # deadline cuts it and `remaining` carries the rest (S2).
            self.assertEqual(len(adapter.jobs), 4)
            self.assertEqual({(job.worker, job.run_config.get("slot", 1)): job.run_config["units"]
                              for job in adapter.jobs}, queues)
            self.assertEqual(_queues_of(result), queues)
            self.assertEqual(result["sessionFit"], report["sessionFit"])
            events = [json.loads(line) for line in _ledger_lines(target)]
            self.assertEqual([len(event["units"]) for event in events], [7, 7, 7, 7])

    def test_an_explicit_timing_path_and_stage_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            elsewhere = Path(tmp) / "timing.json"
            elsewhere.write_text(json.dumps(_timing(10)), encoding="utf-8")
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            report = REMOTE_CLI.cmd_distribute(
                target=target, entrypoint=notebook, adapter=adapter, units=TEN,
                source_digest=lambda t, n: DIGEST, timing=elsewhere, stage="poc")

            self.assertTrue(report["sessionFit"]["measured"])
            self.assertIn("poc upper bound", report["sessionFit"]["source"])


class QueueCommandLineTests(unittest.TestCase):
    """`distribute` and `submit` take `--timing` and `--stage` on the command line."""

    def _main(self, argv: list[str], adapter) -> tuple[int, dict]:
        import contextlib
        import io
        stdout = io.StringIO()
        with unittest.mock.patch.object(REMOTE_CLI, "_load_backend_module", return_value=None), \
                unittest.mock.patch.object(REMOTE_CLI.ADAPTER, "resolve", return_value=QueueAdapter), \
                unittest.mock.patch.object(REMOTE_CLI, "_construct_adapter", return_value=adapter), \
                unittest.mock.patch.object(REMOTE_CLI, "_load_source_digest",
                                           return_value=lambda t, p: DIGEST), \
                unittest.mock.patch.object(JOBFOLDER, "verify_pin_preconditions",
                                           return_value=None), \
                contextlib.redirect_stdout(stdout):
            code = REMOTE_CLI.main(argv)
        return code, json.loads(stdout.getvalue())

    def test_distribute_and_submit_read_the_named_timing_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, TEN, ["w1", "w2"])
            elsewhere = Path(tmp) / "timing.json"
            elsewhere.write_text(json.dumps(_timing(10)), encoding="utf-8")
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)
            common = ["--target", str(target), "--entrypoint", str(notebook),
                      "--backend", "queue", "--timing", str(elsewhere), "--stage", "poc"]
            common += [token for unit in TEN for token in ("--unit", unit)]

            code, report = self._main(["distribute", *common], adapter)
            self.assertEqual(code, 0)
            self.assertEqual(report["sessionFit"]["unitsPerSession"], 6)
            self.assertIn("poc upper bound", report["sessionFit"]["source"])
            self.assertEqual(adapter.jobs, [])

            code, result = self._main(
                ["submit", *common, "--consent", report["consentToken"]], adapter)
            self.assertEqual(code, 0)
            self.assertEqual(result["queues"], report["queues"])
            self.assertEqual(result["sessionFit"], report["sessionFit"])
            self.assertEqual(len(adapter.jobs), 4)
            self.assertEqual(len(_ledger_lines(target)), 4)


class PlacementConsentTests(unittest.TestCase):
    """S3: a queued launch is refused unless its placement is the approved one."""

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(JOBFOLDER, "verify_pin_preconditions",
                                             return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _refused(self, target, notebook, adapter, consent) -> str:
        with self.assertRaises(REMOTE_CLI.ConsentError) as caught:
            _submit(target, notebook, adapter, TEN, consent)
        self.assertEqual(adapter.jobs, [], "nothing was sent")
        self.assertEqual(_ledger_lines(target), [], "nothing was recorded")
        return str(caught.exception)

    def test_a_placement_that_moved_since_distribute_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, TEN, ["w1", "w2"])
            token = _distribute(target, notebook, QueueAdapter([("w1", 2), ("w2", 2)]),
                                TEN)["consentToken"]
            # w2 now grants one slot: three queues instead of four.
            moved = QueueAdapter([("w1", 2), ("w2", 1)], limit=LIMIT_SECONDS)

            message = self._refused(target, notebook, moved, token)

            self.assertIn("PLACEMENT_NOT_CONSENTED", message)
            self.assertIn("distribute", message)

    def test_the_units_only_token_does_not_authorize_a_queued_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, TEN, ["w1", "w2"])
            units_only = REMOTE_CLI.campaign_consent_token(
                pin_commit=COMMIT, relative_entrypoint=ENTRYPOINT, units=TEN)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            message = self._refused(target, notebook, adapter, units_only)

            self.assertIn("PLACEMENT_NOT_CONSENTED", message)

    def test_a_forged_token_is_refused_before_anything_is_sent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, TEN, ["w1", "w2"])
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            self._refused(target, notebook, adapter, "0" * 64)

    def test_the_approved_placement_still_needs_the_operators_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)
            token = _distribute(target, notebook, adapter, TEN)["consentToken"]

            with self.assertRaises(REMOTE_CLI.AuthorizationError):
                _submit(target, notebook, adapter, TEN, token)
            self.assertEqual(adapter.jobs, [])
            self.assertEqual(_ledger_lines(target), [])


#: The QMLEEG wave-2 shape (L2): ten ids, fold1 and fold2 already returned.
WAVE = tuple(f"fold{fold}-{part}" for fold in range(1, 6) for part in ("a", "b"))
RETURNED = WAVE[:4]


def _returned(tmp: str, target: Path, notebook: Path, units, *, files=None,
              missing: bool = False) -> None:
    """Launch `units` as their own campaign and settle every share it sent
    `returned`: with `files` written into each result, or recorded at a path
    that is not on disk when `missing`."""
    adapter = QueueAdapter([("w1", 2), ("w2", 2)])
    token = _distribute(target, notebook, adapter, units)["consentToken"]
    _submit(target, notebook, adapter, units, token)
    ledger = REMOTE_CLI._main_ledger_path(target.resolve(), PRODUCT)
    for job in adapter.jobs:
        sid = f"{job.worker}/kernel-{job.run_config.get('slot', 1)}"
        artifact = Path(tmp) / "results" / sid.replace("/", "-")
        if not missing:
            artifact.mkdir(parents=True)
            for name, text in (files or {}).items():
                (artifact / name).write_text(text, encoding="utf-8")
        LEDGER.append(ledger, LEDGER.returned_event(
            submission_id=sid, artifact_path=str(artifact), observed_concurrency=1))


class DoneUnitsTests(unittest.TestCase):
    """L2: a campaign's full unit list never re-places a unit whose share
    already returned complete -- the units `remaining` calls complete are
    reported under `done` and placed nowhere."""

    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(JOBFOLDER, "verify_pin_preconditions",
                                             return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _placed(self, report: dict) -> list[str]:
        return [unit for row in report["assignments"] for unit in row["units"]]

    def test_distribute_excludes_the_returned_units_and_places_every_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _returned(tmp, target, notebook, RETURNED)
            before = _ledger_lines(target)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, WAVE)

            self.assertEqual(report["done"], list(RETURNED))
            self.assertEqual(report["units"], 10)
            self.assertEqual(report["assigned"], 6)
            self.assertEqual(report["unplaced"], [])
            self.assertEqual(sorted(self._placed(report)), sorted(WAVE[4:]))
            self.assertEqual(_queues_of(report), {
                ("w1", 1): ["fold3-a", "fold5-a"], ("w1", 2): ["fold4-a"],
                ("w2", 1): ["fold3-b", "fold5-b"], ("w2", 2): ["fold4-b"]})
            remaining = REMOTE_CLI.cmd_remaining(target=target, entrypoint=notebook,
                                                 units=WAVE, source_digest=lambda t, n: DIGEST)
            self.assertEqual(remaining["complete"], report["done"])
            self.assertEqual(remaining["remaining"], self._placed_in_order(report))
            self.assertEqual(adapter.jobs, [])
            self.assertEqual(_ledger_lines(target), before, "distribute records nothing")

    def _placed_in_order(self, report: dict) -> list[str]:
        placed = set(self._placed(report))
        return [unit for unit in WAVE if unit in placed]

    def test_the_token_binds_the_placement_after_the_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _returned(tmp, target, notebook, ("u0", "u1"))
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, ("u0", "u1", "u2", "u3"))

            # Two units left on four places: one per slot, yet the token
            # binds the placement and what was left out.
            self.assertEqual(report["done"], ["u0", "u1"])
            import hashlib
            payload = {"entrypoint": "Notebooks/a.ipynb", "pin": None,
                       "units": ["u0", "u1", "u2", "u3"], "done": ["u0", "u1"],
                       "placement": [{"worker": "w1", "slot": 1, "units": ["u2"]},
                                     {"worker": "w2", "slot": 1, "units": ["u3"]}]}
            self.assertEqual(report["consentToken"], hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest())

    def test_submit_with_the_full_list_sends_only_what_is_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _returned(tmp, target, notebook, RETURNED)
            before = len(_ledger_lines(target))
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])
            report = _distribute(target, notebook, adapter, WAVE)

            result = _submit(target, notebook, adapter, WAVE, report["consentToken"])

            sent = [unit for job in adapter.jobs for unit in job.run_config["units"]]
            self.assertEqual(sorted(sent), sorted(WAVE[4:]))
            self.assertEqual(result["done"], list(RETURNED))
            self.assertEqual(result["unplaced"], [])
            self.assertEqual(result["queues"], report["queues"])
            events = [json.loads(line) for line in _ledger_lines(target)[before:]]
            self.assertEqual([event["kind"] for event in events], ["submitted"] * 4)
            self.assertEqual(sorted(u for event in events for u in event["units"]),
                             sorted(WAVE[4:]))

    def test_a_token_minted_before_the_results_returned_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])
            stale = _distribute(target, notebook, adapter, WAVE)["consentToken"]
            _returned(tmp, target, notebook, RETURNED)
            before = _ledger_lines(target)
            launch = QueueAdapter([("w1", 2), ("w2", 2)])

            with self.assertRaises(REMOTE_CLI.ConsentError) as caught:
                _submit(target, notebook, launch, WAVE, stale)

            self.assertIn("PLACEMENT_NOT_CONSENTED", str(caught.exception))
            self.assertEqual(launch.jobs, [])
            self.assertEqual(_ledger_lines(target), before)

    def test_a_result_no_longer_on_disk_stays_placeable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _returned(tmp, target, notebook, RETURNED, missing=True)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, WAVE)

            self.assertNotIn("done", report)
            self.assertEqual(sorted(self._placed(report)), sorted(WAVE))
            remaining = REMOTE_CLI.cmd_remaining(target=target, entrypoint=notebook,
                                                 units=WAVE, source_digest=lambda t, n: DIGEST)
            self.assertEqual(remaining["unknown"], list(RETURNED))

    def test_a_unit_a_partial_result_left_is_placed_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            # Each share of the earlier campaign stopped early: everything it
            # carried but fold1-a is left to do.
            _returned(tmp, target, notebook, RETURNED, files={"partial.json": json.dumps(
                {"remaining": ["fold1-b", "fold2-a", "fold2-b"]})})
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, WAVE)

            self.assertEqual(report["done"], ["fold1-a"])
            self.assertEqual(sorted(self._placed(report)), sorted(WAVE[1:]))

    def test_a_job_folder_campaign_gated_for_the_full_list_launches_what_is_left(self) -> None:
        """The `gate` record binds the list the invocation names: gated for
        all ten, a full-list submit launches the eight not done."""
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _job_folder(tmp)
            _gate(target, RETURNED, ["w1", "w2"])
            with unittest.mock.patch.object(REMOTE_CLI, "_declared_session_limit",
                                            return_value=None):
                _returned(tmp, target, notebook, RETURNED)
            _gate(target, WAVE, ["w1", "w2"])
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)
            report = _distribute(target, notebook, adapter, WAVE)

            result = _submit(target, notebook, adapter, WAVE, report["consentToken"])

            self.assertEqual(result["done"], list(RETURNED))
            self.assertEqual(sorted(u for job in adapter.jobs for u in job.run_config["units"]),
                             sorted(WAVE[4:]))


def _launch(target: Path, notebook: Path, units) -> list:
    """Launch `units` as their own campaign and leave every share in flight."""
    adapter = QueueAdapter([("w1", 2), ("w2", 2)])
    token = _distribute(target, notebook, adapter, units)["consentToken"]
    _submit(target, notebook, adapter, units, token)
    return adapter.jobs


def _settle(tmp: str, target: Path, jobs) -> None:
    """Settle each share `jobs` sent `returned`, with a result on disk."""
    ledger = REMOTE_CLI._main_ledger_path(target.resolve(), PRODUCT)
    for job in jobs:
        sid = f"{job.worker}/kernel-{job.run_config.get('slot', 1)}"
        artifact = Path(tmp) / "settled" / sid.replace("/", "-")
        artifact.mkdir(parents=True)
        LEDGER.append(ledger, LEDGER.returned_event(
            submission_id=sid, artifact_path=str(artifact), observed_concurrency=1))


class InFlightUnitsTests(unittest.TestCase):
    """L3: a unit whose share was submitted and has not returned is never
    placed again -- the units `remaining` calls in flight are reported under
    `inFlight`, bound by the token, and launched nowhere."""

    def _placed(self, report: dict) -> list[str]:
        return [unit for row in report["assignments"] for unit in row["units"]]

    def test_a_unit_in_flight_is_not_placed_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _launch(target, notebook, RETURNED)
            before = _ledger_lines(target)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, WAVE)

            self.assertEqual(report["inFlight"], list(RETURNED))
            self.assertNotIn("done", report)
            self.assertEqual(report["units"], 10)
            self.assertEqual(report["assigned"], 6)
            self.assertEqual(report["unplaced"], [])
            self.assertEqual(sorted(self._placed(report)), sorted(WAVE[4:]))
            remaining = REMOTE_CLI.cmd_remaining(target=target, entrypoint=notebook,
                                                 units=WAVE, source_digest=lambda t, n: DIGEST)
            self.assertEqual(remaining["inFlight"], report["inFlight"])
            self.assertEqual(remaining["remaining"], list(WAVE[4:]))
            self.assertEqual(remaining["complete"], [])
            self.assertEqual(adapter.jobs, [])
            self.assertEqual(_ledger_lines(target), before, "distribute records nothing")

            result = _submit(target, notebook, adapter, WAVE, report["consentToken"])

            sent = [unit for job in adapter.jobs for unit in job.run_config["units"]]
            self.assertEqual(sorted(sent), sorted(WAVE[4:]))
            self.assertEqual(result["inFlight"], list(RETURNED))
            self.assertNotIn("done", result)
            self.assertEqual(result["queues"], report["queues"])
            events = [json.loads(line) for line in _ledger_lines(target)[len(before):]]
            self.assertEqual(sorted(u for event in events for u in event["units"]),
                             sorted(WAVE[4:]))

    def test_a_unit_that_returns_complete_moves_from_in_flight_to_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            jobs = _launch(target, notebook, RETURNED)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])
            self.assertEqual(_distribute(target, notebook, adapter, WAVE)["inFlight"],
                             list(RETURNED))

            _settle(tmp, target, jobs)
            report = _distribute(target, notebook, adapter, WAVE)

            self.assertEqual(report["done"], list(RETURNED))
            self.assertNotIn("inFlight", report)
            self.assertEqual(sorted(self._placed(report)), sorted(WAVE[4:]))

    def test_the_token_binds_the_units_in_flight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            _launch(target, notebook, ("u0", "u1"))
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])

            report = _distribute(target, notebook, adapter, ("u0", "u1", "u2", "u3"))

            import hashlib
            payload = {"entrypoint": "Notebooks/a.ipynb", "pin": None,
                       "units": ["u0", "u1", "u2", "u3"], "inFlight": ["u0", "u1"],
                       "placement": [{"worker": "w1", "slot": 1, "units": ["u2"]},
                                     {"worker": "w2", "slot": 1, "units": ["u3"]}]}
            self.assertEqual(report["consentToken"], hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest())

    def test_a_token_minted_while_units_were_in_flight_is_refused_once_they_return(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            jobs = _launch(target, notebook, RETURNED)
            stale = _distribute(target, notebook, QueueAdapter([("w1", 2), ("w2", 2)]),
                                WAVE)["consentToken"]
            _settle(tmp, target, jobs)
            before = _ledger_lines(target)
            launch = QueueAdapter([("w1", 2), ("w2", 2)])

            with self.assertRaises(REMOTE_CLI.ConsentError) as caught:
                _submit(target, notebook, launch, WAVE, stale)

            self.assertIn("PLACEMENT_NOT_CONSENTED", str(caught.exception))
            self.assertIn("done, left out: fold1-a", str(caught.exception))
            self.assertEqual(launch.jobs, [])
            self.assertEqual(_ledger_lines(target), before)

    def test_a_token_minted_before_units_were_launched_is_refused_naming_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            stale = _distribute(target, notebook, QueueAdapter([("w1", 2), ("w2", 2)]),
                                WAVE)["consentToken"]
            _launch(target, notebook, RETURNED)
            before = _ledger_lines(target)
            launch = QueueAdapter([("w1", 2), ("w2", 2)])

            with self.assertRaises(REMOTE_CLI.ConsentError) as caught:
                _submit(target, notebook, launch, WAVE, stale)

            message = str(caught.exception)
            self.assertIn("PLACEMENT_NOT_CONSENTED", message)
            self.assertIn("in flight, left out: fold1-a, fold1-b, fold2-a, fold2-b", message)
            self.assertEqual(launch.jobs, [], "nothing is sent twice")
            self.assertEqual(_ledger_lines(target), before)

    def test_a_campaign_whose_every_unit_is_in_flight_or_done_sends_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            jobs = _launch(target, notebook, RETURNED[:2])
            _settle(tmp, target, jobs)
            _launch(target, notebook, RETURNED[2:])
            before = _ledger_lines(target)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)], limit=LIMIT_SECONDS)

            report = _distribute(target, notebook, adapter, RETURNED)

            self.assertEqual(report["done"], list(RETURNED[:2]))
            self.assertEqual(report["inFlight"], list(RETURNED[2:]))
            self.assertEqual(report["assigned"], 0)
            self.assertEqual(report["unplaced"], [])
            self.assertEqual(report["queues"], [])

            result = _submit(target, notebook, adapter, RETURNED, report["consentToken"])

            self.assertEqual(adapter.jobs, [])
            self.assertEqual(result["queues"], [])
            self.assertEqual(_ledger_lines(target), before)


class QueueRunnerAndRemainingTests(unittest.TestCase):
    """S2: a queue travels whole to the runner and `remaining` reads it per slot."""

    def test_the_runner_hands_the_target_the_whole_queue(self) -> None:
        runner = sys.modules.get("remote_execution_runner_invoke")
        if runner is None:
            from tests.remote_fakes import _load_or_reuse
            runner = _load_or_reuse("remote_execution_runner_invoke",
                                    REPOSITORY_ROOT / "skills/remote-execution/assets/runner_invoke.py")
        env = runner.submission_environment(units=TEN_QUEUES[("w1", 1)])
        self.assertEqual(env, {"FORGE_RUN_UNITS": json.dumps(["u0", "u4", "u8"])})

    def test_remaining_lists_what_a_cut_queue_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target, notebook = _legacy(tmp)
            adapter = QueueAdapter([("w1", 2), ("w2", 2)])
            token = _distribute(target, notebook, adapter, TEN)["consentToken"]
            _submit(target, notebook, adapter, TEN, token)
            ledger = REMOTE_CLI._main_ledger_path(target.resolve(), PRODUCT)
            for sid in ("w1/kernel-1", "w1/kernel-2", "w2/kernel-1", "w2/kernel-2"):
                artifact = Path(tmp) / sid.replace("/", "-")
                artifact.mkdir()
                if sid == "w1/kernel-1":
                    # Cut at the deadline after u0: u4 and u8 remain.
                    (artifact / "partial.json").write_text(
                        json.dumps({"remaining": ["u4", "u8"]}), encoding="utf-8")
                LEDGER.append(ledger, LEDGER.returned_event(
                    submission_id=sid, artifact_path=str(artifact), observed_concurrency=1))

            report = REMOTE_CLI.cmd_remaining(target=target, entrypoint=notebook, units=TEN,
                                              source_digest=lambda t, n: DIGEST)

            self.assertEqual(report["remaining"], ["u4", "u8"])
            self.assertEqual(report["complete"], [u for u in TEN if u not in ("u4", "u8")])
            self.assertEqual(report["inFlight"], [])
            self.assertEqual(report["unitArgs"], ["--unit", "u4", "--unit", "u8"])


def _parallelism(argv: list[str]) -> dict:
    """Run remote-parallelism's CLI (the module `remote_cli` reads its rules
    from) and return its JSON."""
    import contextlib
    import io
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = REMOTE_CLI._parallelism_cli().run(argv)
    assert code == 0, stdout.getvalue()
    return json.loads(stdout.getvalue())


class PlanningAgreementTests(unittest.TestCase):
    """S4: `schedule` and `plan` report the queues and makespan `distribute`
    launches: 28 units on two accounts of two slots each, 90 minutes per unit
    at the upper bound, a 5-minute setup and 12-hour sessions."""

    UNITS = tuple(f"f{index:02d}" for index in range(28))
    ACCOUNTS = [("svc:alice", 2), ("svc:bob", 2)]

    def _launched(self, tmp: str, accounts) -> dict:
        target, notebook = _job_folder(tmp, timing_folds=28)
        adapter = QueueAdapter(accounts, limit=LIMIT_SECONDS)
        report = _distribute(target, notebook, adapter, self.UNITS)
        self.assertEqual(report["unplaced"], [])
        return report

    @staticmethod
    def _by_index(queues: list[dict], units) -> list[tuple]:
        return [(row["account"], row["slot"], [units[i] for i in row["units"]],
                 [[units[i] for i in session] for session in row["sessions"]], row["minutes"])
                for row in queues]

    def test_schedule_reports_the_queues_and_makespan_distribute_launches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            launched = self._launched(tmp, self.ACCOUNTS)
            timing = Path(tmp) / "repo" / PRODUCT / "Results" / "timing.json"
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({
                "schema": 1, "setupMinutes": 5,
                "steps": [{"id": "hpo", "units": 28, "services": [SERVICE], "axis": "fold",
                           "timing": {SERVICE: {"path": str(timing), "host": f"{SERVICE}:alice",
                                                "stage": "full"}}}],
                "accounts": [{"owner": owner, "service": SERVICE, "sessions": 2, "sessionHours": 12,
                              "quotaHours": None} for owner in ("alice", "bob")],
            }), encoding="utf-8")

            schedule = _parallelism(["--root", tmp, "schedule", "--plan", str(plan)])

            (step,) = schedule["steps"]
            self.assertEqual(self._by_index(step["queues"], self.UNITS),
                             [(row["worker"], row["slot"], row["units"], row["sessions"],
                               row["minutes"]) for row in launched["queues"]])
            self.assertEqual(step["queueMakespanMinutes"], launched["sessionFit"]["makespanMinutes"])
            self.assertEqual(schedule["makespanMinutes"], 640)
            self.assertEqual(step["queueMakespanMinutes"], 640)
            self.assertEqual([share["units"] for share in step["shares"]], [14, 14])

    def test_plan_reports_the_queues_and_makespan_distribute_launches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            launched = self._launched(tmp, [("svc:alice", 2)])
            timing = Path(tmp) / "repo" / PRODUCT / "Results" / "timing.json"

            result = _parallelism(["--root", tmp, "plan", "--timing", str(timing), "--stage", "full",
                                   "--account", f"alice:{SERVICE}:2:12:unknown"])

            (option,) = [item for item in result["plans"]["full"]["options"]
                         if item["option"] == f"{SERVICE}:alice"]
            self.assertEqual(self._by_index(option["queues"], self.UNITS),
                             [(row["worker"], row["slot"], row["units"], row["sessions"],
                               row["minutes"]) for row in launched["queues"]])
            self.assertEqual(option["queueMakespanMinutes"],
                             launched["sessionFit"]["makespanMinutes"])
            # 14 units per slot: three sessions of 6, 6 and 2 units.
            self.assertEqual(option["queueMakespanMinutes"], 3 * 5 + 14 * 90)


class SlotQueueDocTests(unittest.TestCase):
    """The skill and the changelog state slot queues, naming no service."""

    def test_the_skill_and_the_changelog_state_slot_queues(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-execution/SKILL.md").read_text(
            encoding="utf-8")
        rule = skill.split("**Slot queues.**", 1)[1].split("\n  - ", 1)[0]
        for needle in ("FORGE_RUN_UNITS", "`queues`", "`sessionFit`", "--timing", "--stage",
                       "unitsPerSession", "PLACEMENT_NOT_CONSENTED", "same account",
                       "`remaining`", "`done`", "`unknown`", "never placed again",
                       "`inFlight`", "no running unit is sent"):
            self.assertIn(needle, rule)
        for service in ("kaggle", "colab"):
            self.assertNotIn(service, rule.lower())
        self.assertIn("| `PLACEMENT_NOT_CONSENTED` | campaign `submit`", skill)
        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = changelog.split("\n## Unreleased\n", 1)[1].split("\n## ", 1)[0]
        for needle in ("Slot queues", "PLACEMENT_NOT_CONSENTED", "sessionFit", "unplaced",
                       "queueMakespanMinutes", "80% of its limit", "`done`", "`inFlight`"):
            self.assertIn(needle, unreleased)

    def test_remote_parallelism_states_the_queues_the_launch_runs(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-parallelism/SKILL.md").read_text(
            encoding="utf-8")
        rule = skill.split("**The queues the launch runs.**", 1)[1].split("\n\n", 1)[0]
        for needle in ("i mod slots", "round-robin", "80% of the limit", "same account",
                       "`queues`", "`queueMakespanMinutes`"):
            self.assertIn(needle, rule)
        for service in ("kaggle", "colab"):
            self.assertNotIn(service, rule.lower())
        self.assertIn("queues[{account, slot, units, sessions, minutes}]", skill)
        self.assertIn("queueMakespanMinutes?}]", skill)
        self.assertIn("(`done`, `inFlight`)", rule)


class OneUnitPerSlotGoldenTests(unittest.TestCase):
    """S3: units <= slots launches exactly what v0.39.0 launched."""

    def test_records_are_byte_identical_to_v0_39_0(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(sorted(golden), sorted(SCENARIOS))
        for name in SCENARIOS:
            with self.subTest(name):
                self.assertEqual(_scenario(name), golden[name])


if __name__ == "__main__":
    if sys.argv[1:] == ["--capture-golden"]:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({name: _scenario(name) for name in SCENARIOS},
                                     indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}")
    else:
        unittest.main()
