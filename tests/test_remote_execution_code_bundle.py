"""The code bundle: a private repository's pinned code carried inside the job.

A backend whose kernel cannot authenticate a clone (it has no way to attach a
repository credential) declares `CODE_BUNDLE_MAX_BYTES` on its adapter class.
For such a service, `generate-job --code-bundle` archives the declared clone
paths at the pinned commit with `git archive` (never the working tree),
gzips them, writes `code-bundle.tar.gz` into the job folder and records its
sha256 in `run-config.json`'s `codeBundle` block. The backend ships the bytes
inside the pushed notebook; `runner_bootstrap.py` verifies the sha256 and
unpacks instead of cloning, refusing any entry that would escape its clone
directory.

Every git call here runs on a throwaway local repository; nothing reaches a
network and no real credential is read.

Run with: python3 -m unittest tests.test_remote_execution_code_bundle
"""
from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/remote-execution/scripts"
ASSETS = REPOSITORY_ROOT / "skills/remote-execution/assets"


def _load_or_reuse(module_name: str, script: Path):
    """Reuse an already-loaded copy under the same name (the seam's own
    `sys.modules` discipline), so `isinstance` checks agree across suites."""
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_or_reuse("remote_execution_ledger", SCRIPTS / "ledger.py")
ADAPTER = _load_or_reuse("remote_execution_adapter", SCRIPTS / "adapter.py")
PACKER = _load_or_reuse("remote_execution_packer", SCRIPTS / "packer.py")
REMOTE_CLI = _load_or_reuse("remote_execution_cli", SCRIPTS / "remote_cli.py")
JOBFOLDER = sys.modules["remote_execution_jobfolder"]
KAGGLE = _load_or_reuse(
    "remote_execution_kaggle_adapter", SCRIPTS / "adapters" / "kaggle.py"
)
RUNNER_BOOTSTRAP = _load_or_reuse(
    "remote_execution_runner_bootstrap", ASSETS / "runner_bootstrap.py"
)

# A distinctive byte string standing in for a credential; it must never be
# found in anything generation or submission writes.
SECRET = "psmith-bundle-secret-7f3a9c"


class _BundleCarrier(ADAPTER.Adapter):
    """A test backend that declares the capability, nothing else."""

    CODE_BUNDLE_MAX_BYTES = 1_000_000

    def workers(self):
        return []

    def submit(self, job):
        raise NotImplementedError

    def poll(self, submission_id):
        raise NotImplementedError

    def fetch(self, submission_id, into):
        raise NotImplementedError

    def cancel(self, submission_id):
        raise NotImplementedError

    def list_active(self, worker):
        return []


class _TinyCarrier(_BundleCarrier):
    CODE_BUNDLE_MAX_BYTES = 64


class _NonCarrier(_BundleCarrier):
    CODE_BUNDLE_MAX_BYTES = None


CARRIER = "code-bundle-carrier"
TINY = "code-bundle-tiny-carrier"
NON_CARRIER = "code-bundle-non-carrier"
for _name, _cls in ((CARRIER, _BundleCarrier), (TINY, _TinyCarrier),
                    (NON_CARRIER, _NonCarrier)):
    ADAPTER.register(_name, _cls)
    ADAPTER.register_metadata(
        _name, lambda run_config: ("fake-metadata.json", json.dumps({"ok": True}))
    )


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "code-bundle-tests"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "code-bundle@example.invalid"
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def _init_target(root: Path) -> tuple[Path, str]:
    """A target with one clone path (`src/pkg`), a file outside it, and an
    IGNORED credential-shaped file inside the clone path: the working tree
    holds it, the commit does not."""
    target = root / "repo"
    (target / "src" / "pkg").mkdir(parents=True)
    (target / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (target / "src" / "pkg" / "mod.py").write_text(
        "def run(**kwargs):\n    return 1\n", encoding="utf-8"
    )
    (target / "README.md").write_text("outside every clone path\n", encoding="utf-8")
    (target / ".gitignore").write_text("*.token\n", encoding="utf-8")
    _git(target, "init", "-q")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "initial")
    (target / "src" / "pkg" / "repo.token").write_text(SECRET, encoding="utf-8")
    return target, _git(target, "rev-parse", "HEAD")


