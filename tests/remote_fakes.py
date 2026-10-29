"""Shared fakes for the remote-preflight tests: the in-process test backends
(registered once, under one module name), the throwaway git target with a
smoke module, and `PreflightCase`. Imported as `tests.remote_fakes` by every
test module that needs them, so no test module imports another and no fake
backend is registered twice.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/remote-execution/scripts"


def _load_or_reuse(module_name: str, script: Path):
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
REMOTE_CLI = _load_or_reuse("remote_execution_cli", SCRIPTS / "remote_cli.py")
JOBFOLDER = sys.modules["remote_execution_jobfolder"]

SERVICE = "preflight-carrier"
PLAIN = "preflight-plain"


class _Calls:
    submitted: list = []


class _PreflightBackend(ADAPTER.Adapter):
    """A kernel-style test backend: carries code bundles and input
    datasets, declares a session limit and every preflight hook."""

    CODE_BUNDLE_MAX_BYTES = 1_000_000
    INPUT_DATASETS_ROOT = "/inputs"
    interpreter = {"ok": True, "evidence": "the driver imports under this interpreter"}
    accounts = {"w1": {"ok": True, "evidence": "w1 authenticates"}}
    accelerator = {"name": "GPU-X", "architectures": ["sm_75"], "problem": None}

    @classmethod
    def session_limit_seconds(cls, machine_shape=None):
        return 2 * 3600

    def workers(self):
        return [ADAPTER.Worker(id=w, capacity=1) for w in sorted(self.accounts)]

    def submit(self, job):  # pragma: no cover - preflight must never call it
        _Calls.submitted.append(job)
        raise AssertionError("preflight submitted a job")

    def poll(self, submission_id):
        raise AssertionError("preflight polled")

    def fetch(self, submission_id, into):
        raise AssertionError("preflight fetched")

    def cancel(self, submission_id):
        raise AssertionError("preflight cancelled")

    def list_active(self, worker):
        return []

    def interpreter_check(self):
        return dict(self.interpreter)

    def account_check(self, worker):
        return dict(self.accounts.get(worker) or {"ok": False, "evidence": f"{worker} unknown",
                                                  "fix": "register it"})

    def accelerator_request(self, run_config):
        return dict(self.accelerator)


class _PlainBackend(_PreflightBackend):
    """No code bundle, no input attachment, no repo credential."""

    CODE_BUNDLE_MAX_BYTES = None
    INPUT_DATASETS_ROOT = None


for _name, _cls in ((SERVICE, _PreflightBackend), (PLAIN, _PlainBackend)):
    ADAPTER.register(_name, _cls)
    ADAPTER.register_metadata(_name, lambda rc: ("fake-metadata.json", json.dumps({"ok": True})))
    ADAPTER.register_default_accelerator(_name, lambda: ("cuda", ("sm_75",)))


MODULE_SOURCE = '''\
import json
import os
import subprocess
import time
from pathlib import Path


def run(**kwargs):
    return 1


def _commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"],
                             cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True)
    except OSError:
        out = None
    if out is not None and out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    return os.environ.get("FORGE_CLONE_COMMIT")


def smoke_stamps(**kwargs):
    evidence = {"commit": _commit()}
    if os.environ.get("FORGE_RUN_MODE") == "smoke":
        evidence["mode"] = "smoke"
    Path("shard.json").write_text(json.dumps({
        "evidence": evidence,
        "seen": {"cwd": os.getcwd(), "kwargs": kwargs,
                 "cloneRoot": os.environ.get("FORGE_CLONE_ROOT"),
                 "inputs": os.environ.get("FORGE_INPUT_DATASETS")},
    }), encoding="utf-8")
    return evidence


def smoke_silent(**kwargs):
    return 1


def smoke_sleeps(**kwargs):
    time.sleep(float(kwargs.get("seconds", 30)))
'''


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "preflight-tests"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "preflight@example.invalid"
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                          text=True, check=True).stdout.strip()


def _unreachable(*args, **kwargs):
    raise JOBFOLDER.JobFolderError("the declared remote could not serve the pin (private)")


class PreflightCase(unittest.TestCase):
    def setUp(self) -> None:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.root = Path(box.name)
        self.target = self.root / "repo"
        (self.target / "src" / "pkg").mkdir(parents=True)
        (self.target / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (self.target / "src" / "pkg" / "mod.py").write_text(MODULE_SOURCE, encoding="utf-8")
        (self.target / "P").mkdir()
        (self.target / "P" / "README.md").write_text("product\n", encoding="utf-8")
        _git(self.target, "init", "-q")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "initial")
        self.commit = _git(self.target, "rev-parse", "HEAD")
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        # Generation's reachability probe is private by default here.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable)
        self.probe = patcher.start()
        self.addCleanup(patcher.stop)
        _Calls.submitted = []
        for cls in (_PreflightBackend, _PlainBackend):
            self.addCleanup(setattr, cls, "accounts", dict(cls.accounts))
            self.addCleanup(setattr, cls, "interpreter", dict(cls.interpreter))
            self.addCleanup(setattr, cls, "accelerator", dict(cls.accelerator))

    def generate(self, *, service: str = SERVICE, smoke: str = "smoke_stamps",
                 code_bundle: bool = True, required=("evidence.commit",), **extra) -> Path:
        kwargs = dict(
            target=self.target, service=service, job_name="job-a", product="P",
            commit=self.commit, repo_url="https://example.invalid/private.git",
            repo_ref="main", clone_paths=["src/pkg"], run_module="pkg.mod",
            run_function="run", smoke_module="pkg.mod", smoke_function=smoke,
            smoke_required_evidence=list(required) or None, code_bundle=code_bundle,
        )
        kwargs.update(extra)
        return JOBFOLDER.generate_job(**kwargs)

    def preflight(self, job_dir: Path, *extra: str, interpreter: bool = True) -> tuple[int, dict, str]:
        argv = ["preflight", "--target", str(self.target),
                "--entrypoint", str(job_dir / "runner.ipynb"),
                "--workspace", str(self.workspace)]
        if interpreter:
            argv += ["--interpreter", sys.executable]
        argv += list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = REMOTE_CLI.main(argv)
        payload = json.loads(out.getvalue()) if out.getvalue().strip() else {}
        return code, payload, err.getvalue()

    @staticmethod
    def rows(payload: dict, check: str) -> list[dict]:
        return [row for row in payload["checks"] if row["check"] == check]

    def row(self, payload: dict, check: str) -> dict:
        found = self.rows(payload, check)
        self.assertEqual(len(found), 1, (check, payload))
        return found[0]


FAKE_ACCOUNTS = r'''import json, sys
args = sys.argv[1:]
LOG = {log!r}
with open(LOG, "a") as handle:
    handle.write(json.dumps(args) + "\n")
if args[:1] == ["list"]:
    print(json.dumps({{"accounts": [{{"username": "acct-a"}}, {{"username": "acct-b"}}]}}))
elif args[:1] == ["validate"]:
    name = args[args.index("--account") + 1]
    ok = name == "acct-a"
    print(json.dumps({{"accounts": [{{"username": name, "ok": ok,
                                      "detail": "ok" if ok else "rejected (HTTP 401)"}}]}}))
    sys.exit(0 if ok else 1)
'''

KAGGLE = _load_or_reuse("remote_execution_kaggle_adapter", SCRIPTS / "adapters" / "kaggle.py")
COLAB = _load_or_reuse("remote_execution_colab_adapter", SCRIPTS / "adapters" / "colab.py")
