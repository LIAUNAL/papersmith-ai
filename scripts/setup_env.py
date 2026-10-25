#!/usr/bin/env python3
"""Cross-platform environment provisioning via micromamba.

One script, every OS (Linux / macOS / Windows). It creates a single isolated
environment (`papersmith`) that holds every Python dependency the forge needs,
and installs the hardware-appropriate build of PyTorch (CUDA when an NVIDIA GPU
is present, CPU otherwise) plus the `llama-server` OCR backend — both pulled from
conda-forge rather than Homebrew, so the same command works everywhere.

What it installs
    conda-forge: python=3.12, pip, pytest, pytest-xdist, python-build, numpy, pypdfium2, pyyaml, jsonschema,
                 kagglesdk, llama.cpp (provides llama-server), nbformat, nbclient
                 and ipykernel (remote-execution runs notebooks), fastapi,
                 uvicorn, watchfiles and pydantic (the Paper Command Center
                 server the kit ships), and torch —
                 `pytorch-gpu`+`torchvision` on CUDA machines, else
                 `pytorch-cpu`+`torchvision`.
    pip:         this project itself, editable (`pip install -e .`), and the
                 paper-ingestion heavy engine: docling (MIT), plus mlx-vlm (MIT)
                 on Apple Silicon so its formula model runs on the GPU. Every one
                 is license-unrestricted. pypdfium2 (Apache-2.0/BSD-3) is the
                 fast path and comes from conda-forge with the base packages, so
                 `--no-ingestion` still ingests digital PDFs. Marker is no longer
                 installed: its weights are free only below USD 5M in funding or
                 revenue; `pip install marker-pdf==2.0.0` opts in.

Usage
    python3 scripts/setup_env.py install          # detect hardware, provision
    python3 scripts/setup_env.py install --cpu    # force CPU torch
    python3 scripts/setup_env.py install --cuda   # force CUDA torch
    python3 scripts/setup_env.py clean            # remove the environment
    python3 scripts/setup_env.py clean --full     # also remove bootstrapped micromamba

The micromamba it bootstraps is a pinned release (`MICROMAMBA_VERSION`), checked
against a SHA-256 kept here (`MICROMAMBA_SHA256`) before it is put in place or
run. The comment above those constants is the procedure for moving the pin.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

ENV_NAME = "papersmith"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAMBA_ROOT = PROJECT_ROOT / ".micromamba"

# Only pip-only packages go here. Everything else is available on conda-forge and
# is installed through micromamba so platform + hardware variants resolve cleanly.
PIP_PACKAGES = [
    "docling==2.141.0",
    "mlx-vlm==0.7.10; sys_platform == 'darwin' and platform_machine == 'arm64'",
]

CONDA_BASE_PACKAGES = [
    "python=3.12",
    "pip",
    "pytest",
    # `npm run test:py:par` runs the suite across workers (`--dist loadfile`).
    "pytest-xdist",
    # PyPI artifact tests run `python -m build`; the checkout's build/ namespace
    # is not the build distribution. Keep this available even with --no-ingestion.
    "python-build",
    # `tests/test_remote_execution.py` imports requests at module scope, and
    # `tests/test_forge_gate.py` derives every top-level third-party import the
    # forge's own code requires and probes the gate's interpreter for each one.
    # It lived only in `requirements.txt`, which this script never reads, so a
    # correctly provisioned environment failed that probe.
    "requests",
    "numpy",
    # The paper-ingestion fast path and page probe (Apache-2.0 / BSD-3-Clause).
    "pypdfium2",
    "pyyaml",
    "jsonschema",
    # Pinned to requirements.txt's version (tests/test_env_pins.py): the doctrine
    # pin test requires exactly that version, and a bare name took conda-forge's
    # newest build the day 0.1.38 was published (#108).
    "kagglesdk==0.1.37",
    "llama.cpp",
    # remote-execution reads and executes notebooks. `nbformat` parses them
    # and `nbclient` drives them, but driving a notebook means talking to a
    # KERNEL, and the kernel is a separate package: `nbclient` pulls in
    # `jupyter_client`, which knows how to speak to a kernel, and never
    # `ipykernel`, which is the one that runs the cells. Without all three
    # the notebook suites fail -- the first two on import, the last one at
    # execution, where the failure surfaces as a unit process exiting
    # non-zero rather than as a missing module.
    #
    # All three were absent here and present in a hand-made virtualenv that
    # nothing in this repository creates, which is why the gap stayed
    # invisible: every run was green on an environment this script had
    # never actually produced.
    "nbformat",
    "nbclient",
    "ipykernel",
    # The Paper Command Center (`skills/_core/command_center/`) ships into every
    # initialized workspace, and `requirements.txt` -- itself a kit entry, so it
    # ships too -- names these four as that server's dependencies. This script
    # never reads that file, so the declaration and the provisioning disagreed:
    # the interpreter `package.json` names could not import `fastapi`, and
    # `tests/test_command_center_server.py` failed to LOAD. A module that fails
    # to load reports itself as a defect in the suite, which is the reading this
    # gap produced for as long as it existed; `tests/test_suite_collects.py`
    # names the module and never the missing distribution.
    #
    # `uvicorn` is imported unguarded inside `server.main`, so its absence is a
    # hard failure at launch. `watchfiles` sits under a `try/except
    # ModuleNotFoundError`, so its absence is silent instead -- the SSE channel
    # simply stops updating, which is the worse of the two shapes and the reason
    # it is named here rather than left to resolve transitively. `pydantic` is
    # `fastapi`'s own requirement; it is listed so that this list and the
    # manifest stay one declaration instead of two that can drift.
    #
    # `tests/test_forge_gate.py` derives its required-import set from every
    # tracked `.py` under `tests/`, `src/`, `skills/*/scripts/` and
    # `skills/_core/`, so a fifth dependency added to that tree fails the gate
    # the day it lands instead of arriving as an unloadable suite.
    "fastapi",
    "uvicorn",
    "watchfiles",
    "pydantic",
]

# The micromamba release `install` bootstraps, and the SHA-256 of each
# platform's binary in it. A download is checked against this table before it
# is put in place or run, so a changed or substituted binary stops the install
# instead of executing.
#
# Moving the pin is one deliberate, reviewed change to both constants:
#   1. Pick a tag from https://github.com/mamba-org/micromamba-releases/releases.
#   2. List GitHub's digests for its assets:
#        gh api repos/mamba-org/micromamba-releases/releases/tags/<tag> \
#          --jq '.assets[] | "\(.name) \(.digest)"'
#   3. For every platform below, download `micromamba-<platform>` and its
#      `.sha256` file. The local `sha256sum`, that file and GitHub's digest must
#      agree before the digest goes in the table.
#   4. Update MICROMAMBA_VERSION and every entry, then run
#      `pytest tests/test_setup_env_micromamba.py` and a fresh `install`.
MICROMAMBA_VERSION = "2.9.0-0"
MICROMAMBA_SHA256 = {
    "linux-64": "366cd9cd8be14df1ab8ed50352a82111082a36686b2d389fdb79a92c3fafb3e3",
    "linux-aarch64": "9f93b974adcb4d166996af969b6cd371287d1a3e52733704727884d9b74cb7a7",
    "osx-64": "1e71054bb3ac9a076e21f7ec48acfef536f9b3f1408f371a942784bf5ef83d8a",
    "osx-arm64": "ec2a072f028e1a7cf20f3e2e74d5a8127cf5a5f27636375b5359811565f4e5be",
    "win-64": "a6d804394b2418991c4e29562853eaace2f2ce9d9da661a98e74e02e8dbb44b0",
    "win-arm64": "f0da836d2398c00ac0b43e01f7581ba3430224a04405075c39eb3dd78bf0339a",
}
MICROMAMBA_URL = (
    "https://github.com/mamba-org/micromamba-releases/releases/download/"
    "{version}/micromamba-{asset}"
)
#: Ceiling on a download; the largest pinned binary is about 22 MB.
MICROMAMBA_MAX_BYTES = 64 * 1024 * 1024
#: Seconds a connect or a read may stall before the download is abandoned.
MICROMAMBA_TIMEOUT = 60


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def platform_asset() -> str:
    """Return the micromamba release asset suffix for this OS + architecture."""
    system = platform.system()
    machine = platform.machine().lower()
    is_arm = machine in ("aarch64", "arm64")
    if system == "Linux":
        return "linux-aarch64" if is_arm else "linux-64"
    if system == "Windows":
        return "win-arm64" if is_arm else "win-64"
    if system == "Darwin":
        return "osx-arm64" if is_arm else "osx-64"
    raise SystemExit(f"unsupported platform: {system} {machine}")


def detect_cuda() -> bool:
    """True when an NVIDIA GPU driver is reachable (nvidia-smi runs cleanly)."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        subprocess.run(
            [nvidia_smi, "-L"],
            capture_output=True,
            timeout=15,
            check=True,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