def _generate(target: Path, *, service: str = CARRIER, **overrides) -> Path:
    kwargs = dict(
        target=target,
        service=service,
        job_name="job-a",
        product="P",
        repo_url="https://example.invalid/private.git",
        repo_ref="main",
        clone_paths=["src/pkg"],
        run_module="pkg.mod",
        run_function="run",
    )
    kwargs.update(overrides)
    return JOBFOLDER.generate_job(**kwargs)


def _unreachable(*args, **kwargs):
    raise JOBFOLDER.JobFolderError(
        "generation refuses: the declared remote could not serve the pin "
        "(private repository, anonymous probe)"
    )


def _all_bytes_under(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file())


class GenerateCodeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # The remote is private: the anonymous probe always refuses.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable
        )
        self.probe = patcher.start()
        self.addCleanup(patcher.stop)

    def test_bundle_carries_tracked_clone_paths_at_the_pin_and_records_its_sha(self) -> None:
        target, commit = _init_target(self.root)

        job_dir = _generate(target, commit=commit, code_bundle=True)

        names = sorted(p.name for p in job_dir.iterdir())
        self.assertEqual(
            names,
            ["code-bundle.tar.gz", "fake-metadata.json", "run-config.json", "runner.ipynb"],
        )
        bundle = (job_dir / "code-bundle.tar.gz").read_bytes()
        run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            run_config["codeBundle"],
            {
                "file": "code-bundle.tar.gz",
                "format": "tar.gz",
                "sha256": hashlib.sha256(bundle).hexdigest(),
                "bytes": len(bundle),
            },
        )
        self.assertEqual(run_config["commit"], commit)
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            files = sorted(m.name for m in archive.getmembers() if m.isfile())
            mod = archive.extractfile("src/pkg/mod.py").read()
        # Only tracked files under the clone path: no README, no .gitignore,
        # and never the ignored credential-shaped file in the working tree.
        self.assertEqual(files, ["src/pkg/__init__.py", "src/pkg/mod.py"])
        self.assertEqual(mod, b"def run(**kwargs):\n    return 1\n")
        self.assertNotIn(SECRET.encode(), gzip.decompress(bundle))
        self.assertNotIn(SECRET.encode(), _all_bytes_under(job_dir))
        self.probe.assert_not_called()

    def test_bundle_is_byte_identical_across_regenerations(self) -> None:
        target, commit = _init_target(self.root)
        first = (_generate(target, commit=commit, code_bundle=True)
                 / "code-bundle.tar.gz").read_bytes()
        second = (_generate(target, commit=commit, code_bundle=True, regenerate=True)
                  / "code-bundle.tar.gz").read_bytes()
        self.assertEqual(first, second)

    def test_a_bundle_needs_no_anonymously_reachable_remote_and_defaults_to_head(self) -> None:
        target, commit = _init_target(self.root)
        real_run_git = JOBFOLDER._run_git
        asked: list = []

        def _spy(args, **kwargs):
            if args and args[0] in ("ls-remote", "fetch", "clone"):
                asked.append(list(args))
            return real_run_git(args, **kwargs)

        with unittest.mock.patch.object(JOBFOLDER, "_run_git", side_effect=_spy):
            job_dir = _generate(target, code_bundle=True)
        self.assertEqual(asked, [], "a bundled job never asks the remote")
        run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
        self.assertEqual(run_config["commit"], commit)
        self.probe.assert_not_called()

    def test_without_a_bundle_the_unreachable_remote_still_refuses(self) -> None:
        target, commit = _init_target(self.root)
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, commit=commit)
        self.assertIn("could not serve the pin", str(caught.exception))
        self.assertFalse((target / "tools").exists())
        self.probe.assert_called_once()

    def test_without_a_bundle_the_job_folder_is_exactly_as_before(self) -> None:
        target, commit = _init_target(self.root)
        with unittest.mock.patch.object(JOBFOLDER, "_verify_commit_reachable",
                                        return_value=None):
            job_dir = _generate(target, commit=commit)
        self.assertEqual(
            sorted(p.name for p in job_dir.iterdir()),
            ["fake-metadata.json", "run-config.json", "runner.ipynb"],
        )
        run_config = json.loads((job_dir / "run-config.json").read_text(encoding="utf-8"))
        self.assertNotIn("codeBundle", run_config)

    def test_a_bundle_still_refuses_a_pin_that_is_not_head_under_the_clone_paths(self) -> None:
        target, pinned = _init_target(self.root)
        (target / "src" / "pkg" / "mod.py").write_text(
            "def run(**kwargs):\n    return 2\n", encoding="utf-8")
        _git(target, "commit", "-q", "-am", "move on")
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, commit=pinned, code_bundle=True)
        self.assertIn("src/pkg/mod.py", str(caught.exception))
        self.assertFalse((target / "tools").exists())

    def test_a_bundle_still_refuses_a_pin_absent_from_local_history(self) -> None:
        target, _ = _init_target(self.root)
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, commit="d" * 40, code_bundle=True)
        self.assertIn("d" * 40, str(caught.exception))
        self.assertFalse((target / "tools").exists())

    def test_a_bundle_still_refuses_a_dirty_clone_path(self) -> None:
        target, commit = _init_target(self.root)
        (target / "src" / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        with self.assertRaises(JOBFOLDER.JobFolderError):
            _generate(target, commit=commit, code_bundle=True)
        self.assertFalse((target / "tools").exists())

    def test_a_service_that_does_not_carry_bundles_refuses_by_code(self) -> None:
        target, commit = _init_target(self.root)
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, service=NON_CARRIER, commit=commit, code_bundle=True)
        self.assertTrue(str(caught.exception).startswith("CODE_BUNDLE_NOT_CARRIED"))
        self.assertIn(NON_CARRIER, str(caught.exception))
        self.assertFalse((target / "tools").exists())

    def test_a_bundle_over_the_service_limit_refuses_naming_both_sizes(self) -> None:
        target, commit = _init_target(self.root)
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, service=TINY, commit=commit, code_bundle=True)
        message = str(caught.exception)
        self.assertTrue(message.startswith("CODE_BUNDLE_TOO_LARGE"), message)
        self.assertIn("64 bytes", message)
        self.assertRegex(message, r"is \d+ bytes")
        self.assertFalse((target / "tools").exists())

    def test_a_tracked_symlink_in_a_clone_path_refuses(self) -> None:
        target, _ = _init_target(self.root)
        os.symlink("../../README.md", target / "src" / "pkg" / "link.md")
        _git(target, "add", "-A")
        _git(target, "commit", "-q", "-m", "link")
        commit = _git(target, "rev-parse", "HEAD")
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            _generate(target, commit=commit, code_bundle=True)
        self.assertTrue(str(caught.exception).startswith("CODE_BUNDLE_UNSAFE_ENTRY"))
        self.assertIn("src/pkg/link.md", str(caught.exception))
        self.assertFalse((target / "tools").exists())

    def test_a_bundled_job_goes_stale_exactly_when_a_clone_path_changes(self) -> None:
        target, commit = _init_target(self.root)
        job_dir = _generate(target, commit=commit, code_bundle=True)
        _git(target, "add", "-A")
        _git(target, "commit", "-q", "-m", "job folder")
        self.assertEqual(JOBFOLDER.read(job_dir).staleness["status"], "fresh")

        (target / "README.md").write_text("docs moved\n", encoding="utf-8")
        _git(target, "commit", "-q", "-am", "docs only")
        self.assertEqual(JOBFOLDER.read(job_dir).staleness["status"], "fresh")

        (target / "src" / "pkg" / "mod.py").write_text("x = 2\n", encoding="utf-8")
        _git(target, "commit", "-q", "-am", "code moved")
        staleness = JOBFOLDER.read(job_dir).staleness
        self.assertEqual(staleness["status"], "drift")
        self.assertEqual(staleness["changedPaths"], ["src/pkg/mod.py"])

    def test_a_malformed_code_bundle_block_is_refused_on_read(self) -> None:
        target, commit = _init_target(self.root)
        job_dir = _generate(target, commit=commit, code_bundle=True)
        config_path = job_dir / "run-config.json"
        good = json.loads(config_path.read_text(encoding="utf-8"))
        for bad in (
            {**good["codeBundle"], "file": "../escape.tar.gz"},
            {**good["codeBundle"], "sha256": "not-a-sha"},
            {**good["codeBundle"], "bytes": -1},
            {**good["codeBundle"], "format": "zip"},
            "code-bundle.tar.gz",
        ):
            config_path.write_text(json.dumps({**good, "codeBundle": bad}), encoding="utf-8")
            with self.assertRaises(JOBFOLDER.JobFolderError, msg=repr(bad)):
                JOBFOLDER.read(job_dir)


