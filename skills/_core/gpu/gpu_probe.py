#!/usr/bin/env python3
"""What GPU this machine has, whether this process can reach it, and how to fix it.

One stdlib-only probe shared by ``smith gpu``, the paper-ingestion scripts and
``scripts/setup_env.py``. It works on any machine -- NVIDIA, AMD, Apple Silicon
or none -- and reads only what the kernel and the installed tools say:

* the vendor, from each DRM card's PCI vendor id
  (``/sys/class/drm/card<N>/device/vendor``) or from the platform on macOS;
* the AMD ``gfx`` target, from the KFD topology
  (``/sys/class/kfd/kfd/topology/nodes/*/properties``, ``gfx_target_version``
  ``110500`` -> ``gfx1150``);
* VRAM and GTT totals (``mem_info_{vram,gtt}_total``);
* whether this process can open the device nodes (``/dev/kfd``,
  ``/dev/dri/renderD*``), whether the account is listed in the ``render``
  group, and whether that membership is live in this session -- when it is
  listed but not live (a session older than the ``usermod``), ``sg render -c``
  grants it without a password, which is the remedy ingestion applies itself;
* the Vulkan devices llama.cpp can open (``llama-server --list-devices``);
* the PyTorch backend (``cuda``, ``hip``, ``mps`` or ``cpu``) of an
  interpreter, in process or through another environment's ``python``.

Every probe fails closed and fast: a missing file, an unreadable node, a tool
that hangs or a malformed value yields "nothing found", never an exception.
``PAPERSMITH_GPU_SYSROOT`` points every sysfs, ``/dev`` and ``/etc/group`` read
at another root (tests use a fake one).

Run directly: ``python gpu_probe.py [--json] [--python <interpreter>]``.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

#: Environment variable that re-roots every sysfs, /dev and /etc/group read.
SYSROOT_ENV = "PAPERSMITH_GPU_SYSROOT"
#: Set in the child of a ``sg render -c`` re-execution, so it never re-executes again.
REEXEC_ENV = "PAPERSMITH_GPU_SG_REEXEC"
#: The group that owns the GPU compute and render nodes on Linux.
GPU_GROUP = "render"

#: AMD gfx targets the ROCm 10.1 PyTorch wheels support natively, so
#: ``setup_env.py`` installs them by default on these GPUs (``--rocm`` forces
#: any other target). Checked against the ROCm compatibility matrix below; add
#: a target here only when that matrix lists it for the wheel release pinned
#: in ``ROCM_TORCH_VERSION``.
ROCM_SUPPORTED_TARGETS = frozenset({
    "gfx1100", "gfx1101", "gfx1102",  # RDNA3 (Radeon RX 7000, PRO W7000)
    "gfx1150", "gfx1151",             # RDNA3.5 APUs (Radeon 880M/890M, Strix Halo)
    "gfx1200", "gfx1201",             # RDNA4 (Radeon RX 9000)
    "gfx942",                         # CDNA3 (Instinct MI300)
})
ROCM_COMPATIBILITY_URL = "https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html"
#: AMD's wheel index: the ROCm runtime ships inside the wheels (no system ROCm).
ROCM_WHEEL_INDEX = "https://stable.repo.amd.com/rocm/whl-next/"
ROCM_TORCH_VERSION = "2.14.0+rocm10.1.0"
ROCM_TORCHVISION_VERSION = "0.29.0a0+rocm10.1.0"

PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}

#: Seconds a ``llama-server --list-devices`` may take before it counts as none.
LLAMA_TIMEOUT = 20
#: Seconds a foreign interpreter may take to import torch.
TORCH_TIMEOUT = 90

_VULKAN_LINE = re.compile(r"^\s*Vulkan\d+:\s*(.+?)\s*(?:\(\d+ MiB.*)?$")
_CARD = re.compile(r"^card\d+$")

_TORCH_PROBE = r"""
import json
info = {"available": False, "version": None, "backend": "cpu", "hip": None, "cuda": None, "device": None}
try:
    import torch
    info["available"] = True
    info["version"] = torch.__version__
    info["hip"] = getattr(torch.version, "hip", None)
    info["cuda"] = getattr(torch.version, "cuda", None)
    if torch.cuda.is_available():
        info["backend"] = "hip" if info["hip"] else "cuda"
        info["device"] = torch.cuda.get_device_name(0)
    else:
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            info["backend"] = "mps"
except Exception as exc:
    info["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(info))
"""


# --------------------------------------------------------------------------- #
# Small readers that never raise
# --------------------------------------------------------------------------- #
def sysroot(root: str | os.PathLike | None = None) -> Path:
    """The root every system read is relative to (``/`` unless re-rooted)."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get(SYSROOT_ENV) or "/")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _int(text: str | None) -> int | None:
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None


def _listdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir())
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# Hardware
# --------------------------------------------------------------------------- #
def gfx_name(version: int | None) -> str | None:
    """``gfx_target_version`` -> AMD's name: 110500 -> gfx1150, 90010 -> gfx90a.

    major = v // 10000, minor = (v // 100) % 100, stepping = v % 100; minor and
    stepping are written as hex digits, as AMD names its targets."""
    if not version or version <= 0:
        return None
    major, minor, step = version // 10000, (version // 100) % 100, version % 100
    return f"gfx{major}{minor:x}{step:x}"


