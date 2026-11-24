"""One dependency specification, locked (issue #58).

`env/environment.yml` (with `env/torch-*.yml`) is the source; `env/*.conda-lock.yml`
are the locks conda-lock solved from it; `scripts/lock-env.py check` fails when a
source changed without a refresh, and when `requirements.txt` is not the file
`scripts/lock-env.py requirements` writes from the sources. `scripts/setup_env.py
install` builds the environment from the lock of its torch kind, and solves the
sources live, with a warning, only on a platform no lock covers. Every micromamba
and pip call is recorded by a stand-in, so nothing is installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
LOCK_ENV = REPO / "scripts" / "lock-env.py"
SETUP_ENV = REPO / "scripts" / "setup_env.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lock_env = _load(LOCK_ENV, "lock_env_under_test")
setup_env = _load(SETUP_ENV, "setup_env_locks_under_test")


def lock_env_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LOCK_ENV), *args], capture_output=True, text=True,
                          timeout=120)


class LockFreshnessTests(unittest.TestCase):
    def copy_of_the_sources(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="papersmith-locks-"))
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copytree(REPO / "env", root / "env")
        shutil.copyfile(REPO / "requirements.txt", root / "requirements.txt")
        return root

    def test_the_repository_locks_and_requirements_are_current(self) -> None:
        done = lock_env_cli("check")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("locks: current", done.stdout)

    def test_a_copy_of_the_sources_is_current(self) -> None:
        done = lock_env_cli("check", "--root", str(self.copy_of_the_sources()))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_editing_a_source_without_a_refresh_fails_the_check(self) -> None:
        root = self.copy_of_the_sources()
        source = root / "env" / "environment.yml"
        source.write_text(source.read_text(encoding="utf-8") + "  - tqdm\n", encoding="utf-8")
        done = lock_env_cli("check", "--root", str(root))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        for variant in ("cpu", "cuda", "rocm"):
            self.assertIn(f"--variant {variant}", done.stdout)

    def test_editing_a_torch_source_fails_only_its_variant(self) -> None:
        root = self.copy_of_the_sources()
        torch = root / "env" / "torch-cuda.yml"
        torch.write_text(torch.read_text(encoding="utf-8") + "  - torchaudio\n", encoding="utf-8")
        done = lock_env_cli("check", "--root", str(root))
        self.assertEqual(done.returncode, 1)
        self.assertIn("--variant cuda", done.stdout)
        self.assertNotIn("--variant cpu", done.stdout)

    def test_a_hand_edited_requirements_file_fails_the_check(self) -> None:
        root = self.copy_of_the_sources()
        requirements = root / "requirements.txt"
        requirements.write_text(requirements.read_text(encoding="utf-8") + "tqdm\n", encoding="utf-8")
        done = lock_env_cli("check", "--root", str(root))
        self.assertEqual(done.returncode, 1)
        self.assertIn("requirements.txt", done.stdout)
        self.assertIn("lock-env.py requirements", done.stdout)

    def test_each_lock_lists_the_platforms_locks_json_records(self) -> None:
        record = json.loads((REPO / "env" / "locks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(record["variants"]), {"cpu", "cuda", "rocm"})
        for variant, entry in record["variants"].items():
            with self.subTest(variant=variant):
                lock = REPO / "env" / entry["lockfile"]
                self.assertEqual(lock.name, f"{variant}.conda-lock.yml")
                self.assertEqual(lock_env.lock_platforms(lock), entry["platforms"])
                self.assertEqual(entry["platforms"], list(lock_env.VARIANTS[variant][1]))

    def test_the_requirements_verb_writes_the_committed_requirements_file(self) -> None:
        root = self.copy_of_the_sources()
        (root / "requirements.txt").unlink()
        done = lock_env_cli("requirements", "--root", str(root))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((root / "requirements.txt").read_text(encoding="utf-8"),
                         (REPO / "requirements.txt").read_text(encoding="utf-8"))

    def test_requirements_carries_the_sources_with_pip_names_and_bounds(self) -> None:
        text = (REPO / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("generated", text.splitlines()[0].lower())
        names = [line.split("#")[0].strip() for line in text.splitlines()]
        names = [line for line in names if line]
        for spec in ("torch", "torchvision", "Pillow>=10.0", "PyYAML>=6.0", "build",
                     "kagglesdk==0.1.37", "pytest-xdist>=3.5", "docling==2.141.0"):
            self.assertIn(spec, names)
        for dropped in ("python=3.12", "pip", "llama.cpp", "pytorch-cpu", "pillow>=10.0"):
            self.assertNotIn(dropped, names)


class PipRequirementTests(unittest.TestCase):
    def test_conda_constraints_become_valid_pip_requirements(self) -> None:
        from papersmith.core import manifest

        self.assertEqual(manifest.pip_requirement("pyyaml", ">=6.0"), "PyYAML>=6.0")
        self.assertEqual(manifest.pip_requirement("kagglesdk", "==0.1.37"), "kagglesdk==0.1.37")
        # conda's single `=` means "this version or any build of it"; pip spells it `==X.*`.
        self.assertEqual(manifest.pip_requirement("numpy", "=1.26"), "numpy==1.26.*")
        self.assertEqual(manifest.pip_requirement("numpy", "=1.26.*"), "numpy==1.26.*")
        self.assertIsNone(manifest.pip_requirement("llama.cpp", ""))


class LockedInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="env-locks-root-")
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)

    def install(self, *, kind: str = "cpu", asset: str = "linux-64", exists: bool = False,
                no_ingestion: bool = False, fail=lambda call: False):
        calls: list[list[str]] = []

        def run(_mm, a, _env):
            calls.append(list(a))
            if fail(a):
                raise subprocess.CalledProcessError(1, ["micromamba", *a])

        args = argparse.Namespace(cpu=kind == "cpu", cuda=kind == "cuda", rocm=kind == "rocm",
                                  no_ingestion=no_ingestion, name="papersmith")
        gpu = {"vendor": "amd", "gfx_targets": ["gfx1150"]} if kind == "rocm" else \
            {"vendor": "none", "gfx_targets": []}
        out = io.StringIO()
        with mock.patch.object(setup_env, "find_micromamba", return_value=Path("/mm")), \
                mock.patch.object(setup_env, "MAMBA_ROOT", self.root), \
                mock.patch.object(setup_env, "run", side_effect=run), \
                mock.patch.object(setup_env, "env_exists", return_value=exists), \
                mock.patch.object(setup_env, "detect_cuda", return_value=False), \
                mock.patch.object(setup_env, "gpu_facts", return_value=gpu), \
                mock.patch.object(setup_env, "platform_asset", return_value=asset), \
                redirect_stdout(out):
            self.assertEqual(setup_env.cmd_install(args), 0)
        return calls, out.getvalue()

    def conda(self, calls):
        return [c for c in calls if c[0] in ("create", "install", "remove")]

    def test_a_new_env_builds_from_its_lock_and_records_which(self) -> None:
        for kind in ("cpu", "cuda", "rocm"):
            with self.subTest(kind=kind):
                calls, out = self.install(kind=kind)
                lock = str(REPO / "env" / f"{kind}.conda-lock.yml")
                self.assertEqual(self.conda(calls), [["create", "-y", "-n", "papersmith", "-f", lock,
                                                      "--category", "main"]])
                self.assertNotIn("not locked", out)
                stamp = json.loads((self.root / "envs" / "papersmith" / setup_env.STAMP).read_text())
                self.assertEqual(stamp["kind"], kind)

    def test_an_env_that_already_matches_its_lock_is_not_rebuilt(self) -> None:
        self.install(kind="cpu")
        calls, out = self.install(kind="cpu", exists=True)
        self.assertEqual(self.conda(calls), [])
        self.assertIn("already matches", out)
        self.assertTrue([c for c in calls if "-r" in c], "the pip layers still run")

    def test_an_existing_env_is_rebuilt_only_after_every_package_is_downloaded(self) -> None:
        """`create -y` over an env wipes it first, so the packages are fetched into a
        throwaway prefix before; a failed download leaves the working env untouched."""
        self.install(kind="cpu")
        lock = str(REPO / "env" / "rocm.conda-lock.yml")
        calls, out = self.install(kind="rocm", exists=True)
        staging = str(self.root / "envs" / ".papersmith-download")
        self.assertEqual(self.conda(calls), [
            ["create", "-y", "--download-only", "-p", staging, "-f", lock, "--category", "main"],
            ["create", "-y", "-n", "papersmith", "-f", lock, "--category", "main"]])
        self.assertIn("rebuilding", out)
        with self.assertRaises(subprocess.CalledProcessError):
            self.install(kind="cpu", exists=True, fail=lambda a: "--download-only" in a)
        self.assertEqual(json.loads((self.root / "envs" / "papersmith" / setup_env.STAMP)
                                    .read_text())["kind"], "rocm", "the failed rebuild changed nothing")

    def test_an_unlocked_platform_solves_the_sources_live_with_a_warning(self) -> None:
        cases = (("cpu", "linux-aarch64", "torch-cpu.yml"), ("cpu", "win-arm64", "torch-cpu.yml"),
                 ("cuda", "osx-arm64", "torch-cuda.yml"))
        for kind, asset, torch in cases:
            with self.subTest(kind=kind, asset=asset):
                calls, out = self.install(kind=kind, asset=asset)
                [conda] = [c for c in calls if c[0] in ("create", "install")]
                self.assertEqual(conda, ["create", "-y", "-n", "papersmith",
                                         "-f", str(REPO / "env" / "environment.yml"),
                                         "-f", str(REPO / "env" / torch)])
                self.assertIn(f"WARNING: {asset} is not locked", out)
                self.assertNotIn("--category", conda)

    def test_a_locked_platform_of_another_variant_is_used(self) -> None:
        calls, out = self.install(kind="cpu", asset="osx-arm64")
        self.assertIn(str(REPO / "env" / "cpu.conda-lock.yml"), calls[0])
        self.assertNotIn("not locked", out)

    def test_ingestion_installs_from_its_requirements_file_after_torch(self) -> None:
        ingestion = str(REPO / "env" / "ingestion.txt")
        for kind in ("cpu", "rocm"):
            with self.subTest(kind=kind):
                calls, _ = self.install(kind=kind)
                pip = [c for c in calls if "pip" in c and "-r" in c]
                self.assertEqual(len(pip), 1, calls)
                self.assertEqual(pip[0][-2:], ["-r", ingestion])
                torch = [i for i, c in enumerate(calls)
                         if c[0] == "create" or any(a.startswith("torch[") for a in c)]
                self.assertLess(max(torch), calls.index(pip[0]))

    def test_no_ingestion_skips_exactly_the_ingestion_layer(self) -> None:
        calls, _ = self.install(no_ingestion=True)
        self.assertFalse([c for c in calls if "-r" in c], calls)
        self.assertEqual(calls[0][0], "create")


if __name__ == "__main__":
    unittest.main()