# --------------------------------------------------------------------------- #
# micromamba bootstrap
# --------------------------------------------------------------------------- #
def micromamba_exe() -> Path:
    """Path to the project-local micromamba binary (per OS)."""
    return MAMBA_ROOT / "bin" / ("micromamba.exe" if os.name == "nt" else "micromamba")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_pinned(path: Path) -> bool:
    """True when ``path`` is the pinned micromamba binary for this platform."""
    return path.is_file() and _sha256(path) == MICROMAMBA_SHA256[platform_asset()]


def _is_project_local(path: Path) -> bool:
    """True when ``path`` is this project's own bootstrapped binary, however it
    is reached: a PATH entry, an activated environment, a symlink."""
    local = micromamba_exe()
    try:
        return local.exists() and os.path.samefile(path, local)
    except OSError:
        return False


def find_micromamba() -> Path | None:
    """Locate an existing micromamba: PATH first, then project-local, then common homes.

    The project-local binary is the one `install` bootstraps, so it counts only
    when it is the pinned release, however it is reached (PATH, or a home
    install that links to it); any other file there (an older download, a
    replaced binary) is downloaded again rather than run. Any other
    micromamba on PATH or in a home install is the operator's own and is
    used as installed.
    """
    on_path = shutil.which("micromamba")
    if on_path and not _is_project_local(Path(on_path)):
        return Path(on_path)

    if is_pinned(micromamba_exe()):
        return micromamba_exe()
    home = Path.home()
    candidates = [
        home / "micromamba" / "bin" / "micromamba.exe" if os.name == "nt"
        else home / "micromamba" / "bin" / "micromamba",
        home / ".local" / "bin" / "micromamba",
    ]
    for candidate in candidates:
        if candidate.is_file() and not _is_project_local(candidate):
            return candidate
    return None


