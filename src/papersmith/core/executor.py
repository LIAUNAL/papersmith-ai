"""Resolve execution profiles and dispatch local or remote jobs."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..bridges.python import interpreter_for, mapped_returncode, script_environment
from ..core.exit_codes import EXECUTION_ERROR, SUCCESS, USER_ERROR
from ..errors import ExecutionError, UserError
from . import config, ledger
from .target import ssh_destination


def _job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"job-{stamp}-{os.getpid()}"


#: Placeholders naming the implementation target a profile runs against.
#: `{target}` is the target's workspace-relative directory and
#: `{target_python}` its own virtualenv's interpreter. A profile naming
#: neither never resolves a target, so explicit profiles keep working as
#: written. `{paper_slug}` (the workspace folder name) is unchanged.
TARGET_PLACEHOLDERS = ("{target}", "{target_python}")
IMPLEMENTATIONS = "implementations"


def _substitute(value: str, *, paper_slug: str, job_id: str, shard_value: Any = None,
                target: dict[str, str] | None = None) -> str:
    result = value.replace("{paper_slug}", paper_slug).replace("{job_id}", job_id)
    if target is not None:
        result = (result.replace("{target_python}", target["python"])
                  .replace("{target}", target["path"]))
    if shard_value is not None:
        result = result.replace("{shard_value}", str(shard_value))
    return result


def _target_markers(profile: dict) -> set[str]:
    """Which of `TARGET_PLACEHOLDERS` the profile's entrypoint and env name."""
    texts = [str(profile.get("entrypoint", ""))]
    texts += [str(item) for item in (profile.get("env_vars") or {}).values()]
    return {marker for marker in TARGET_PLACEHOLDERS if any(marker in text for text in texts)}


#: How profiles written by `smith init` before 0.14.0 named the target.
#: `{paper_slug}` is the workspace folder name, which names no implementation
#: unless the target happens to share it.
LEGACY_TARGET = IMPLEMENTATIONS + "/{paper_slug}"


def _legacy_target_problem(root: Path, profile: dict) -> str | None:
    """Why a pre-0.14.0 profile's `implementations/{paper_slug}` is wrong here.

    `None` when the profile does not name it, or when that directory exists,
    so a profile that works keeps working exactly as written.
    """
    texts = [str(profile.get("entrypoint", ""))]
    texts += [str(item) for item in (profile.get("env_vars") or {}).values()]
    if not any(LEGACY_TARGET in text for text in texts):
        return None
    if (root / IMPLEMENTATIONS / root.name).is_dir():
        return None
    return (f"this profile names {LEGACY_TARGET}, which resolves to "
            f"{IMPLEMENTATIONS}/{root.name}/ and does not exist: {{paper_slug}} is the "
            "workspace folder name, not an implementation target. Edit papersmith.yaml "
            "to name {target} instead (and {target_python} -m pytest rather than a bare "
            "pytest), as `smith init` writes from 0.14.0 on")


def _venv_python(directory: Path) -> Path:
    if os.name == "nt":
        return directory / ".venv" / "Scripts" / "python.exe"
    return directory / ".venv" / "bin" / "python"


def resolve_target(root: Path, name: str | None, *, need_python: bool = True) -> dict[str, str]:
    """The implementation a profile's `{target}` placeholders name.

    `name` (from `--implementation`) picks one directory of
    `implementations/`; without it the directory must be the only one there.
    When the profile names `{target_python}` (`need_python`), the target's own
    `.venv` interpreter must exist: running `pytest` from PATH would test with
    whatever environment the caller happens to have. A remote profile naming
    only `{target}` runs a remote interpreter and needs no local venv.
    Raises :class:`UserError` naming the fix, and nothing is dispatched.
    """
    directory = root / IMPLEMENTATIONS
    try:
        candidates = sorted(p.name for p in directory.iterdir()
                            if p.is_dir() and not p.name.startswith("."))
    except OSError:
        candidates = []
    if name is not None:
        if name not in candidates:
            raise UserError(
                f"--implementation {name!r} is not a directory of {IMPLEMENTATIONS}/ "
                f"(found: {', '.join(candidates) or 'none'})")
        chosen = name
    elif len(candidates) == 1:
        chosen = candidates[0]
    elif not candidates:
        raise UserError(
            f"this profile runs against an implementation target, and {IMPLEMENTATIONS}/ "
            "holds none; land one there first (proposal-implementation, step 1)")
    else:
        raise UserError(
            f"this profile runs against an implementation target, and {IMPLEMENTATIONS}/ "
            f"holds several ({', '.join(candidates)}); pass --implementation <name>")
    python = _venv_python(directory / chosen)
    if need_python and not python.is_file():
        raise UserError(
            f"{IMPLEMENTATIONS}/{chosen} has no .venv interpreter ({python.relative_to(root).as_posix()}); "
            "build it with the implementation skill's `env` command first")
    return {"name": chosen, "path": f"{IMPLEMENTATIONS}/{chosen}", "python": str(python)}


