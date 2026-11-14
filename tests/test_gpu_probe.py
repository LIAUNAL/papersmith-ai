"""`skills/_core/gpu/gpu_probe.py` and `smith gpu`: what GPU this machine has,
whether this process can reach it, and the exact command for every blocker.

Every probe reads a fake system root (sysfs, /dev and /etc/group laid out in a
temporary directory), a fake `llama-server` and a fake interpreter, so the
suite measures the rules and never the machine it runs on.
"""

from __future__ import annotations

import getpass
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "_core" / "gpu" / "gpu_probe.py"
SPEC = importlib.util.spec_from_file_location("gpu_probe_under_test", SCRIPT)
assert SPEC and SPEC.loader
GPU = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GPU
SPEC.loader.exec_module(GPU)

USER = getpass.getuser()
#: A gid no test process belongs to, so the fake render group is never "in session".
FOREIGN_GID = 64999


def _write(path: Path, text: str, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)  # a node left at mode 000 cannot be rewritten
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return path


def fake_root(base: Path, *, vendor: str = "0x1002", gfx: int | None = 110500,
              devices_rw: bool = False, listed: bool = True, kfd: bool = True) -> Path:
    """A system root shaped like this machine: one AMD card, a KFD node, the
    device nodes, and a render group that lists (or not) the current user."""
    root = base / "sysroot"
    card = root / "sys" / "class" / "drm" / "card0" / "device"
    _write(card / "vendor", f"{vendor}\n")
    _write(card / "mem_info_vram_total", "34359738368\n")
    _write(card / "mem_info_gtt_total", "16635277312\n")
    # A connector entry has no vendor file; the probe must skip it.
    (root / "sys" / "class" / "drm" / "card0-DP-1").mkdir(parents=True, exist_ok=True)
    if gfx is not None:
        nodes = root / "sys" / "class" / "kfd" / "kfd" / "topology" / "nodes"
        _write(nodes / "0" / "properties", "cpu_cores_count 24\ngfx_target_version 0\n")
        _write(nodes / "1" / "properties", f"simd_count 32\ngfx_target_version {gfx}\n")
    mode = 0o600 if devices_rw else 0o000
    if kfd:
        _write(root / "dev" / "kfd", "", mode)
    _write(root / "dev" / "dri" / "renderD128", "", mode)
    _write(root / "dev" / "dri" / "card0", "", 0o000)  # not a render node: never checked
    members = USER if listed else "someone"
    _write(root / "etc" / "group", f"video:x:44:{members}\nrender:x:{FOREIGN_GID}:{members}\n")
    return root


def fake_llama(base: Path, lines: list[str]) -> Path:
    body = "\n".join(lines)
    return _write(base / "bin" / "llama-server",
                  "#!/bin/sh\ncat <<'EOF'\nAvailable devices:\n" + body + "\nEOF\n", 0o755)


def fake_python(base: Path, payload: dict) -> Path:
    return _write(base / "bin" / "python-fake",
                  "#!/bin/sh\necho 'noise before the payload'\necho '" + json.dumps(payload) + "'\n", 0o755)


@unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permission bits, non-root")
class GfxTargetTests(unittest.TestCase):
    def test_kfd_versions_render_as_amd_names(self) -> None:
        self.assertEqual(GPU.gfx_name(110500), "gfx1150")
        self.assertEqual(GPU.gfx_name(110501), "gfx1151")
        self.assertEqual(GPU.gfx_name(110000), "gfx1100")
        self.assertEqual(GPU.gfx_name(120001), "gfx1201")
        self.assertEqual(GPU.gfx_name(90402), "gfx942")
        self.assertEqual(GPU.gfx_name(90010), "gfx90a")  # stepping in hex, as AMD writes it
        self.assertIsNone(GPU.gfx_name(0))

    def test_targets_come_from_kfd_topology_skipping_cpu_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_root(Path(tmp))
            self.assertEqual(GPU.amd_gfx_targets(root), ["gfx1150"])
            self.assertEqual(GPU.amd_gfx_targets(Path(tmp) / "absent"), [])

    def test_supported_set_is_one_documented_constant(self) -> None:
        for target in ("gfx1150", "gfx1151", "gfx1100", "gfx1101", "gfx1102", "gfx1200", "gfx1201", "gfx942"):
            self.assertIn(target, GPU.ROCM_SUPPORTED_TARGETS)
        self.assertIn("compatibility-matrix", GPU.ROCM_COMPATIBILITY_URL)


@unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permission bits, non-root")
class AccessTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)

    def test_vendor_memory_and_devices_are_read_from_the_root(self) -> None:
        root = fake_root(self.base)
        facts = GPU.access(root, system="Linux", machine="x86_64", which=lambda _n: "/usr/bin/sg")
        self.assertEqual(facts["vendor"], "amd")
        self.assertEqual(facts["cards"], [{"card": "card0", "vendor": "0x1002",
                                           "vram_bytes": 34359738368, "gtt_bytes": 16635277312}])
        self.assertEqual(facts["nodes"], {"/dev/kfd": False, "/dev/dri/renderD128": False})
        self.assertFalse(facts["accessible"])

    def test_listed_user_outside_the_group_in_this_session_gets_sg(self) -> None:
        facts = GPU.access(fake_root(self.base), system="Linux", machine="x86_64",
                           which=lambda _n: "/usr/bin/sg")
        self.assertEqual(facts["group"]["name"], "render")
        self.assertTrue(facts["group"]["listed"])
        self.assertFalse(facts["group"]["in_session"])
        self.assertTrue(facts["sg_remedy"])

    def test_unlisted_user_gets_no_sg_and_the_usermod_remedy(self) -> None:
        facts = GPU.access(fake_root(self.base, listed=False), system="Linux", machine="x86_64",
                           which=lambda _n: "/usr/bin/sg")
        self.assertFalse(facts["group"]["listed"])
        self.assertFalse(facts["sg_remedy"])
        codes = {r["code"]: r for r in GPU.remedies({**facts, "torch": None, "llama": None})}
        self.assertIn("GPU_GROUP_MISSING", codes)
        self.assertEqual(codes["GPU_GROUP_MISSING"]["command"], "sudo usermod -aG render,video $USER")

    def test_accessible_devices_need_no_group_remedy(self) -> None:
        facts = GPU.access(fake_root(self.base, devices_rw=True), system="Linux", machine="x86_64",
                           which=lambda _n: "/usr/bin/sg")
        self.assertTrue(facts["accessible"])
        self.assertFalse(facts["sg_remedy"])
        codes = {r["code"] for r in GPU.remedies({**facts, "torch": None, "llama": None})}
        self.assertFalse(codes & {"GPU_GROUP_MISSING", "GPU_GROUP_NOT_IN_SESSION"})

    def test_nvidia_and_apple_and_none(self) -> None:
        nvidia = fake_root(self.base / "n", vendor="0x10de", gfx=None, kfd=False)
        self.assertEqual(GPU.access(nvidia, system="Linux", machine="x86_64", which=lambda _n: None)["vendor"],
                         "nvidia")
        empty = self.base / "empty"
        empty.mkdir()
        self.assertEqual(GPU.access(empty, system="Linux", machine="x86_64", which=lambda _n: None)["vendor"], "none")
        self.assertEqual(GPU.access(empty, system="Darwin", machine="arm64", which=lambda _n: None)["vendor"], "apple")

    def test_a_broken_root_never_raises(self) -> None:
        root = self.base / "broken"
        _write(root / "sys" / "class" / "drm" / "card0" / "device" / "vendor", "not-hex\n")
        _write(root / "sys" / "class" / "kfd" / "kfd" / "topology" / "nodes" / "1" / "properties",
               "gfx_target_version banana\n")
        _write(root / "etc" / "group", "garbage line without colons\n")
        facts = GPU.access(root, system="Linux", machine="x86_64", which=lambda _n: None)
        self.assertEqual(facts["vendor"], "none")
        self.assertEqual(facts["gfx_targets"], [])


@unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permission bits, non-root")
class ReexecTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)

    def _facts(self, **kwargs):
        return GPU.access(fake_root(self.base, **kwargs), system="Linux", machine="x86_64",
                          which=lambda _n: "/usr/bin/sg")

    def test_inaccessible_devices_and_a_listed_user_reexec_under_sg_with_quoted_argv(self) -> None:
        argv = ["/env/bin/python", "/w/extract_pdf.py", "--engine", "marker", "a paper's name.pdf"]
        out = GPU.reexec_argv(argv, self._facts(), environ={})
        self.assertEqual(out[:3], ["/usr/bin/sg", "render", "-c"])
        self.assertEqual(out[3], "/env/bin/python /w/extract_pdf.py --engine marker 'a paper'\"'\"'s name.pdf'")

    def test_the_marker_stops_a_second_reexec(self) -> None:
        self.assertIsNone(GPU.reexec_argv(["p"], self._facts(), environ={GPU.REEXEC_ENV: "1"}))

    def test_no_reexec_when_devices_are_accessible_or_absent_or_user_unlisted(self) -> None:
        self.assertIsNone(GPU.reexec_argv(["p"], self._facts(devices_rw=True), environ={}))
        self.assertIsNone(GPU.reexec_argv(["p"], self._facts(listed=False), environ={}))
        empty = self.base / "empty"
        empty.mkdir()
        facts = GPU.access(empty, system="Linux", machine="x86_64", which=lambda _n: "/usr/bin/sg")
        self.assertIsNone(GPU.reexec_argv(["p"], facts, environ={}))


class LlamaAndTorchTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)

    def test_vulkan_lines_are_parsed(self) -> None:
        text = ("Available devices:\n  Vulkan0: AMD Radeon 890M (RADV GFX1150) (48632 MiB, 33042 MiB free)\n"
                "  BLAS: MKL (0 MiB, 0 MiB free)\n")
        self.assertEqual(GPU.parse_vulkan_devices(text), ["AMD Radeon 890M (RADV GFX1150)"])
        self.assertEqual(GPU.parse_vulkan_devices("  BLAS: MKL (0 MiB, 0 MiB free)\n"), [])

    @unittest.skipIf(os.name == "nt", "shell-script stand-ins")
    def test_vulkan_devices_runs_the_binary_and_fails_closed(self) -> None:
        binary = fake_llama(self.base, ["  Vulkan0: AMD Radeon 890M (RADV GFX1150) (48632 MiB, 1 MiB free)"])
        self.assertEqual(GPU.vulkan_devices(str(binary))["devices"], ["AMD Radeon 890M (RADV GFX1150)"])
        missing = GPU.vulkan_devices(str(self.base / "nope"))
        self.assertEqual(missing["devices"], [])
        self.assertTrue(missing["error"])
        self.assertEqual(GPU.vulkan_devices(None)["devices"], [])

    def test_llama_server_binary_prefers_the_env_var_then_the_interpreters_bin(self) -> None:
        env_bin = _write(self.base / "env" / "bin" / "llama-server", "", 0o755)
        python = self.base / "env" / "bin" / "python"
        self.assertEqual(GPU.llama_server_binary({"LLAMA_CPP_BINARY": "/x/llama"}, str(python), which=lambda _n: None),
                         "/x/llama")
        self.assertEqual(GPU.llama_server_binary({}, str(python), which=lambda _n: None), str(env_bin))
        self.assertEqual(GPU.llama_server_binary({}, str(self.base / "p"), which=lambda _n: "/usr/bin/llama-server"),
                         "/usr/bin/llama-server")

    @unittest.skipIf(os.name == "nt", "shell-script stand-ins")
    def test_torch_backend_through_another_interpreter_reads_the_last_json_line(self) -> None:
        python = fake_python(self.base, {"available": True, "version": "2.14.0+rocm10.1.0",
                                         "backend": "hip", "hip": "10.1", "cuda": None, "device": "AMD Radeon 890M"})
        info = GPU.torch_backend(str(python))
        self.assertEqual(info["backend"], "hip")
        broken = GPU.torch_backend(str(self.base / "no-python"))
        self.assertFalse(broken["available"])
        self.assertEqual(broken["backend"], "cpu")

    def test_backend_env_on_rocm_and_on_vulkan_only(self) -> None:
        hip = GPU.backend_env({"backend": "hip"}, [], environ={})
        self.assertEqual(hip, {"SURYA_INFERENCE_BACKEND": "llamacpp", "DOCLING_DEVICE": "cuda"})
        vulkan = GPU.backend_env({"backend": "cpu"}, ["AMD Radeon 890M"], environ={})
        self.assertEqual(vulkan, {"TORCH_DEVICE": "cpu", "SURYA_INFERENCE_BACKEND": "llamacpp",
                                  "LLAMA_CPP_NGL": "99"})
        self.assertEqual(GPU.backend_env({"backend": "hip"}, [], environ={"SURYA_INFERENCE_BACKEND": "vllm"}),
                         {"DOCLING_DEVICE": "cuda"})
        self.assertEqual(GPU.backend_env({"backend": "cuda"}, ["x"], environ={}), {})
        self.assertEqual(GPU.backend_env({"backend": "cpu"}, [], environ={}), {})

    def test_rocm_install_names_the_index_the_extra_and_the_pins(self) -> None:
        args = GPU.rocm_pip_args("gfx1150")
        self.assertIn("https://stable.repo.amd.com/rocm/whl-next/", args)
        self.assertIn(f"torch[device-gfx1150]=={GPU.ROCM_TORCH_VERSION}", args)
        self.assertIn(f"torchvision[device-gfx1150]=={GPU.ROCM_TORCHVISION_VERSION}", args)


@unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permission bits, non-root")
class RemedyTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)

    def _report(self, environ=None, **torch):
        facts = GPU.access(fake_root(self.base), system="Linux", machine="x86_64", which=lambda _n: "/usr/bin/sg")
        info = {"available": True, "backend": "cpu", "version": "2.14.1", "python": "/env/bin/python", **torch}
        return {**facts, "torch": info, "llama": {"binary": "/env/bin/llama-server", "devices": []},
                "environ": environ or {}}

    def test_cpu_torch_on_a_supported_amd_target_names_the_rocm_install(self) -> None:
        codes = {r["code"]: r for r in GPU.remedies(self._report())}
        rocm = codes["ROCM_TORCH_MISSING"]
        self.assertIn("smith env install --rocm", rocm["message"])
        self.assertIn("/env/bin/python -m pip install", rocm["command"])
        self.assertIn("torch[device-gfx1150]", rocm["command"])
        self.assertEqual(codes["GPU_GROUP_NOT_IN_SESSION"]["command"], "sg render -c '<command>'")

    def test_hsa_override_on_a_supported_target_warns(self) -> None:
        codes = {r["code"]: r for r in GPU.remedies(self._report({"HSA_OVERRIDE_GFX_VERSION": "11.0.0"}, backend="hip"))}
        self.assertEqual(codes["HSA_OVERRIDE_SET"]["command"], "unset HSA_OVERRIDE_GFX_VERSION")
        self.assertNotIn("ROCM_TORCH_MISSING", codes)


@unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "POSIX permission bits, non-root")
class SmithGpuCommandTests(unittest.TestCase):
    """`smith gpu --json` as a real process, against the fake root."""

    def test_json_reports_the_probe_and_every_remedy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = fake_root(base)
            llama = fake_llama(base, ["  Vulkan0: AMD Radeon 890M (RADV GFX1150) (48632 MiB, 1 MiB free)"])
            python = fake_python(base, {"available": True, "version": "2.14.1", "backend": "cpu",
                                        "hip": None, "cuda": None, "device": None})
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
            env[GPU.SYSROOT_ENV] = str(root)
            env["LLAMA_CPP_BINARY"] = str(llama)
            env.pop("HSA_OVERRIDE_GFX_VERSION", None)
            done = subprocess.run([sys.executable, "-m", "papersmith.cli", "gpu", "--json", "--python", str(python),
                                   str(base)], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads(done.stdout)
            self.assertEqual(report["vendor"], "amd")
            self.assertEqual(report["gfx_targets"], ["gfx1150"])
            self.assertTrue(report["rocm_supported"])
            self.assertEqual(report["nodes"], {"/dev/kfd": False, "/dev/dri/renderD128": False})
            self.assertEqual(report["llama"]["devices"], ["AMD Radeon 890M (RADV GFX1150)"])
            self.assertEqual(report["torch"]["backend"], "cpu")
            self.assertIn("Vulkan (llama.cpp)", report["accelerators"])
            codes = {r["code"] for r in report["remedies"]}
            self.assertIn("ROCM_TORCH_MISSING", codes)
            self.assertIn("GPU_GROUP_NOT_IN_SESSION" if shutil.which("sg") else "GPU_GROUP_MISSING", codes)

            text = subprocess.run([sys.executable, "-m", "papersmith.cli", "gpu", "--python", str(python),
                                   str(base)], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(text.returncode, 0, text.stderr)
            self.assertIn("gfx1150", text.stdout)
            self.assertIn("pip install", text.stdout)

    def test_the_command_is_registered(self) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        from papersmith.cli import build_parser

        args = build_parser().parse_args(["gpu", "--json"])
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
