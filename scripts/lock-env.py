#!/usr/bin/env python3
"""Refresh the locked environments built from ``env/environment.yml`` (issue #58).

Maintainer-only: it needs ``conda-lock`` and network access, which a workspace
never does. ``scripts/setup_env.py install`` reads the locks this writes; it
never solves the source files itself.

    python3 scripts/lock-env.py lock [--variant cpu|cuda|rocm ...] [--conda-lock <path>] [--micromamba <path>]
    python3 scripts/lock-env.py check

``lock`` solves each variant for its platforms and records, in
``env/locks.json``, the sha256 of every source file it was solved from.
``check`` exits 1 when a source changed since its lock was written, so an edit
to ``env/*.yml`` without a refresh fails the suite (tests/test_env_locks.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "env"
RECORD = ENV / "locks.json"
#: The CUDA version the cuda variant is solved for: builds for it run on any
#: NVIDIA driver from the 570 series on. The other variants are solved without CUDA,
#: so no package resolves to a CUDA build there.
CUDA_VERSION = "12.8"

#: variant -> (source files, platforms). The ROCm variant locks no torch: it comes
#: from AMD's pinned index (skills/_core/gpu/gpu_probe.py). Ingestion's pip layer
#: (env/ingestion.txt) is installed on top of every variant and is not locked here.
VARIANTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "cpu": (("environment.yml", "torch-cpu.yml"), ("linux-64", "osx-64", "osx-arm64", "win-64")),
    "cuda": (("environment.yml", "torch-cuda.yml"), ("linux-64", "win-64")),
    "rocm": (("environment.yml",), ("linux-64",)),
}


def lock_path(variant: str) -> Path:
    # micromamba reads a file as a conda-lock lockfile only when its name ends in `-lock.yml`.
    return ENV / f"{variant}.conda-lock.yml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(variant: str) -> dict[str, str]:
    return {name: sha256(ENV / name) for name in VARIANTS[variant][0]}


def read_record() -> dict:
    try:
        data = json.loads(RECORD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "variants": {}}
    return data if isinstance(data, dict) and isinstance(data.get("variants"), dict) else {"schema": 1, "variants": {}}


def stale(record: dict | None = None) -> list[str]:
    """One line per variant whose lock is missing or older than its sources."""
    record = read_record() if record is None else record
    problems = []
    for variant, (_, platforms) in VARIANTS.items():
        entry = record["variants"].get(variant)
        if not lock_path(variant).is_file():
            problems.append(f"{variant}: {lock_path(variant).relative_to(ROOT)} is missing")
        elif not isinstance(entry, dict) or entry.get("inputs") != inputs(variant):
            problems.append(f"{variant}: env/*.yml changed since its lock; run `python3 scripts/lock-env.py lock "
                            f"--variant {variant}`")
        elif entry.get("platforms") != list(platforms):
            problems.append(f"{variant}: locked for {entry.get('platforms')}, expected {list(platforms)}")
    return problems


def cmd_lock(args: argparse.Namespace) -> int:
    conda_lock = args.conda_lock or shutil.which("conda-lock")
    if not conda_lock:
        print("conda-lock is not on PATH; pass --conda-lock <path> (docs/releasing.md)", file=sys.stderr)
        return 2
    record = read_record()
    for variant in args.variant or list(VARIANTS):
        files, platforms = VARIANTS[variant]
        command = [conda_lock, "lock", "--lockfile", str(lock_path(variant))]
        if args.micromamba:
            command += ["--micromamba", "--conda", args.micromamba]
        for name in files:
            command += ["-f", str(ENV / name)]
        for platform in platforms:
            command += ["-p", platform]
        command += ["--with-cuda", CUDA_VERSION] if variant == "cuda" else ["--without-cuda"]
        print(f"locking {variant} for {', '.join(platforms)}", flush=True)
        if subprocess.run(command, cwd=ENV).returncode != 0:
            print(f"conda-lock failed for {variant}; its previous lock is kept", file=sys.stderr)
            return 1
        record["variants"][variant] = {"inputs": inputs(variant), "platforms": list(platforms),
                                       "lockfile": lock_path(variant).name,
                                       "cuda": CUDA_VERSION if variant == "cuda" else None}
        RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    problems = stale()
    for line in problems:
        print(line)
    if not problems:
        print("locks: current")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lock-env.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    lock = sub.add_parser("lock", help="solve the locks with conda-lock")
    lock.add_argument("--variant", action="append", choices=list(VARIANTS))
    lock.add_argument("--conda-lock", default=None, help="path to the conda-lock executable")
    lock.add_argument("--micromamba", default=None, help="solve with this micromamba binary")
    lock.set_defaults(func=cmd_lock)
    check = sub.add_parser("check", help="exit 1 when a lock is older than its sources")
    check.set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