def amd_gfx_targets(root: str | os.PathLike | None = None) -> list[str]:
    """Every GPU node's gfx target in the KFD topology (CPU nodes report 0)."""
    nodes = sysroot(root) / "sys" / "class" / "kfd" / "kfd" / "topology" / "nodes"
    targets: list[str] = []
    for node in _listdir(nodes):
        for line in (_read(node / "properties") or "").splitlines():
            key, _, value = line.partition(" ")
            if key == "gfx_target_version":
                name = gfx_name(_int(value.strip()))
                if name and name not in targets:
                    targets.append(name)
    return targets


def drm_cards(root: str | os.PathLike | None = None) -> list[dict]:
    """Each DRM card with its PCI vendor id and VRAM/GTT totals in bytes."""
    cards = []
    for card in _listdir(sysroot(root) / "sys" / "class" / "drm"):
        if not _CARD.match(card.name):
            continue  # connector entries (card0-DP-1) carry no device of their own
        device = card / "device"
        vendor = (_read(device / "vendor") or "").lower()
        if vendor not in PCI_VENDORS:
            continue
        cards.append({"card": card.name, "vendor": vendor,
                      "vram_bytes": _int(_read(device / "mem_info_vram_total")),
                      "gtt_bytes": _int(_read(device / "mem_info_gtt_total"))})
    return cards


def detect_vendor(cards: list[dict], root: Path, system: str, machine: str,
                  which: Callable[[str], str | None]) -> str:
    """``nvidia``, ``amd``, ``apple`` or ``none``; NVIDIA wins on a hybrid laptop."""
    if system == "Darwin":
        return "apple" if machine.lower() in ("arm64", "aarch64") else "none"
    names = {PCI_VENDORS.get(card["vendor"]) for card in cards}
    if "nvidia" in names or (root / "dev" / "nvidia0").exists():
        return "nvidia"
    if "amd" in names:
        return "amd"
    if root == Path("/") and which("nvidia-smi"):
        return "nvidia"  # WSL and containers expose the driver without DRM cards
    return "none"


def device_nodes(root: str | os.PathLike | None = None) -> dict[str, bool]:
    """``{"/dev/kfd": rw, "/dev/dri/renderD128": rw, ...}`` for the nodes present."""
    base = sysroot(root)
    paths = []
    if (base / "dev" / "kfd").exists():
        paths.append(base / "dev" / "kfd")
    paths += [p for p in _listdir(base / "dev" / "dri") if p.name.startswith("renderD")]
    nodes = {}
    for path in paths:
        try:
            ok = os.access(path, os.R_OK | os.W_OK)
        except OSError:
            ok = False
        nodes["/" + path.relative_to(base).as_posix()] = ok
    return nodes


def current_user() -> str | None:
    try:
        import getpass

        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or os.environ.get("USERNAME")


