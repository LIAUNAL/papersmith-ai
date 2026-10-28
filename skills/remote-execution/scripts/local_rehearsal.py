#!/usr/bin/env python3
"""The local rehearsal `remote_cli preflight` runs: the job's smoke, here,
under the conditions a worker gives it, in seconds instead of a remote round.

A remote rehearsal costs a clone, an install, a queue and a slice of quota,
and the defects it found most often needed none of those to show: a smoke
that never wrote `shard.json`, a stamp missing a field the job requires, a
commit read with `git rev-parse` on a worker that only has `.git/HEAD`. So
this module reproduces what the worker sees, and nothing more:

- the job's code is materialized the way the runner does it, by the runner's
  own functions (`runner_bootstrap.py`): unpacked from the job's code bundle
  when it carries one -- so there is no git metadata beyond `.git/HEAD` --
  and otherwise sparse-cloned at the pin from the target itself;
- the session directory is a fresh scratch directory OUTSIDE the target, so
  nothing in the target's or the workspace's own tree is reachable by a
  relative path the worker would not have either;
- the smoke block is selected and called by the runner's own `invoke()`
  (`runner_invoke.py`) with `mode` set to `smoke`, under the target's own
  interpreter, with a minimal environment: `PATH`, `HOME`, the clone's `src`
  on `PYTHONPATH`, `FORGE_CLONE_ROOT`/`FORGE_CLONE_COMMIT`, and whatever
  `invoke()` itself exports (`FORGE_RUN_MODE`, `FORGE_INPUT_DATASETS` with
  every declared input unattached, `FORGE_SESSION_DEADLINE` when the service
  declares a session limit);
- the run has a time budget, and the `shard.json` it leaves is judged by the
  same `shard_io.completeness()` `smoke record` uses.

It never contacts a service, never reads a credential, and installs nothing:
the target's interpreter is expected to hold the target's dependencies, as it
does for every implementation stage.

Stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SESSION_DIRNAME = "session"
DRIVER_FILENAME = "rehearse.py"
RUN_CONFIG_FILENAME = "run-config.json"
SHARD_FILENAME = "shard.json"
#: The environment names a rehearsal child inherits; everything else is the
#: runner's own handoff, composed below.
ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
DEFAULT_TIMEOUT_SECONDS = 600
OUTPUT_TAIL_CHARS = 2000


def _load_asset(module_name: str, filename: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, ASSETS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BOOTSTRAP = _load_asset("remote_execution_runner_bootstrap", "runner_bootstrap.py")
INVOKE = _load_asset("remote_execution_runner_invoke", "runner_invoke.py")

#: What the child runs: the runner's own `invoke()` over the scratch
#: session's run-config, with the clone's `src` first on `sys.path`, exactly
#: as cell 0 leaves it for cell 1.
DRIVER_SOURCE = '''\
import importlib.util
import json
import sys
from pathlib import Path

invoke_path, base, clone_src = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, clone_src)
spec = importlib.util.spec_from_file_location("forge_runner_invoke", invoke_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run_config = json.loads((base / "run-config.json").read_text(encoding="utf-8"))
module.invoke(run_config, base_dir=base)
'''


class RehearsalError(Exception):
    """The rehearsal could not even be set up (no smoke block, no code)."""


def target_interpreter(target: Path) -> Path:
    """The target's own `.venv` interpreter, where the implementation skills
    create it."""
    if os.name == "nt":
        return target / ".venv" / "Scripts" / "python.exe"
    return target / ".venv" / "bin" / "python"


def rehearsal_config(
    run_config: Mapping[str, Any],
    *,
    smoke_kwargs: Mapping[str, Any] | None = None,
    session_limit_seconds: int | None = None,
) -> dict:
    """The run-config a worker would receive for a smoke submission: `mode`
    `smoke`, and the service's session limit when it declares one (what
    `submit` adds). `smoke_kwargs`, when given, replace the smoke block's
    kwargs -- a cheaper local scale the target declared."""
    config = json.loads(json.dumps(dict(run_config)))
    smoke = (config.get("run") or {}).get("smoke")
    if not isinstance(smoke, dict) or not smoke:
        raise RehearsalError(
            "the job declares no smoke block (run.smoke): generate it with "
            "--smoke-module/--smoke-function or --smoke-notebook")
    if smoke_kwargs is not None:
        if "notebook" in smoke:
            raise RehearsalError("--local-smoke-kwargs applies to a smoke callable, "
                                 "not to a smoke notebook")
        smoke["kwargs"] = dict(smoke_kwargs)
    config["mode"] = "smoke"
    if session_limit_seconds:
        config[INVOKE.SESSION_LIMIT_KEY] = int(session_limit_seconds)
    return config


def materialize(run_config: Mapping[str, Any], job_dir: Path, target: Path,
                session: Path) -> tuple[Path, str]:
    """The job's code in `<session>/clone`, the way the runner materializes
    it, and how it got there."""
    if run_config.get("codeBundle") is not None:
        shutil.copy2(job_dir / BOOTSTRAP.CODE_BUNDLE_FILENAME,
                     session / BOOTSTRAP.CODE_BUNDLE_FILENAME)
        clone = BOOTSTRAP.unpack_code_bundle(run_config, session,
                                             session / BOOTSTRAP.CLONE_DIRNAME)
        return Path(clone), "unpacked from the job's code bundle (only .git/HEAD)"
    local = dict(run_config)
    local["repo"] = {**dict(run_config.get("repo") or {}), "url": str(target)}
    clone = BOOTSTRAP.clone_repo(local, session / BOOTSTRAP.CLONE_DIRNAME)
    return Path(clone), "sparse-cloned at the pin from the target"


def _tail(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text[-OUTPUT_TAIL_CHARS:]


def rehearse(
    *,
    job_dir: Path,
    target: Path,
    run_config: Mapping[str, Any],
    interpreter: Path,
    completeness,
    smoke_kwargs: Mapping[str, Any] | None = None,
    session_limit_seconds: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    keep: Path | None = None,
) -> dict:
    """Run the job's smoke locally and judge its `shard.json`.

    Returns `{status, evidence, fix, details}` with `status` `pass` or
    `fail`. `completeness(stamp, required)` is `shard_io.completeness`,
    handed in so this module and `smoke record` hold one predicate.
    `keep`, when given, is where the scratch directory is left (it must not
    exist yet); otherwise a passing rehearsal's directory is removed and a
    failing one's is kept for reading.
    """
    required = list(((run_config.get("run") or {}).get("smoke") or {})
                    .get("requiredEvidence") or [])
    config = rehearsal_config(run_config, smoke_kwargs=smoke_kwargs,
                              session_limit_seconds=session_limit_seconds)
    if keep is not None:
        keep = Path(keep).resolve()
        if keep.exists():
            raise RehearsalError(f"--keep-rehearsal {keep} already exists")
        keep.mkdir(parents=True)
        scratch = keep
    else:
        scratch = Path(tempfile.mkdtemp(prefix="psmith-preflight-"))
    resolved_target = Path(target).resolve()
    if resolved_target in [scratch.resolve(), *scratch.resolve().parents]:
        raise RehearsalError(f"the scratch directory {scratch} lies inside the target")
    session = scratch / SESSION_DIRNAME
    session.mkdir()
    details: dict[str, Any] = {"scratch": str(scratch), "interpreter": str(interpreter)}

    def finish(status: str, evidence: str, fix: str) -> dict:
        details["kept"] = keep is not None or status != "pass"
        if not details["kept"]:
            shutil.rmtree(scratch, ignore_errors=True)
        elif keep is None:
            evidence = f"{evidence}; the scratch session is kept at {session}"
        return {"status": status, "evidence": evidence, "fix": fix, "details": details}

    try:
        clone, how = materialize(config, Path(job_dir), resolved_target, session)
    except (BOOTSTRAP.BootstrapError, OSError) as exc:
        return finish("fail", f"the job's code could not be materialized as the runner "
                      f"would: {exc}", "regenerate the job (`generate-job --regenerate`) "
                      "and commit what it declares")
    details["code"] = how
    (session / RUN_CONFIG_FILENAME).write_text(json.dumps(config, indent=2, sort_keys=True),
                                               encoding="utf-8")
    driver = scratch / DRIVER_FILENAME
    driver.write_text(DRIVER_SOURCE, encoding="utf-8")
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    env["PYTHONPATH"] = INVOKE.kernel_python_path(clone, None)
    env[INVOKE.CLONE_ROOT_ENV] = str(clone.resolve())
    env[INVOKE.CLONE_COMMIT_ENV] = str(config.get("commit", ""))
    argv = [str(interpreter), str(driver), str(ASSETS / "runner_invoke.py"), str(session),
            str((clone / INVOKE.SRC_DIRNAME).resolve())]
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=session, env=env, capture_output=True,
                                text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        details["seconds"] = round(time.monotonic() - started, 2)
        details["output"] = _tail(exc.stderr) or _tail(exc.stdout)
        return finish("fail", f"the smoke did not finish within its {timeout:g} s local "
                      f"budget under {interpreter}",
                      "declare a cheaper local scale with --local-smoke-kwargs '<json>' "
                      "(the smoke's own kwargs), or raise --local-timeout")
    except OSError as exc:
        details["seconds"] = round(time.monotonic() - started, 2)
        return finish("fail", f"could not start {interpreter}: {exc}",
                      "create the target's .venv with the implementation skill's venv "
                      "stage, or pass --interpreter")
    details["seconds"] = round(time.monotonic() - started, 2)
    details["exitCode"] = result.returncode
    if result.returncode != 0:
        details["output"] = _tail(result.stderr) or _tail(result.stdout)
        last = (details["output"].strip().splitlines() or ["(no output)"])[-1]
        return finish("fail", f"the smoke raised under runner conditions ({how}) in "
                      f"{details['seconds']} s: {last}",
                      "fix the target's smoke so it runs from a clone holding only the "
                      "declared clone paths, then commit and regenerate the job")
    stamp_path = session / SHARD_FILENAME
    if not stamp_path.is_file():
        return finish("fail", f"the smoke ran in {details['seconds']} s but left no "
                      f"{SHARD_FILENAME} in its working directory, so `smoke record` "
                      "would refuse the rehearsal",
                      "have the smoke write shard.json into its working directory: in a "
                      "scaffolded target call `remote_stamp.write_shard(summary)` once its "
                      "work is done (or decorate it with `@remote_stamp.stamped`)")
    try:
        stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return finish("fail", f"{SHARD_FILENAME} is not valid JSON: {exc}",
                      "write shard.json with json.dumps")
    verdict = completeness(stamp, required)
    details["missing"] = list(verdict["missing"])
    if not verdict["complete"]:
        return finish("fail", f"{SHARD_FILENAME} lacks required evidence "
                      f"{', '.join(verdict['missing'])} (requiredEvidence: "
                      f"{', '.join(required)})",
                      "make the stamp carry every requiredEvidence path; in a code-bundle "
                      "job read the commit from FORGE_CLONE_COMMIT when `git rev-parse` fails")
    ran = f"the smoke ran in {details['seconds']} s under {interpreter} ({how})"
    if not required:
        return finish("warn", f"{ran}, but the job names no requiredEvidence, so `smoke "
                      "record` would pass any stamp", "regenerate with "
                      "--smoke-required-evidence evidence.commit --smoke-required-evidence "
                      "environment.device.kind")
    return finish("pass", f"{ran} and its {SHARD_FILENAME} carries {', '.join(required)}", "")
