"""`scripts/setup_env.py install` picks the PyTorch build for the GPU it finds.

NVIDIA keeps conda-forge's CUDA build (the cuda lock); an AMD GPU whose gfx
target is in the probe's ROCm set gets the rocm lock (no torch) and AMD's ROCm
wheels (pip) on top instead of the CPU build; `--rocm` forces them, `--cpu` forbids them. Every micromamba and
pip call is recorded by a stand-in, so nothing is installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "setup_env.py"
SPEC = importlib.util.spec_from_file_location("setup_env_gpu_under_test", SCRIPT)
assert SPEC and SPEC.loader
setup_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_env)


def facts(vendor: str = "amd", targets: tuple[str, ...] = ("gfx1150",)) -> dict:
    return {"vendor": vendor, "gfx_targets": list(targets), "platform": {"system": "Linux", "machine": "x86_64"}}


class TorchChoiceInstallTests(unittest.TestCase):
    def _install(self, *, cpu=False, cuda=False, rocm=False, gpu=None, nvidia=False, exists=False):
        calls: list[list[str]] = []
        args = argparse.Namespace(cpu=cpu, cuda=cuda, rocm=rocm, no_ingestion=False, name="papersmith")
        out = io.StringIO()
        with mock.patch.object(setup_env, "find_micromamba", return_value=Path("/mm")), \
                mock.patch.object(setup_env, "run", side_effect=lambda _mm, a, _env: calls.append(list(a))), \
                mock.patch.object(setup_env, "env_exists", return_value=exists), \
                mock.patch.object(setup_env, "detect_cuda", return_value=nvidia), \
                mock.patch.object(setup_env, "gpu_facts", return_value=gpu or facts("none", ())), \
                mock.patch.object(setup_env, "platform_asset", return_value="linux-64"), \
                redirect_stdout(out):
            self.assertEqual(setup_env.cmd_install(args), 0)
        return calls, out.getvalue()

    @staticmethod
    def _lock(calls) -> str:
        """The lock the environment was created from."""
        conda = calls[0]
        assert conda[0] == "create", conda
        return Path(conda[conda.index("-f") + 1]).name

    @staticmethod
    def _rocm_pip(calls):
        return [c for c in calls if "pip" in c and any(a.startswith("torch[device-") for a in c)]

    def test_a_supported_amd_gpu_gets_the_rocm_wheels_and_no_conda_torch(self) -> None:
        calls, out = self._install(gpu=facts())
        self.assertEqual(self._lock(calls), "rocm.conda-lock.yml")
        self.assertNotIn("pytorch", (REPO / "env" / "rocm.conda-lock.yml").read_text(encoding="utf-8"))
        [rocm] = self._rocm_pip(calls)
        self.assertIn("torch[device-gfx1150]==2.14.0+rocm10.1.0", rocm)
        self.assertIn("torchvision[device-gfx1150]==0.29.0a0+rocm10.1.0", rocm)
        self.assertIn("https://stable.repo.amd.com/rocm/whl-next/", rocm)
        docling = next(i for i, c in enumerate(calls) if any(a.endswith("ingestion.txt") for a in c))
        self.assertLess(calls.index(rocm), docling, "ROCm torch goes in before docling resolves torch")
        self.assertIn("torch=ROCm", out)
        self.assertIn("gfx1150", out)

    def test_nvidia_keeps_conda_forge_cuda(self) -> None:
        calls, out = self._install(nvidia=True, gpu=facts("nvidia", ()))
        self.assertEqual(self._lock(calls), "cuda.conda-lock.yml")
        self.assertEqual(self._rocm_pip(calls), [])
        self.assertIn("torch=CUDA (GPU)", out)

    def test_cpu_forbids_rocm_on_a_supported_gpu(self) -> None:
        calls, out = self._install(cpu=True, gpu=facts())
        self.assertEqual(self._lock(calls), "cpu.conda-lock.yml")
        self.assertEqual(self._rocm_pip(calls), [])
        self.assertIn("torch=CPU", out)

    def test_an_unsupported_target_stays_on_cpu_unless_rocm_forces_it(self) -> None:
        calls, out = self._install(gpu=facts(targets=("gfx1036",)))
        self.assertEqual(self._lock(calls), "cpu.conda-lock.yml")
        self.assertIn("gfx1036", out)
        self.assertIn("--rocm", out)
        forced, _ = self._install(rocm=True, gpu=facts(targets=("gfx1036",)))
        [rocm] = self._rocm_pip(forced)
        self.assertIn("torch[device-gfx1036]==2.14.0+rocm10.1.0", rocm)

    def test_an_existing_env_is_rebuilt_from_the_rocm_lock_before_the_wheels(self) -> None:
        # `create -y` replaces the environment, so a conda torch an earlier
        # build left cannot sit under the ROCm wheels (`install` would keep it).
        calls, out = self._install(gpu=facts(), exists=True)
        self.assertEqual(calls[0][:2], ["create", "-y"])
        self.assertEqual(self._lock(calls), "rocm.conda-lock.yml")
        self.assertFalse([c for c in calls if c[:1] in (["remove"], ["install"])], calls)
        self.assertLess(0, calls.index(self._rocm_pip(calls)[0]))
        self.assertIn("rebuilding the existing environment", out)

    def test_conflicting_flags_and_rocm_without_an_amd_gpu_refuse(self) -> None:
        with self.assertRaises(SystemExit):
            self._install(rocm=True, cpu=True, gpu=facts())
        with self.assertRaises(SystemExit):
            self._install(rocm=True, cuda=True, gpu=facts())
        with self.assertRaises(SystemExit):
            self._install(rocm=True, gpu=facts("none", ()))

    def test_the_parser_accepts_rocm(self) -> None:
        with mock.patch("sys.argv", ["setup_env.py", "install", "--rocm"]), \
                mock.patch.object(setup_env, "cmd_install", side_effect=lambda a: 0 if a.rocm else 1):
            self.assertEqual(setup_env.main(), 0)


class GpuFactsTests(unittest.TestCase):
    def test_facts_come_from_the_kit_probe_and_fail_closed_without_it(self) -> None:
        self.assertIn("vendor", setup_env.gpu_facts())
        with mock.patch.object(setup_env, "PROJECT_ROOT", Path("/nonexistent-kit")):
            self.assertEqual(setup_env.gpu_facts()["vendor"], "none")


if __name__ == "__main__":
    unittest.main()