def _profile_jobs(root: Path, profile_name: str, target_name: str, profile: dict,
                  *, shard: int | None, job_id: str,
                  implementation: dict[str, str] | None = None) -> list[dict[str, Any]]:
    entrypoint = profile.get("entrypoint")
    if not isinstance(entrypoint, str):
        raise UserError(f"execution_profiles.{profile_name}.entrypoint must be a string")
    sharding = profile.get("sharding") or {}
    enabled = bool(sharding.get("enabled", False))
    values = list(sharding.get("values", [])) if enabled else [None]
    if shard is not None:
        if not enabled:
            raise UserError(f"profile {profile_name} does not enable sharding")
        if shard < 0 or shard >= len(values):
            raise UserError(f"shard index {shard} is outside the profile's {len(values)} values")
        values = [values[shard]]
    jobs: list[dict[str, Any]] = []
    for value in values:
        rendered = _substitute(entrypoint, paper_slug=root.name, job_id=job_id, shard_value=value,
                               target=implementation)
        command = shlex.split(rendered)
        if value is not None and sharding.get("parameter"):
            command.extend([str(sharding["parameter"]), str(value)])
        env = {
            str(key): _substitute(str(item), paper_slug=root.name, job_id=job_id,
                                  shard_value=value, target=implementation)
            for key, item in (profile.get("env_vars") or {}).items()
        }
        jobs.append({
            "command": command,
            "command_text": shlex.join(command),
            "entrypoint": rendered,
            "env": env,
            "shard_value": value,
            "target": target_name,
        })
    return jobs


