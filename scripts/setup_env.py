#!/usr/bin/env python3
"""Cross-platform environment provisioning via micromamba.

One script, every OS (Linux / macOS / Windows). It creates a single isolated
environment (`papersmith`) that holds every Python dependency the forge needs,
and installs the hardware-appropriate build of PyTorch (CUDA when an NVIDIA GPU
is present, AMD's ROCm wheels when an AMD GPU with a supported gfx target is,
CPU otherwise) plus the `llama-server` OCR backend — pulled from conda-forge
rather than Homebrew, so the same command works everywhere.

What it installs
    One dependency specification (issue #58): `env/environment.yml` plus the
    torch build's file (`env/torch-cpu.yml`, `env/torch-cuda.yml`), locked by
    conda-lock into `env/<kind>.conda-lock.yml` (`scripts/lock-env.py`,
    docs/releasing.md). `install` builds the environment from the lock of its
    torch kind, so every machine of a platform gets the same packages:
    conda-forge: python=3.12, pytest, numpy, pypdfium2, kagglesdk, llama.cpp
                 (provides llama-server), the notebook runners, the Paper
                 Command Center's server, and torch -- `pytorch-gpu` on CUDA
                 machines, else `pytorch-cpu` (none in the ROCm lock).
    pip:         on an AMD GPU whose gfx target is in the probe's ROCm set
                 (`skills/_core/gpu/gpu_probe.py`, `ROCM_SUPPORTED_TARGETS`),
                 AMD's ROCm builds of torch and torchvision with the
                 `device-<gfx>` extra from https://stable.repo.amd.com/rocm/whl-next/
                 (the ROCm runtime ships in the wheels: no system ROCm needed);
                 this project itself, editable (`pip install -e .`), and the
                 paper-ingestion heavy engine, pinned in `env/ingestion.txt`:
                 docling (MIT), plus mlx-vlm (MIT) on Apple Silicon so its
                 formula model runs on the GPU. Every one is license-unrestricted.
                 pypdfium2 (Apache-2.0/BSD-3) is the fast path and comes from the
                 lock, so `--no-ingestion` still ingests digital PDFs. Marker is
                 no longer installed: its weights are free only below USD 5M in
                 funding or revenue; `pip install marker-pdf==2.0.0` opts in.
    A platform no lock covers (`env/locks.json`: today linux-aarch64 and
    win-arm64, and CUDA on macOS) is solved live from the same source files,
    with a warning that the result is not reproducible.

Usage
    python3 scripts/setup_env.py install          # detect hardware, provision
    python3 scripts/setup_env.py install --cpu    # force CPU torch
    python3 scripts/setup_env.py install --cuda   # force CUDA torch
    python3 scripts/setup_env.py install --rocm   # force AMD ROCm wheels for the detected gfx target
    python3 scripts/setup_env.py clean            # remove the environment
    python3 scripts/setup_env.py clean --full     # also remove bootstrapped micromamba

The micromamba it bootstraps is a pinned release (`MICROMAMBA_VERSION`), checked
against a SHA-256 kept here (`MICROMAMBA_SHA256`) before it is put in place or
run. The comment above those constants is the procedure for moving the pin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

#: The dependency source and its locks (scripts/lock-env.py writes them).
ENV_DIR = PROJECT_ROOT / "env"
#: Each torch kind's source file beside `environment.yml`; ROCm locks no torch.
TORCH_SOURCES = {"cpu": "torch-cpu.yml", "cuda": "torch-cuda.yml", "rocm": None}
#: Paper ingestion's pinned pip layer, skipped by `--no-ingestion`.
INGESTION_REQUIREMENTS = ENV_DIR / "ingestion.txt"

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


GPU_PROBE = Path("skills") / "_core" / "gpu" / "gpu_probe.py"


def load_gpu_probe():
    """The kit's shared GPU probe, or None when this copy carries none."""
    import importlib.util

    path = PROJECT_ROOT / GPU_PROBE
    try:
        spec = importlib.util.spec_from_file_location("papersmith_setup_gpu_probe", path)
        if spec is None or spec.loader is None or not path.is_file():
            return None
        module = importlib.util.module_from_spec(spec)
        previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:  # no __pycache__ inside the kit's skills/ tree
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        return module
    except Exception:
        return None