def _download(url: str, destination: Path) -> str:
    """Stream ``url`` into ``destination``, bounded in size and stall time, and
    return the SHA-256 of the bytes that arrived."""
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(url, timeout=MICROMAMBA_TIMEOUT) as response, \
            destination.open("xb") as out:
        while chunk := response.read(1 << 20):
            received += len(chunk)
            if received > MICROMAMBA_MAX_BYTES:
                raise SystemExit(
                    f"[setup] refusing {url}: larger than {MICROMAMBA_MAX_BYTES} bytes")
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def bootstrap_micromamba() -> Path:
    """Download the pinned micromamba binary for this platform, verified first.

    The download goes to a temporary file beside the target, named for this
    run alone so a second install at the same time cannot write into it, and
    is moved into place only when its SHA-256 matches `MICROMAMBA_SHA256`; a
    mismatch stops the install and leaves nothing behind to run.
    """
    target = micromamba_exe()
    if is_pinned(target):
        return target

    asset = platform_asset()
    expected = MICROMAMBA_SHA256[asset]
    url = MICROMAMBA_URL.format(version=MICROMAMBA_VERSION, asset=asset)
    if target.exists():
        print(f"[setup] replacing {target}: it is not micromamba {MICROMAMBA_VERSION}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    print(f"[setup] downloading micromamba {MICROMAMBA_VERSION} for {asset} ...")
    try:
        actual = _download(url, partial)
        if actual != expected:
            raise SystemExit(
                f"[setup] refusing {url}: its SHA-256 is {actual}, but micromamba "
                f"{MICROMAMBA_VERSION} for {asset} is pinned to {expected}. "
                "Nothing was installed.")
        if os.name != "nt":
            partial.chmod(partial.stat().st_mode | 0o111)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    print(f"[setup] micromamba {MICROMAMBA_VERSION} verified, ready at {target}")
    return target


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def mamba_env() -> dict[str, str]:
    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = str(MAMBA_ROOT)
    return env


def run(mm: Path, args: list[str], env: dict[str, str]) -> None:
    print(f"[setup] $ micromamba {' '.join(args)}")
    subprocess.run([str(mm), "--log-level=warning", *args], env=env, check=True)


def env_exists(name: str) -> bool:
    """True when the named environment's prefix already exists."""
    return (MAMBA_ROOT / "envs" / name).exists()


def conda_torch_packages(cuda: bool) -> list[str]:
    """Hardware-appropriate PyTorch, from conda-forge's CPU/CUDA variants."""
    if cuda:
        return ["pytorch-gpu", "torchvision"]
    return ["pytorch-cpu", "torchvision"]


def cmd_install(args: argparse.Namespace) -> int:
    if args.cuda and args.cpu:
        raise SystemExit("--cuda and --cpu are mutually exclusive")

    cuda = args.cuda or (not args.cpu and detect_cuda())
    kind = "CUDA (GPU)" if cuda else "CPU"
    print(f"[setup] platform={platform_asset()}  torch={kind}")

    mm = find_micromamba() or bootstrap_micromamba()

    conda_packages = CONDA_BASE_PACKAGES + conda_torch_packages(cuda)
    verb = "install" if env_exists(args.name) else "create"
    run(mm, [verb, "-y", "-n", args.name, "-c", "conda-forge", *conda_packages],
        mamba_env())

    # The framework checkout itself, editable: `papersmith` is a real package
    # with a console entry point, and the MCP suites import it directly.
    # Editable rather than a plain install so the environment keeps tracking
    # the checkout instead of freezing a copy of it. Only when PROJECT_ROOT
    # is a Python project: a workspace copy carries no `pyproject.toml` or
    # `setup.py`, so an unconditional install fails there and aborts the
    # ingestion-engine step below.
    if (PROJECT_ROOT / "pyproject.toml").is_file() or (PROJECT_ROOT / "setup.py").is_file():
        run(mm, ["run", "-n", args.name, "python", "-m", "pip", "install", "-e",
                 str(PROJECT_ROOT)], mamba_env())
    else:
        print(f"[setup] skipping editable install: {PROJECT_ROOT} has no "
              "pyproject.toml or setup.py")

    pip_packages = [] if args.no_ingestion else PIP_PACKAGES
    if pip_packages:
        run(mm, ["run", "-n", args.name, "python", "-m", "pip", "install", *pip_packages],
            mamba_env())

    print("\n[setup] done. Activate or run through the environment:")
    print(f"  micromamba run -n {args.name} python skills/paper-ingestion/scripts/extract_pdf.py --list")
    print(f"  micromamba run -n {args.name} python -m pytest tests/")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    mm = find_micromamba()
    env = mamba_env()

    if mm is not None:
        # Best-effort: removing an already-absent env is a no-op that still exits 0.
        subprocess.run(
            [str(mm), "remove", "-y", "-n", args.name, "--all"],
            env=env,
            check=False,
        )
    else:
        env_prefix = MAMBA_ROOT / "envs" / args.name
        if env_prefix.exists():
            shutil.rmtree(env_prefix)

    if args.full and MAMBA_ROOT.exists():
        print(f"[setup] removing {MAMBA_ROOT}")
        shutil.rmtree(MAMBA_ROOT, ignore_errors=True)

    print(f"[clean] environment '{args.name}' removed.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    mm = find_micromamba()
    print(f"micromamba: {mm or 'not found (run install to bootstrap)'}")
    print(f"CUDA detected: {detect_cuda()}")
    print(f"env prefix: {MAMBA_ROOT / 'envs' / args.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision/clean the papersmith micromamba environment.")
    parser.add_argument("--name", default=ENV_NAME, help="environment name (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="create/update the environment")
    p_install.add_argument("--cpu", action="store_true", help="force CPU PyTorch")
    p_install.add_argument("--cuda", action="store_true", help="force CUDA PyTorch")
    p_install.add_argument("--no-ingestion", action="store_true",
                           help="skip docling (the heavy ingestion engine); the pypdfium2 fast path stays")

    sub.add_parser("clean", help="remove the environment").add_argument(
        "--full", action="store_true", help="also delete bootstrapped micromamba")

    sub.add_parser("status", help="show detected hardware and micromamba location")

    args = parser.parse_args()
    if args.command == "install":
        return cmd_install(args)
    if args.command == "clean":
        return cmd_clean(args)
    if args.command == "status":
        return cmd_status(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