def group_membership(root: str | os.PathLike | None = None, user: str | None = None,
                     process_groups: Iterable[int] | None = None) -> dict:
    """Whether ``user`` is listed in the ``render`` group and whether this
    process already holds it (a session predating ``usermod`` does not)."""
    base = sysroot(root)
    user = user if user is not None else current_user()
    info = {"name": GPU_GROUP, "exists": False, "gid": None, "user": user, "listed": False, "in_session": False}
    for line in (_read(base / "etc" / "group") or "").splitlines():
        fields = line.split(":")
        if len(fields) < 4 or fields[0] != GPU_GROUP:
            continue
        info["exists"], info["gid"] = True, _int(fields[2])
        info["listed"] = bool(user) and user in [m.strip() for m in fields[3].split(",")]
        break
    if base == Path("/") and user and not info["listed"]:
        try:  # NSS groups (LDAP, sssd) that /etc/group does not hold
            import grp

            entry = grp.getgrnam(GPU_GROUP)
            info["exists"], info["gid"] = True, entry.gr_gid
            info["listed"] = user in entry.gr_mem
        except (ImportError, KeyError, OSError):
            pass
    if process_groups is None:
        try:
            process_groups = set(os.getgroups()) | {os.getegid()}
        except (AttributeError, OSError):
            process_groups = set()
    info["in_session"] = info["gid"] is not None and info["gid"] in set(process_groups)
    return info


def access(root: str | os.PathLike | None = None, *, system: str | None = None, machine: str | None = None,
           user: str | None = None, process_groups: Iterable[int] | None = None,
           which: Callable[[str], str | None] = shutil.which) -> dict:
    """The cheap, sysfs-only half of the probe: vendor, gfx targets, memory,
    device access and the render-group remedy. No subprocess is started."""
    base = sysroot(root)
    system = system or platform.system()
    machine = machine or platform.machine()
    try:
        cards = drm_cards(base)
        targets = amd_gfx_targets(base)
        vendor = detect_vendor(cards, base, system, machine, which)
        nodes = device_nodes(base) if system == "Linux" else {}
        group = group_membership(base, user, process_groups)
    except Exception:  # fail closed: an unexpected layout reads as no GPU
        cards, targets, vendor, nodes, group = [], [], "none", {}, group_membership(Path("/nonexistent"), user, ())
    accessible = bool(nodes) and all(nodes.values())
    sg = which("sg") if system == "Linux" else None
    blocked = bool(nodes) and not accessible
    return {
        "platform": {"system": system, "machine": machine},
        "vendor": vendor,
        "cards": cards,
        "gfx_targets": targets,
        "rocm_supported": any(t in ROCM_SUPPORTED_TARGETS for t in targets),
        "nodes": nodes,
        "accessible": accessible,
        "group": group,
        "sg": sg,
        "sg_remedy": bool(blocked and group["listed"] and not group["in_session"] and sg),
    }


# --------------------------------------------------------------------------- #
# Tools: llama.cpp and PyTorch
# --------------------------------------------------------------------------- #
def llama_server_binary(environ: dict | None = None, python: str | None = None,
                        which: Callable[[str], str | None] = shutil.which) -> str | None:
    """The ``llama-server`` Surya would spawn: ``LLAMA_CPP_BINARY``, else the
    one beside ``python`` (an environment run without activation leaves its
    ``bin/`` off PATH), else PATH."""
    environ = os.environ if environ is None else environ
    named = environ.get("LLAMA_CPP_BINARY")
    if named:
        return which(named) or named
    beside = Path(python or sys.executable).parent / ("llama-server.exe" if os.name == "nt" else "llama-server")
    try:
        if beside.is_file() and os.access(beside, os.X_OK):
            return str(beside)
    except OSError:
        pass
    return which("llama-server")


def parse_vulkan_devices(text: str) -> list[str]:
    """The device names of every ``Vulkan<N>:`` line of ``--list-devices``."""
    return [m.group(1) for line in (text or "").splitlines() if (m := _VULKAN_LINE.match(line))]