class GenerateJobCliCodeBundleTests(unittest.TestCase):
    """`generate-job --code-bundle` through the real front door, against the
    real shipped backend that declares the capability."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _argv(self, target: Path, *extra: str) -> list[str]:
        return [
            "generate-job", "--target", str(target), "--service", "kaggle",
            "--job-name", "job-a", "--product", "P",
            "--repo-url", "https://example.invalid/private.git", "--repo-ref", "main",
            "--clone-path", "src/pkg", "--run-module", "pkg.mod",
            "--run-function", "run", *extra,
        ]

    def _main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = REMOTE_CLI.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_code_bundle_flag_writes_the_bundle_and_reports_it(self) -> None:
        target, commit = _init_target(self.root)
        with unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable
        ) as probe:
            code, out, err = self._main(self._argv(target, "--code-bundle"))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        job_dir = Path(payload["jobFolder"])
        bundle = (job_dir / "code-bundle.tar.gz").read_bytes()
        self.assertEqual(payload["commit"], commit)
        self.assertEqual(payload["codeBundle"]["sha256"], hashlib.sha256(bundle).hexdigest())
        self.assertEqual(payload["codeBundle"]["bytes"], len(bundle))
        self.assertLessEqual(len(bundle), KAGGLE.KaggleAdapter.CODE_BUNDLE_MAX_BYTES)
        self.assertNotIn(SECRET, out + err)
        probe.assert_not_called()

    def test_without_the_flag_an_unreachable_remote_still_refuses(self) -> None:
        target, commit = _init_target(self.root)
        with unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable
        ):
            code, out, err = self._main(self._argv(target, "--commit", commit))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("could not serve the pin", err)
        self.assertFalse((target / "tools").exists())

    def test_help_names_the_flag(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            REMOTE_CLI.main(["generate-job", "--help"])
        self.assertIn("--code-bundle", out.getvalue())
        self.assertIn("CODE_BUNDLE_MAX_BYTES", out.getvalue())


class SubmitGateCodeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable
        )
        self.probe = patcher.start()
        self.addCleanup(patcher.stop)

    def _bundled_job(self) -> Path:
        target, commit = _init_target(self.root)
        job_dir = _generate(target, commit=commit, code_bundle=True)
        _git(target, "add", "-A")
        _git(target, "commit", "-q", "-m", "job folder")
        return job_dir

    def test_submit_gate_passes_a_bundled_job_without_asking_the_remote(self) -> None:
        job_dir = self._bundled_job()
        REMOTE_CLI._gate_job_folder_pin(job_dir / "runner.ipynb")
        self.probe.assert_not_called()

    def test_submit_gate_refuses_a_tampered_bundle_before_any_quota(self) -> None:
        job_dir = self._bundled_job()
        (job_dir / "code-bundle.tar.gz").write_bytes(b"tampered")
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            REMOTE_CLI._gate_job_folder_pin(job_dir / "runner.ipynb")
        self.assertTrue(str(caught.exception).startswith("CODE_BUNDLE_MISMATCH"))

    def test_submit_gate_refuses_a_missing_bundle(self) -> None:
        job_dir = self._bundled_job()
        (job_dir / "code-bundle.tar.gz").unlink()
        with self.assertRaises(JOBFOLDER.JobFolderError) as caught:
            REMOTE_CLI._gate_job_folder_pin(job_dir / "runner.ipynb")
        self.assertTrue(str(caught.exception).startswith("CODE_BUNDLE_MISMATCH"))

    def test_submit_gate_without_a_bundle_still_asks_the_remote(self) -> None:
        target, commit = _init_target(self.root)
        with unittest.mock.patch.object(JOBFOLDER, "_verify_commit_reachable",
                                        return_value=None):
            job_dir = _generate(target, commit=commit)
        _git(target, "add", "-A")
        _git(target, "commit", "-q", "-m", "job folder")
        with self.assertRaises(JOBFOLDER.JobFolderError):
            REMOTE_CLI._gate_job_folder_pin(job_dir / "runner.ipynb")
        self.probe.assert_called_once()


def _write_notebook_copying_driver(driver_dir: Path, record_dir: Path) -> Path:
    """A `kaggle_driver.py` stand-in: copies the staged notebook and metadata
    it was handed, prints success, never reaches a socket."""
    driver_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)
    script = driver_dir / "fake_driver.py"
    script.write_text(
        "import json, shutil, sys\n"
        "from pathlib import Path\n"
        f"RECORD = Path({str(record_dir)!r})\n"
        "staging = Path(sys.argv[2])\n"
        "meta = json.loads((staging / 'kernel-metadata.json').read_text())\n"
        "shutil.copy(staging / meta['code_file'], RECORD / 'pushed.ipynb')\n"
        "shutil.copy(staging / 'kernel-metadata.json', RECORD / 'kernel-metadata.json')\n"
        "print(json.dumps({'ok': True, 'ref': meta['id'], 'url': 'https://example.invalid/',"
        " 'versionNumber': 1}))\n",
        encoding="utf-8",
    )
    return script


class KagglePushCodeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.record = self.root / "record"
        driver = _write_notebook_copying_driver(self.root / "driver", self.record)
        token = self.root / "creds" / "token"
        token.parent.mkdir()
        token.write_text(SECRET + "\n", encoding="utf-8")
        self.adapter = KAGGLE.KaggleAdapter(
            credentials={"w1": KAGGLE.CredentialHandle(worker_id="w1", token_path=token)},
            driver_script=driver,
            team_registry=self.root / "no-team.json",
        )

    def _job(self, *, bundle: bool) -> Path:
        target, commit = _init_target(self.root)
        with unittest.mock.patch.object(JOBFOLDER, "_verify_commit_reachable",
                                        return_value=None):
            return _generate(target, service="kaggle", commit=commit, code_bundle=bundle)

    def _push(self, job_dir: Path) -> dict:
        self.adapter.submit(ADAPTER.Job(
            entrypoint=job_dir / "runner.ipynb", run_config={"mode": "smoke"}, worker="w1"))
        return json.loads((self.record / "pushed.ipynb").read_text(encoding="utf-8"))

    def _run_cells(self, notebook: dict, cwd: Path, upto: int) -> None:
        previous = Path.cwd()
        os.chdir(cwd)
        try:
            for cell in notebook["cells"][:upto]:
                exec(compile("".join(cell["source"]), "<cell>", "exec"), {})
        finally:
            os.chdir(previous)

    def test_the_pushed_notebook_carries_the_bundle_ahead_of_the_bootstrap_cell(self) -> None:
        job_dir = self._job(bundle=True)
        bundle = (job_dir / "code-bundle.tar.gz").read_bytes()
        runner = json.loads((job_dir / "runner.ipynb").read_text(encoding="utf-8"))

        pushed = self._push(job_dir)

        # Two staged cells (bundle, run-config), then the runner's own two
        # cells byte for byte.
        self.assertEqual(len(pushed["cells"]), 4)
        self.assertEqual(pushed["cells"][2:], runner["cells"])
        kernel_cwd = self.root / "kernel"
        kernel_cwd.mkdir()
        self._run_cells(pushed, kernel_cwd, upto=2)
        self.assertEqual((kernel_cwd / "code-bundle.tar.gz").read_bytes(), bundle)
        staged_config = json.loads((kernel_cwd / "run-config.json").read_text())
        self.assertEqual(staged_config["codeBundle"]["sha256"],
                         hashlib.sha256(bundle).hexdigest())
        self.assertEqual(staged_config["mode"], "smoke")
        pushed_text = (self.record / "pushed.ipynb").read_text(encoding="utf-8")
        self.assertNotIn(SECRET, pushed_text)
        self.assertNotIn(SECRET, (self.record / "kernel-metadata.json").read_text())
        # The job folder's own versioned runner is never edited.
        self.assertEqual(
            json.loads((job_dir / "runner.ipynb").read_text(encoding="utf-8")), runner)

    def test_without_a_bundle_the_pushed_notebook_is_exactly_as_before(self) -> None:
        job_dir = self._job(bundle=False)
        runner = json.loads((job_dir / "runner.ipynb").read_text(encoding="utf-8"))
        pushed = self._push(job_dir)
        self.assertEqual(len(pushed["cells"]), 3)
        self.assertEqual(pushed["cells"][1:], runner["cells"])
        self.assertNotIn("code-bundle", "".join(pushed["cells"][0]["source"]))

    def test_a_declared_bundle_whose_file_is_missing_refuses_the_push(self) -> None:
        job_dir = self._job(bundle=True)
        (job_dir / "code-bundle.tar.gz").unlink()
        with self.assertRaises(ADAPTER.AdapterError):
            self.adapter.submit(ADAPTER.Job(
                entrypoint=job_dir / "runner.ipynb", run_config={}, worker="w1"))
        self.assertFalse((self.record / "pushed.ipynb").exists())

    def test_the_adapter_declares_the_capability_and_the_abc_stays_at_six(self) -> None:
        self.assertIsInstance(KAGGLE.KaggleAdapter.CODE_BUNDLE_MAX_BYTES, int)
        self.assertIsNone(ADAPTER.Adapter.CODE_BUNDLE_MAX_BYTES)
        self.assertEqual(len(ADAPTER.Adapter.__abstractmethods__), 6)


def _tar_gz(entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for info, data in entries:
            if data is not None:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            else:
                archive.addfile(info)
    return buffer.getvalue()


def _file(name: str, data: bytes = b"x = 1\n") -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.type = tarfile.REGTYPE
    return info, data


class RunnerUnpackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name) / "work"
        self.base.mkdir()

    def _stage(self, bundle: bytes, *, sha: str | None = None,
               clone_paths=("src/fixturepkg",)) -> dict:
        (self.base / "code-bundle.tar.gz").write_bytes(bundle)
        return {
            "schemaVersion": 1, "commit": "a" * 40,
            "repo": {"url": "https://example.invalid/private.git", "ref": "main"},
            "clonePaths": list(clone_paths),
            "run": {"module": "fixturepkg", "function": "run"},
            "codeBundle": {
                "file": "code-bundle.tar.gz", "format": "tar.gz",
                "sha256": sha or hashlib.sha256(bundle).hexdigest(),
                "bytes": len(bundle),
            },
        }

    def _unpack(self, run_config: dict) -> Path:
        return RUNNER_BOOTSTRAP.unpack_code_bundle(
            run_config, self.base, self.base / "clone")

    def test_a_valid_bundle_unpacks_into_the_clone_without_git(self) -> None:
        bundle = _tar_gz([_file("src/fixturepkg/__init__.py", b"VALUE = 7\n")])
        run_config = self._stage(bundle)
        with unittest.mock.patch.object(
            RUNNER_BOOTSTRAP, "_run_git", side_effect=AssertionError("no git")
        ):
            clone = self._unpack(run_config)
        self.assertEqual(clone, self.base / "clone")
        self.assertEqual(
            (clone / "src" / "fixturepkg" / "__init__.py").read_bytes(), b"VALUE = 7\n")

    def test_a_sha_mismatch_refuses_before_anything_is_unpacked(self) -> None:
        bundle = _tar_gz([_file("src/fixturepkg/__init__.py")])
        run_config = self._stage(bundle, sha="0" * 64)
        with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError) as caught:
            self._unpack(run_config)
        self.assertIn("CODE_BUNDLE_MISMATCH", str(caught.exception))
        self.assertFalse((self.base / "clone" / "src").exists())

    def test_a_missing_bundle_file_refuses(self) -> None:
        run_config = self._stage(_tar_gz([_file("src/fixturepkg/a.py")]))
        (self.base / "code-bundle.tar.gz").unlink()
        with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
            self._unpack(run_config)

    def test_a_bundle_file_name_that_is_a_path_refuses(self) -> None:
        run_config = self._stage(_tar_gz([_file("src/fixturepkg/a.py")]))
        run_config["codeBundle"]["file"] = "../code-bundle.tar.gz"
        with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError):
            self._unpack(run_config)

    def _assert_refused_and_nothing_escaped(self, entries) -> None:
        run_config = self._stage(_tar_gz(entries))
        before = sorted(str(p) for p in Path(self._tmp.name).rglob("*"))
        with self.assertRaises(RUNNER_BOOTSTRAP.BootstrapError) as caught:
            self._unpack(run_config)
        self.assertIn("CODE_BUNDLE_UNSAFE_ENTRY", str(caught.exception))
        after = sorted(str(p) for p in Path(self._tmp.name).rglob("*")
                       if "clone" not in p.relative_to(self._tmp.name).parts)
        self.assertEqual(
            [p for p in after if "clone" not in p], [p for p in before if "clone" not in p])
        self.assertFalse((self.base / "clone" / "src").exists())

    def test_an_entry_with_dotdot_refuses(self) -> None:
        self._assert_refused_and_nothing_escaped(
            [_file("src/fixturepkg/ok.py"), _file("src/fixturepkg/../../../escape.py")])

    def test_an_absolute_entry_refuses(self) -> None:
        self._assert_refused_and_nothing_escaped(
            [_file(str(Path(self._tmp.name) / "abs-escape.py"))])

    def test_a_symlink_entry_refuses(self) -> None:
        link = tarfile.TarInfo("src/fixturepkg/link.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        self._assert_refused_and_nothing_escaped([(link, None)])

    def test_a_hardlink_entry_refuses(self) -> None:
        link = tarfile.TarInfo("src/fixturepkg/hard.py")
        link.type = tarfile.LNKTYPE
        link.linkname = "src/fixturepkg/ok.py"
        self._assert_refused_and_nothing_escaped([_file("src/fixturepkg/ok.py"), (link, None)])

    def test_a_device_entry_refuses(self) -> None:
        fifo = tarfile.TarInfo("src/fixturepkg/pipe")
        fifo.type = tarfile.FIFOTYPE
        self._assert_refused_and_nothing_escaped([(fifo, None)])

    def test_an_entry_outside_the_declared_clone_paths_refuses(self) -> None:
        self._assert_refused_and_nothing_escaped([_file("elsewhere/secret.py")])

    def test_bootstrap_unpacks_instead_of_cloning_and_records_the_pinned_commit(self) -> None:
        bundle = _tar_gz([_file("src/fixturepkg/__init__.py", b"def run():\n    return 1\n")])
        run_config = self._stage(bundle)
        run_config.update(product="P", service="s", jobName="j",
                          runnerTemplate=[{"path": "x", "sha256": "y"}])
        (self.base / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        fake_torch = SimpleNamespace(
            __version__="1.2.3",
            cuda=SimpleNamespace(is_available=lambda: False, get_device_name=lambda i: "n/a"),
        )
        saved_path = list(sys.path)
        try:
            with unittest.mock.patch.object(
                RUNNER_BOOTSTRAP, "_run_git", side_effect=AssertionError("no git")
            ):
                result = RUNNER_BOOTSTRAP.bootstrap(
                    self.base, hardware_import=lambda name: fake_torch)
        finally:
            sys.path[:] = saved_path
            sys.modules.pop("fixturepkg", None)
        self.assertEqual(result["commit"], "a" * 40)
        written = json.loads((self.base / "bootstrap.json").read_text(encoding="utf-8"))
        self.assertEqual(written["commit"], "a" * 40)

    def test_bootstrap_without_a_bundle_still_clones(self) -> None:
        run_config = {
            "schemaVersion": 1, "commit": "a" * 40,
            "repo": {"url": "https://example.invalid/r.git", "ref": "main"},
            "clonePaths": ["src/fixturepkg"], "run": {"module": "fixturepkg"},
        }
        (self.base / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        with unittest.mock.patch.object(
            RUNNER_BOOTSTRAP, "clone_repo",
            side_effect=RUNNER_BOOTSTRAP.BootstrapError("clone attempted"),
        ) as clone, unittest.mock.patch.object(
            RUNNER_BOOTSTRAP, "unpack_code_bundle",
            side_effect=AssertionError("no bundle declared"),
        ):
            with self.assertRaises(SystemExit) as caught:
                RUNNER_BOOTSTRAP.bootstrap(self.base)
        clone.assert_called_once()
        self.assertIn("clone attempted", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