def gpu_facts() -> dict:
    """Vendor and AMD gfx targets from the probe (sysfs only, no subprocess);
    no GPU when the probe is missing or fails."""
    probe = load_gpu_probe()
    if probe is None:
        return {"vendor": "none", "gfx_targets": []}
    try:
        return probe.access()
    except Exception:
        return {"vendor": "none", "gfx_targets": []}


def torch_choice(args: argparse.Namespace, facts: dict) -> tuple[str, str | None, str]:
    """``(kind, gfx, why)``: ``cuda``, ``rocm`` (with its gfx target) or ``cpu``.

    NVIDIA wins as before; an AMD gfx target in the probe's ROCm set gets the
    ROCm wheels; ``--rocm`` forces them for the detected target, ``--cpu``
    forbids every GPU build."""
    rocm = getattr(args, "rocm", False)
    if sum(bool(flag) for flag in (args.cpu, args.cuda, rocm)) > 1:
        raise SystemExit("--cpu, --cuda and --rocm are mutually exclusive")
    if args.cpu:
        return "cpu", None, "--cpu"
    if args.cuda:
        return "cuda", None, "--cuda"
    targets = list(facts.get("gfx_targets") or [])
    probe = load_gpu_probe()
    supported = set(getattr(probe, "ROCM_SUPPORTED_TARGETS", ()))
    if rocm:
        if not targets:
            raise SystemExit("--rocm needs an AMD GPU the kernel reports (no gfx target in "
                             "/sys/class/kfd/kfd/topology); is the amdgpu driver loaded?")
        return "rocm", targets[0], f"--rocm for {targets[0]}"
    if detect_cuda():
        return "cuda", None, "nvidia-smi found an NVIDIA GPU"
    for target in targets:
        if target in supported:
            return "rocm", target, f"AMD {target} is in the ROCm 10.1 wheel set"
    if targets:
        url = getattr(probe, "ROCM_COMPATIBILITY_URL", "the ROCm compatibility matrix")
        return "cpu", None, (f"AMD {', '.join(targets)} is not in the ROCm 10.1 wheel set ({url}); "
                             "pass --rocm to install the wheels anyway")
    return "cpu", None, "no NVIDIA or supported AMD GPU found"


def rocm_pip_args(gfx: str) -> list[str]:
    probe = load_gpu_probe()
    if probe is None:
        raise SystemExit(f"[setup] --rocm needs {GPU_PROBE} (run `smith upgrade` to restore the kit)")
    return probe.rocm_pip_args(gfx)


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


def lockfile(kind: str) -> Path:
    # micromamba reads a file as a conda-lock lockfile only when its name ends in `-lock.yml`.
    return ENV_DIR / f"{kind}.conda-lock.yml"