def vulkan_devices(binary: str | None, *, prefix: list[str] | None = None, timeout: float = LLAMA_TIMEOUT,
                   run: Callable = subprocess.run) -> dict:
    """``{"binary", "devices", "error"}`` from ``<binary> --list-devices``.

    ``prefix`` wraps the command (``["sg", "render", "-c"]`` lists what a
    re-executed run would see)."""
    result = {"binary": binary, "devices": [], "error": None}
    if not binary:
        result["error"] = "no llama-server found"
        return result
    argv = [binary, "--list-devices"]
    if prefix:
        argv = [*prefix, shlex.join(argv)]
    try:
        done = run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        result["devices"] = parse_vulkan_devices((done.stdout or "") + "\n" + (done.stderr or ""))
    except Exception as exc:  # OSError, TimeoutExpired, anything a stand-in raises
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def torch_backend(python: str | None = None, *, timeout: float = TORCH_TIMEOUT,
                  run: Callable = subprocess.run) -> dict:
    """PyTorch's backend: ``cuda``, ``hip`` (ROCm), ``mps`` or ``cpu``.

    In process when ``python`` is None (the caller is about to import torch
    anyway); otherwise through that interpreter, whose last JSON line is read."""
    empty = {"python": python or sys.executable, "available": False, "version": None, "backend": "cpu",
             "hip": None, "cuda": None, "device": None}
    if python is None:
        scope: dict = {}
        try:
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()) as out:
                exec(_TORCH_PROBE, scope)  # noqa: S102 -- a fixed probe, no input
            return {**empty, **json.loads(out.getvalue().strip().splitlines()[-1])}
        except Exception as exc:
            return {**empty, "error": f"{type(exc).__name__}: {exc}"}
    try:
        done = run([python, "-c", _TORCH_PROBE], capture_output=True, text=True, timeout=timeout,
                   stdin=subprocess.DEVNULL)
        for line in reversed((done.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return {**empty, **json.loads(line)}
        return {**empty, "error": (done.stderr or "no output").strip()[-300:]}
    except Exception as exc:
        return {**empty, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def rocm_pip_args(gfx: str) -> list[str]:
    """``pip install`` arguments for AMD's ROCm wheels built for ``gfx``.

    The ``device-<gfx>`` extra pulls the kernels for that target; the runtime
    is bundled, so no system ROCm is needed. Exact pins keep pip from taking
    PyPI's newer CPU build through the extra index."""
    return ["--index-url", ROCM_WHEEL_INDEX, "--extra-index-url", "https://pypi.org/simple",
            f"torch[device-{gfx}]=={ROCM_TORCH_VERSION}",
            f"torchvision[device-{gfx}]=={ROCM_TORCHVISION_VERSION}"]


def sg_command(argv: list[str], sg: str = "sg") -> list[str]:
    """``argv`` run under ``sg render -c``, shell-quoted so it survives intact."""
    return [sg, GPU_GROUP, "-c", shlex.join(argv)]


def reexec_argv(argv: list[str], facts: dict, environ: dict | None = None) -> list[str] | None:
    """The ``sg render -c`` command that re-runs ``argv`` with the GPU group,
    or None when it would not help (devices open or absent, account not
    listed, no ``sg``) or this process already is the re-execution."""
    environ = os.environ if environ is None else environ
    if environ.get(REEXEC_ENV) or not facts.get("sg_remedy"):
        return None
    return sg_command(list(argv), facts["sg"])


def backend_env(torch_info: dict | None, vulkan: list[str] | None, environ: dict | None = None) -> dict[str, str]:
    """Environment the ingestion engines need for the GPU found, minus what is set.

    * ROCm: Surya reads any ``torch.cuda`` device as NVIDIA and would start
      vllm, so ``SURYA_INFERENCE_BACKEND=llamacpp``; Docling takes the GPU
      through ``DOCLING_DEVICE=cuda`` (ROCm answers the CUDA API).
    * Vulkan only (torch on the CPU): the layout model stays on the CPU
      (``TORCH_DEVICE=cpu``) and the recognition model runs in llama.cpp on
      the GPU with every layer offloaded (``LLAMA_CPP_NGL=99``)."""
    environ = os.environ if environ is None else environ
    backend = (torch_info or {}).get("backend") or "cpu"
    wanted: dict[str, str] = {}
    if backend == "hip":
        wanted = {"SURYA_INFERENCE_BACKEND": "llamacpp", "DOCLING_DEVICE": "cuda"}
    elif backend == "cpu" and vulkan:
        wanted = {"TORCH_DEVICE": "cpu", "SURYA_INFERENCE_BACKEND": "llamacpp", "LLAMA_CPP_NGL": "99"}
    return {key: value for key, value in wanted.items() if key not in environ}


def accelerators(report: dict) -> list[str]:
    torch_info = report.get("torch") or {}
    found = {"cuda": "CUDA", "hip": "ROCm (HIP)", "mps": "MPS (Apple Silicon)"}.get(torch_info.get("backend"))
    out = [found] if found else []
    if (report.get("llama") or {}).get("devices"):
        out.append("Vulkan (llama.cpp)")
    return out


def remedies(report: dict) -> list[dict]:
    """One ``{code, message, command}`` per blocker between this machine and its GPU."""
    out: list[dict] = []
    torch_info = report.get("torch") or {}
    llama = report.get("llama") or {}
    environ = report.get("environ") if report.get("environ") is not None else dict(os.environ)
    group = report.get("group") or {}
    nodes = report.get("nodes") or {}
    vendor = report.get("vendor")
    targets = report.get("gfx_targets") or []
    supported = [t for t in targets if t in ROCM_SUPPORTED_TARGETS]
    python = torch_info.get("python") or "python"

    if nodes and not report.get("accessible"):
        if group.get("listed") and not group.get("in_session"):
            out.append({"code": "GPU_GROUP_NOT_IN_SESSION",
                        "message": "the account is in the render group but this session predates it; ingestion "
                                   "re-executes itself under `sg render -c`. Log out and back in to make it permanent."
                                   if report.get("sg") else
                                   "the account is in the render group but this session predates it; log out and back in.",
                        "command": "sg render -c '<command>'" if report.get("sg") else "newgrp render"})
        elif not group.get("listed"):
            out.append({"code": "GPU_GROUP_MISSING",
                        "message": f"this account cannot open {', '.join(n for n, ok in nodes.items() if not ok)}; "
                                   "add it to the render and video groups, then log out and back in.",
                        "command": "sudo usermod -aG render,video $USER"})
    if vendor == "amd" and supported and torch_info.get("backend") != "hip":
        gfx = supported[0]
        out.append({"code": "ROCM_TORCH_MISSING",
                    "message": f"{gfx} is supported by ROCm 10.1 but PyTorch here is "
                               f"{torch_info.get('version') or 'absent'} ({torch_info.get('backend', 'cpu')}); "
                               "`smith env install --rocm` installs AMD's wheels into the workspace environment, "
                               "or run the command below in the environment you ingest with.",
                    "command": f"{python} -m pip install " + " ".join(shlex.quote(a) for a in rocm_pip_args(gfx))})
    if vendor == "amd" and targets and not supported:
        out.append({"code": "ROCM_TARGET_UNSUPPORTED",
                    "message": f"{', '.join(targets)} is not in the ROCm 10.1 wheel set ({ROCM_COMPATIBILITY_URL}); "
                               "Vulkan through llama.cpp still serves Marker's OCR model. "
                               "`smith env install --rocm` forces the wheels anyway.",
                    "command": None})
    if environ.get("HSA_OVERRIDE_GFX_VERSION") and supported:
        out.append({"code": "HSA_OVERRIDE_SET",
                    "message": f"HSA_OVERRIDE_GFX_VERSION={environ['HSA_OVERRIDE_GFX_VERSION']} is set, but "
                               f"{supported[0]} is supported natively; the override loads kernels built for "
                               "another target.",
                    "command": "unset HSA_OVERRIDE_GFX_VERSION"})
    if vendor == "nvidia" and torch_info and torch_info.get("backend") not in ("cuda", None) and torch_info.get("available"):
        out.append({"code": "CUDA_TORCH_MISSING",
                    "message": "an NVIDIA GPU is present but PyTorch here is a CPU build.",
                    "command": "smith env install --cuda"})
    if vendor in ("amd", "intel") or (vendor == "none" and report.get("cards")):
        if not llama.get("binary"):
            out.append({"code": "LLAMA_SERVER_MISSING",
                        "message": "no llama-server found; `smith env install` provides conda-forge's llama.cpp "
                                   "(built with Vulkan).",
                        "command": "smith env install"})
        elif not llama.get("devices") and not llama.get("devices_via_sg") and report.get("accessible"):
            out.append({"code": "VULKAN_MISSING",
                        "message": "llama-server lists no Vulkan GPU; install the Mesa Vulkan driver "
                                   "(RADV for AMD, ANV for Intel) from your distribution.",
                        "command": None})
    return out


def probe(root: str | os.PathLike | None = None, *, python: str | None = None, environ: dict | None = None,
          user: str | None = None, process_groups: Iterable[int] | None = None,
          which: Callable[[str], str | None] = shutil.which, run: Callable = subprocess.run,
          with_torch: bool = True) -> dict:
    """The full report: :func:`access`, llama.cpp's Vulkan devices (also under
    ``sg render`` when that is the remedy), the torch backend, accelerators and
    remedies."""
    environ = dict(os.environ if environ is None else environ)
    report = access(root, user=user, process_groups=process_groups, which=which)
    binary = llama_server_binary(environ, python, which)
    llama = vulkan_devices(binary, run=run)
    if not llama["devices"] and report["sg_remedy"] and binary:
        llama["devices_via_sg"] = vulkan_devices(binary, prefix=[report["sg"], GPU_GROUP, "-c"], run=run)["devices"]
    report["llama"] = llama
    report["torch"] = torch_backend(python, run=run) if with_torch else None
    report["hsa_override"] = environ.get("HSA_OVERRIDE_GFX_VERSION")
    report["accelerators"] = accelerators(report)
    report["remedies"] = remedies({**report, "environ": environ})
    return report


# --------------------------------------------------------------------------- #
# Text rendering (shared by `smith gpu` and direct runs)
# --------------------------------------------------------------------------- #
def _gib(value: int | None) -> str:
    return f"{value / 2**30:.1f} GiB" if value else "-"


def render_text(report: dict) -> str:
    lines = [f"GPU vendor: {report['vendor']}  ({report['platform']['system']} {report['platform']['machine']})"]
    for card in report.get("cards") or []:
        lines.append(f"  {card['card']}: PCI {card['vendor']}  VRAM {_gib(card['vram_bytes'])}  "
                     f"GTT {_gib(card['gtt_bytes'])}")
    if report.get("gfx_targets"):
        state = "supported by the ROCm 10.1 wheels" if report["rocm_supported"] else "not in the ROCm 10.1 wheel set"
        lines.append(f"AMD target: {', '.join(report['gfx_targets'])} ({state})")
    for node, ok in (report.get("nodes") or {}).items():
        lines.append(f"  {node}: {'read/write' if ok else 'NOT accessible to this process'}")
    group = report.get("group") or {}
    if group.get("exists"):
        lines.append(f"render group: account {'listed' if group.get('listed') else 'NOT listed'}, "
                     f"{'active' if group.get('in_session') else 'not active'} in this session")
    llama = report.get("llama") or {}
    vulkan = llama.get("devices") or []
    lines.append(f"llama-server: {llama.get('binary') or 'not found'}"
                 + (f"  Vulkan: {', '.join(vulkan)}" if vulkan else "  Vulkan: none"))
    if llama.get("devices_via_sg"):
        lines.append(f"  under `sg render`: Vulkan {', '.join(llama['devices_via_sg'])}")
    torch_info = report.get("torch")
    if torch_info:
        lines.append(f"torch ({torch_info.get('python')}): "
                     + (f"{torch_info.get('version')} backend {torch_info.get('backend')}"
                        + (f" on {torch_info['device']}" if torch_info.get("device") else "")
                        if torch_info.get("available") else "not importable"))
    lines.append(f"accelerators: {', '.join(report.get('accelerators') or []) or 'none (CPU only)'}")
    for item in report.get("remedies") or []:
        lines.append(f"[{item['code']}] {item['message']}")
        if item.get("command"):
            lines.append(f"    $ {item['command']}")
    if not report.get("remedies"):
        lines.append("Nothing blocks the GPU.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report this machine's GPU and what blocks it.")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--python", default=None, help="interpreter whose torch to probe (default: this one)")
    args = parser.parse_args(argv)
    report = probe(python=args.python)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
