"""Remote results come back without the clone's regenerable directories.

A remote job clones the product into `clone/` and its code downloads the
dataset into the clone's `.cache/`. Fetch used to bring every file back, so a
workspace kept one copy of the dataset per run (23 copies of a 306 MB cache,
about 13 GB, in one real workspace). Nothing local reads those folders: the
gate reads `bootstrap.json`, continuations read `partial.json`, `runs.jsonl`
and the declared carry paths, and the dashboard reads ledgers. So fetch skips
`.cache`, `__pycache__`, `.venv` and `.git` under `clone/`, on Kaggle and on
Colab, and `remote_cli.py prune-caches` clears the copies older fetches left.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_remote_execution import (
    COLAB,
    COLAB_EXECUTOR,
    REMOTE_CLI_SCRIPT,
    _ColabCLISimulator,
    _load_kaggle_driver_module,
    _load_or_reuse,
    _session_answering,
    _streamed,
)
from tests.test_papersmith_init import WorkspaceSetupEnvTests

KEPT = ["log.txt", "Results/e1/partial.json", "clone/Prod/Results/runs.jsonl",
        "clone/Prod/Results/checkpoints/last.pt", "clone/Prod/src/cache.py"]
SKIPPED = ["clone/.cache/eeg-data/b2bd.npz", "clone/Prod/.cache/eeg-data/b2bd.json",
           "clone/Prod/src/__pycache__/model.cpython-312.pyc", "clone/.venv/lib/site.py",
           "clone/.git/objects/pack/p.pack"]


class KaggleFetchTests(unittest.TestCase):
    def test_the_driver_skips_regenerable_directories_and_never_requests_them(self) -> None:
        driver = _load_kaggle_driver_module()
        requested: list[str] = []

        def answer(request):
            requested.append(request.url)
            return _streamed(b"payload")

        names = [name for name in KEPT + SKIPPED if name != "log.txt"]

        class _Client:
            def __init__(self):
                self._client = SimpleNamespace(_session=_session_answering(answer))

            def list_kernel_session_output(self, request):
                return SimpleNamespace(files=[SimpleNamespace(url=f"https://files.example.invalid/{n}",
                                                              file_name=n) for n in names],
                                       log="ok\n")

            def get_kernel_session_status(self, request):
                return SimpleNamespace(status="complete", failure_message="")

        with tempfile.TemporaryDirectory() as tmp:
            into = Path(tmp) / "out"
            result = driver.cmd_fetch(_Client(), "acct-1/kernel-1", into)
            self.assertEqual(result["files"], sorted(KEPT))
            for name in KEPT:
                self.assertTrue((into / name).is_file(), name)
            for name in SKIPPED:
                self.assertFalse((into / name).exists(), name)
                self.assertNotIn(f"https://files.example.invalid/{name}", requested)


class ColabFetchTests(unittest.TestCase):
    def test_the_executor_manifest_leaves_regenerable_directories_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in [n for n in KEPT if n != "log.txt"] + SKIPPED:
                (base / name).parent.mkdir(parents=True, exist_ok=True)
                (base / name).write_text("x", encoding="utf-8")
            self.assertEqual(COLAB_EXECUTOR.manifest_entries(base), sorted(n for n in KEPT if n != "log.txt"))

    def test_the_adapter_skips_them_even_when_an_older_manifest_lists_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sim = _ColabCLISimulator(tmp)
            name = "psmith-x-00000000"
            session_dir = sim.session_dir(name)
            session_dir.mkdir(parents=True, exist_ok=True)
            sim.seed_session(name)
            listed = [n for n in KEPT if n != "log.txt"] + SKIPPED
            for entry in listed:
                (session_dir / entry).parent.mkdir(parents=True, exist_ok=True)
                (session_dir / entry).write_text("x", encoding="utf-8")
            (session_dir / "files.json").write_text(json.dumps(listed), encoding="utf-8")
            (session_dir / "status.json").write_text(json.dumps({"exitCode": 0, "finishedAt": "t"}),
                                                     encoding="utf-8")
            adapter = COLAB.ColabAdapter(colab_executable=str(sim.executable), remote_root=str(sim.remote_root))
            into = Path(tmp) / "out"
            adapter.fetch("colab/" + name, into)
            for entry in listed:
                self.assertEqual((into / entry).exists(), entry not in SKIPPED, entry)


def _remote_cli():
    return _load_or_reuse("remote_execution_cli", REMOTE_CLI_SCRIPT)


class PruneCachesTests(unittest.TestCase):
    def product(self, tmp: str) -> Path:
        product = Path(tmp) / "implementations" / "repo" / "Prod"
        returned = product / ".remote-execution"
        for name in (*KEPT, *SKIPPED):
            for run in ("returned/e1_run", "rehearsal/acct/papersmith-e1", "quarantine/acct"):
                path = returned / run / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 10)
        (product / "Results" / ".cache").mkdir(parents=True)
        (product / "Results" / ".cache" / "keep.json").write_text("{}", encoding="utf-8")
        (returned / "returned" / "e1_run" / "Results" / ".cache").mkdir(parents=True)
        (returned / "returned" / "e1_run" / "Results" / ".cache" / "keep.json").write_text("{}", encoding="utf-8")
        return product

    def run_cli(self, *argv: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = _remote_cli().main(["prune-caches", *argv])
        return code, json.loads(out.getvalue())

    def test_a_dry_run_lists_the_caches_and_removes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product = self.product(tmp)
            code, report = self.run_cli("--product", str(product))
            self.assertEqual(code, 0)
            self.assertFalse(report["applied"])
            self.assertEqual(len(report["dirs"]), 3 * 5)
            self.assertTrue(all("/clone/" in d for d in report["dirs"]))
            self.assertGreater(report["bytes"], 0)
            self.assertTrue((product / ".remote-execution/returned/e1_run/clone/.cache/eeg-data/b2bd.npz").exists())

    def test_apply_removes_only_the_clone_caches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product = self.product(tmp)
            code, report = self.run_cli("--product", str(product), "--apply")
            self.assertEqual(code, 0)
            self.assertTrue(report["applied"])
            base = product / ".remote-execution"
            for run in ("returned/e1_run", "rehearsal/acct/papersmith-e1", "quarantine/acct"):
                for name in KEPT:
                    self.assertTrue((base / run / name).is_file(), f"{run}/{name}")
                for name in SKIPPED:
                    self.assertFalse((base / run / name).exists(), f"{run}/{name}")
            self.assertTrue((base / "returned/e1_run/Results/.cache/keep.json").is_file())
            self.assertTrue((product / "Results/.cache/keep.json").is_file())

    def test_a_product_without_remote_runs_has_nothing_to_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, report = self.run_cli("--product", tmp, "--apply")
            self.assertEqual((code, report["dirs"], report["bytes"]), (0, [], 0))


class SetupEnvCleanTests(WorkspaceSetupEnvTests):
    def test_install_drops_the_package_downloads_it_no_longer_needs(self) -> None:
        calls = self.install_calls(self.new_bare_root())
        self.assertEqual(calls[-1], ["clean", "--all", "--yes"])


del WorkspaceSetupEnvTests

if __name__ == "__main__":
    unittest.main()