def locked_platforms(kind: str) -> list[str]:
    """The platforms `env/locks.json` records for this kind's lock; none when
    the record is missing or unreadable."""
    try:
        record = json.loads((ENV_DIR / "locks.json").read_text(encoding="utf-8"))
        platforms = record["variants"][kind]["platforms"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [p for p in platforms if isinstance(p, str)] if isinstance(platforms, list) else []


def environment_args(kind: str, asset: str) -> list[str]:
    """The `micromamba create` file arguments for this kind on this platform:
    its lock when the lock covers the platform, else the source files solved
    live (with a warning)."""
    lock = lockfile(kind)
    if asset in locked_platforms(kind) and lock.is_file():
        print(f"[setup] environment: {lock.relative_to(PROJECT_ROOT)} ({asset})")
        return ["-f", str(lock), "--category", "main"]
    sources = [ENV_DIR / "environment.yml"]
    if TORCH_SOURCES[kind]:
        sources.append(ENV_DIR / TORCH_SOURCES[kind])
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise SystemExit(f"[setup] {missing[0]} is missing; run `smith upgrade` to restore the kit")
    names = " + ".join(str(path.relative_to(PROJECT_ROOT)) for path in sources)
    print(f"[setup] WARNING: {asset} is not locked for the {kind} build (env/locks.json); "
          f"solving {names} live, so this environment is not reproducible")
    args: list[str] = []
    for path in sources:
        args += ["-f", str(path)]
    return args


#: Written inside the environment after it is built: which kind and which file
#: bytes built it, so `install` does not rebuild an environment that already
#: matches its lock.
STAMP = Path("conda-meta") / "papersmith-environment.json"


def environment_fingerprint(kind: str, files: list[str]) -> dict:
    """The kind plus the sha256 of every file the build reads (lock or sources)."""
    paths = [Path(arg) for arg, before in zip(files, ["", *files]) if before == "-f"]
    return {"kind": kind, "files": {path.name: _sha256(path) for path in paths}}


def read_stamp(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_stamp(path: Path, fingerprint: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fingerprint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:  # the environment is built; only the next install's shortcut is lost
        print(f"[setup] could not record the build in {path} ({exc}); the next install rebuilds")


def cmd_install(args: argparse.Namespace) -> int:
    kind, gfx, why = torch_choice(args, gpu_facts())
    label = {"cuda": "CUDA (GPU)", "rocm": f"ROCm ({gfx})", "cpu": "CPU"}[kind]
    print(f"[setup] platform={platform_asset()}  torch={label}  ({why})")

    mm = find_micromamba() or bootstrap_micromamba()

    files = environment_args(kind, platform_asset())
    fingerprint = environment_fingerprint(kind, files)
    stamp = MAMBA_ROOT / "envs" / args.name / STAMP
    existed = env_exists(args.name)
    if existed and read_stamp(stamp) == fingerprint:
        print(f"[setup] the environment '{args.name}' already matches its lock; not rebuilt")
    else:
        if existed:
            # `create -y` over an existing environment removes it and builds it
            # again, so it holds exactly the lock's packages (`install -f <lock>`
            # kept a conda torch an earlier build left there, measured with
            # micromamba 2.9.0 on 2026-11-24). Because it removes the working
            # environment first, every package is fetched into a throwaway prefix
            # before: a failed download (offline, a dropped mirror) stops here and
            # leaves the environment as it was. Packages added by hand are not kept.
            print(f"[setup] rebuilding the existing environment '{args.name}' from the lock")
            staging = MAMBA_ROOT / "envs" / f".{args.name}-download"
            try:
                run(mm, ["create", "-y", "--download-only", "-p", str(staging), *files], mamba_env())
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        run(mm, ["create", "-y", "-n", args.name, *files], mamba_env())
        write_stamp(stamp, fingerprint)

    if kind == "rocm":
        print(f"[setup] installing AMD's ROCm PyTorch wheels for {gfx} (runtime bundled; "
              "leave HSA_OVERRIDE_GFX_VERSION unset)")
        run(mm, ["run", "-n", args.name, "python", "-m", "pip", "install", *rocm_pip_args(gfx)], mamba_env())

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

    # After any torch, so docling resolves against the one already installed.
    if not args.no_ingestion:
        run(mm, ["run", "-n", args.name, "python", "-m", "pip", "install", "-r",
                 str(INGESTION_REQUIREMENTS)], mamba_env())

    # The environment keeps its files; the downloaded tarballs and the index
    # cache only weigh on the workspace's disk once it is built. The extracted
    # packages stay, so the environment can be built again offline, and a
    # cleanup that fails never fails an environment that is already built.
    try:
        run(mm, ["clean", "--tarballs", "--index-cache", "--locks", "--yes"], mamba_env())
    except subprocess.CalledProcessError as exc:
        print(f"[setup] could not clean the package downloads (exit {exc.returncode}); "
              "the environment is built and usable")

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
    facts = gpu_facts()
    print(f"GPU vendor: {facts.get('vendor')}  AMD targets: {', '.join(facts.get('gfx_targets') or []) or '-'}")
    print(f"env prefix: {MAMBA_ROOT / 'envs' / args.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision/clean the papersmith micromamba environment.")
    parser.add_argument("--name", default=ENV_NAME, help="environment name (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="create/update the environment")
    p_install.add_argument("--cpu", action="store_true", help="force CPU PyTorch")
    p_install.add_argument("--cuda", action="store_true", help="force CUDA PyTorch")
    p_install.add_argument("--rocm", action="store_true",
                           help="force AMD's ROCm PyTorch wheels for the detected gfx target")
    p_install.add_argument("--no-ingestion", action="store_true",
                           help="skip env/ingestion.txt (docling, the heavy ingestion engine); "
                                "the pypdfium2 fast path stays")

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
