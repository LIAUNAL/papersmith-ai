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
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
from tests.test_remote_execution import JOBFOLDER

KEPT = ["log.txt", "Results/e1/partial.json", "clone/Prod/Results/runs.jsonl",
        "clone/Prod/Results/checkpoints/last.pt", "clone/Prod/src/cache.py"]
SKIPPED = ["clone/.cache/eeg-data/b2bd.npz", "clone/Prod/.cache/eeg-data/b2bd.json",
           "clone/Prod/src/__pycache__/model.cpython-312.pyc", "clone/.venv/lib/site.py",
           "clone/.git/objects/pack/p.pack"]
#: A worktree or submodule clone carries `.git` as a file, not a directory.
GIT_FILE = "clone/vendor/lib/.git"


class KaggleFetchTests(unittest.TestCase):
    def test_the_driver_skips_regenerable_directories_and_never_requests_them(self) -> None:
        driver = _load_kaggle_driver_module()
        requested: list[str] = []

        def answer(request):
            requested.append(request.url)
            return _streamed(b"payload")

        names = [name for name in KEPT + SKIPPED + [GIT_FILE] if name != "log.txt"]

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
            for name in SKIPPED + [GIT_FILE]:
                self.assertFalse((into / name).exists(), name)
                self.assertNotIn(f"https://files.example.invalid/{name}", requested)


class ColabFetchTests(unittest.TestCase):
    def test_the_executor_manifest_leaves_regenerable_directories_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in [n for n in KEPT if n != "log.txt"] + SKIPPED + [GIT_FILE]:
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


    def test_a_missing_product_is_refused_not_reported_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = _remote_cli().main(["prune-caches", "--product", str(Path(tmp) / "typo")])
            self.assertEqual(code, 2)
            self.assertIn("is not a directory", err.getvalue())

    def test_a_directory_that_cannot_be_removed_is_reported_and_the_rest_go(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product = self.product(tmp)
            cli = _remote_cli()
            real = cli.shutil.rmtree
            stuck = ".remote-execution/returned/e1_run/clone/.git"

            def rmtree(path, *args, **kwargs):
                if Path(path).as_posix().endswith(stuck):
                    raise PermissionError("read-only pack")
                return real(path, *args, **kwargs)

            with mock.patch.object(cli.shutil, "rmtree", rmtree):
                code, report = self.run_cli("--product", str(product), "--apply")
            self.assertEqual(code, 1)
            self.assertEqual(report["failed"], [{"dir": stuck, "error": "PermissionError: read-only pack"}])
            self.assertEqual(len(report["removed"]), 14)
            self.assertNotIn(stuck, report["removed"])
            self.assertTrue((product / stuck).is_dir())
            self.assertFalse((product / ".remote-execution/returned/e1_run/clone/.cache").exists())
            self.assertEqual(report["freed"], 14 * 10)

    def test_a_symlinked_cache_is_neither_followed_nor_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product = Path(tmp) / "Prod"
            outside = Path(tmp) / "elsewhere"
            (outside / "data.npz").parent.mkdir(parents=True)
            (outside / "data.npz").write_bytes(b"x" * 10)
            clone = product / ".remote-execution/returned/e1_run/clone"
            clone.mkdir(parents=True)
            (clone / ".cache").symlink_to(outside, target_is_directory=True)
            code, report = self.run_cli("--product", str(product), "--apply")
            self.assertEqual((code, report["dirs"]), (0, []))
            self.assertTrue((outside / "data.npz").is_file())
            self.assertTrue((clone / ".cache").is_symlink())


class CarryPathTests(unittest.TestCase):
    def test_a_carry_path_inside_a_directory_fetch_leaves_out_is_refused(self) -> None:
        for raw in ("Results/.cache/checkpoints", ".venv/state", "hpo/__pycache__/study.db", "src/.git"):
            with self.subTest(raw=raw):
                with self.assertRaises(JOBFOLDER.JobFolderError) as ctx:
                    JOBFOLDER.validate_carry_paths([raw])
                self.assertIn("a fetch leaves out", str(ctx.exception))

    def test_the_usual_carry_paths_still_pass(self) -> None:
        self.assertEqual(JOBFOLDER.validate_carry_paths(["Results/checkpoints", "hpo/studies"]),
                         ("Results/checkpoints", "hpo/studies"))


class OneRuleTests(unittest.TestCase):
    def test_every_copy_of_the_skipped_directory_names_agrees(self) -> None:
        driver = _load_kaggle_driver_module()
        copies = {
            "kaggle_driver": driver.REGENERABLE_DIRNAMES,
            "colab adapter": COLAB.REGENERABLE_DIRNAMES,
            "colab executor": COLAB_EXECUTOR.REGENERABLE_DIRNAMES,
            "remote_cli": _remote_cli().REGENERABLE_DIRNAMES,
            "jobfolder": JOBFOLDER.FETCH_SKIPPED_DIRNAMES,
        }
        self.assertEqual({name: sorted(value) for name, value in copies.items()},
                         {name: sorted(copies["kaggle_driver"]) for name in copies})


class SetupEnvCleanTests(WorkspaceSetupEnvTests):
    def test_install_drops_only_what_it_can_download_again(self) -> None:
        calls = self.install_calls(self.new_bare_root())
        self.assertEqual(calls[-1], ["clean", "--tarballs", "--index-cache", "--locks", "--yes"])

    def test_a_failed_cleanup_does_not_fail_a_built_environment(self) -> None:
        module = self.load_copy(self.new_bare_root())
        module.find_micromamba = lambda: Path("/fake/mm")
        module.env_exists = lambda name: False
        module.detect_cuda = lambda: False

        def run(mm, args, env):
            if args[0] == "clean":
                raise subprocess.CalledProcessError(1, ["micromamba", *args])

        module.run = run
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.cmd_install(argparse.Namespace(name="papersmith", cpu=True, cuda=False, no_ingestion=True))
        self.assertEqual(code, 0)
        self.assertIn("[setup] done", out.getvalue())
        self.assertIn("could not clean", out.getvalue())


del WorkspaceSetupEnvTests

if __name__ == "__main__":
    unittest.main()