def _local_job(root: Path, profile_name: str, job_id: str, job: dict[str, Any], profile: dict) -> int:
    environment = script_environment(job["env"])
    environment.update({
        "PAPERSMITH_PROFILE": profile_name,
        "PAPERSMITH_JOB_ID": job_id,
    })
    if job["shard_value"] is not None:
        environment["PAPERSMITH_SHARD"] = str(job["shard_value"])
    timeout = profile.get("timeout_seconds")
    try:
        result = subprocess.run(
            job["command"], cwd=root, env=environment,
            capture_output=False, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return EXECUTION_ERROR
    except OSError:
        return EXECUTION_ERROR
    return SUCCESS if result.returncode == 0 else EXECUTION_ERROR


def _env_is_provisioned(root: Path) -> bool:
    env_dir = root / ".micromamba" / "envs" / "papersmith"
    mamba_name = "micromamba.exe" if os.name == "nt" else "micromamba"
    mamba_local = root / ".micromamba" / "bin" / mamba_name
    fallback_local = root / ".micromamba" / "bin" / "micromamba"
    return env_dir.is_dir() and (
        mamba_local.is_file()
        or fallback_local.is_file()
        or shutil.which("micromamba") is not None
    )


def _prompt_env_if_interactive(root: Path, profile_name: str) -> None:
    if _env_is_provisioned(root):
        return

    script = root / "scripts" / "setup_env.py"
    if not script.is_file():
        return

    if sys.stdin.isatty():
        sys.stderr.write(
            f"\n[!] Profile '{profile_name}' uses Kaggle remote execution.\n"
            "    The isolated papersmith micromamba environment is not yet installed.\n"
            "Would you like to provision it now? [y/N]: "
        )
        sys.stderr.flush()
        try:
            line = sys.stdin.readline()
            reply = line.strip().lower() if line else "n"
        except (OSError, KeyboardInterrupt):
            reply = "n"
        if reply in {"y", "yes"}:
            sys.stderr.write("\n[setup] Provisioning micromamba environment via scripts/setup_env.py install ...\n")
            py = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
            proc = subprocess.run([py, str(script), "install"], cwd=root, check=False)
            if proc.returncode == 0:
                sys.stderr.write("[setup] Environment provisioning complete.\n\n")
            else:
                sys.stderr.write("[setup] Warning: environment provisioning failed; continuing with fallback interpreter.\n\n")
        else:
            sys.stderr.write(
                "[note] Continuing with host interpreter. To install the isolated environment later:\n"
                "       smith env install  (or python3 scripts/setup_env.py install)\n\n"
            )


def _remote_command(root: Path, job: dict[str, Any], target: dict, *, consent: str | None) -> list[str]:
    script = root / "skills" / "remote-execution" / "scripts" / "remote_cli.py"
    entrypoint = None
    for token in shlex.split(job["entrypoint"]):
        if token.startswith("-") or token in {"python", "python3", "pytest", "papermill"}:
            continue
        candidate = Path(token)
        if candidate.suffix in {".py", ".ipynb"}:
            entrypoint = candidate if candidate.is_absolute() else root / candidate
            break
    if entrypoint is None:
        entrypoint = root / "runner.ipynb"
    interpreter = interpreter_for(root, prefer_micromamba=True)
    command = [
        *interpreter, os.fspath(script), "submit",
        "--target", str(root), "--entrypoint", str(entrypoint),
        "--backend", str(target.get("backend", "kaggle")),
    ]
    if job["shard_value"] is not None:
        command.extend(["--unit", str(job["shard_value"])])
    if consent:
        command.extend(["--consent", consent])
    return command


def _slurm_command(job: dict[str, Any], target: dict) -> list[str]:
    host = ssh_destination(target.get("host"), missing_message="remote-ssh target requires host")
    command = ["sbatch"]
    for key, flag in (("partition", "--partition"), ("walltime", "--time")):
        if target.get(key):
            command.extend([flag, str(target[key])])
    command.extend(["--wrap", job["command_text"]])
    # ssh joins its remote arguments with spaces and hands them to the remote
    # shell, so the sbatch argv is quoted as ONE string: --wrap's command text
    # stays a single argument and its metacharacters stay inert (#82).
    return ["ssh", "--", host, shlex.join(command)]


def run_profile(workspace: str | Path, profile_name: str, *, target_override: str | None = None,
                dry_run: bool = False, shard: int | None = None,
                consent: str | None = None,
                implementation: str | None = None) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    yaml = config.load_papersmith_yaml(root)
    profiles = yaml["execution_profiles"]
    if profile_name not in profiles:
        raise UserError(f"unknown execution profile: {profile_name}")
    profile = profiles[profile_name]
    targets = yaml["compute_targets"]["targets"]
    target_name = target_override or profile.get("target") or yaml["compute_targets"]["default"]
    if target_name not in targets:
        raise UserError(f"unknown compute target: {target_name}")
    target = targets[target_name]
    job_id = _job_id()
    resolution: dict[str, Any] | None = None
    resolved: dict[str, str] | None = None
    markers = _target_markers(profile)
    legacy = _legacy_target_problem(root, profile)
    if legacy is not None:
        if not dry_run:
            raise UserError(legacy)
        resolution = {"status": "unresolved", "reason": legacy}
    elif markers:
        try:
            resolved = resolve_target(root, implementation,
                                      need_python="{target_python}" in markers)
            resolution = {"status": "resolved", **resolved}
        except UserError as error:
            # A dry run plans and dispatches nothing, so it states what would
            # refuse instead of refusing; a real run refuses before any job
            # starts or any ledger row is written.
            if not dry_run:
                raise
            resolution = {"status": "unresolved", "reason": str(error)}
    jobs = _profile_jobs(root, profile_name, target_name, profile, shard=shard, job_id=job_id,
                         implementation=resolved)
    provider = target["provider"]
    results: list[dict[str, Any]] = []
    for job in jobs:
        command: list[str] | None = None
        if provider == "local":
            if dry_run:
                code = SUCCESS
                command = job["command"]
            else:
                code = _local_job(root, profile_name, job_id, job, profile)
        elif provider == "kaggle":
            command = _remote_command(root, job, target, consent=consent)
            if dry_run:
                code = SUCCESS
            else:
                _prompt_env_if_interactive(root, profile_name)
                command = _remote_command(root, job, target, consent=consent)
                try:
                    # remote_cli.py is a kit script under the workspace's skills/.
                    # The ssh branch below needs no such environment: ssh does
                    # not forward it, and nothing runs locally but ssh itself.
                    child = subprocess.run(command, cwd=root, env=script_environment(),
                                           check=False)
                    code = mapped_returncode(child)
                except OSError:
                    code = EXECUTION_ERROR
        elif provider == "remote-ssh":
            command = _slurm_command(job, target)
            if dry_run:
                code = SUCCESS
            else:
                try:
                    child = subprocess.run(command, cwd=root, check=False)
                    code = mapped_returncode(child)
                except OSError:
                    code = EXECUTION_ERROR
        else:
            raise UserError(f"unsupported target provider: {provider}")
        event = {
            "profile": profile_name,
            "target": target_name,
            "provider": provider,
            "job_id": job_id,
            "shard_value": job["shard_value"],
            "dry_run": dry_run,
            "exit": code,
            "command": command or job["command"],
        }
        if resolution is not None:
            event["target_resolution"] = resolution
        ledger.append(root, event)
        results.append(event)
    status = "ok" if all(item["exit"] == 0 for item in results) else "failed"
    return {"status": status, "job_id": job_id, "profile": profile_name,
            "target": target_name, "jobs": results}


def print_result(result: dict[str, Any], *, dry_run: bool) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))
    if dry_run:
        print("dry-run: no job was dispatched", file=sys.stderr)


def register(subparsers) -> None:
    parser = subparsers.add_parser("run", help="run an execution profile")
    parser.add_argument("profile_name")
    parser.add_argument("--target", default=None, help="override the profile's compute target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shard", type=int, default=None)
    parser.add_argument("--consent", default=None, help="remote submission consent token")
    parser.add_argument("--implementation", default=None, metavar="<name>",
                        help="the implementations/ directory {target} and {target_python} "
                             "name (default: the only one there)")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    result = run_profile(
        args.directory, args.profile_name, target_override=args.target,
        dry_run=args.dry_run, shard=args.shard, consent=args.consent,
        implementation=args.implementation,
    )
    print_result(result, dry_run=args.dry_run)
    return SUCCESS if result["status"] == "ok" else EXECUTION_ERROR
