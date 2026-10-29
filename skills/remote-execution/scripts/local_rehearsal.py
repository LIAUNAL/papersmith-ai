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

The deadline rehearsal (`deadline_rehearse`, session-chains S1) runs the same
way, twice: session 1 under a deadline that has already arrived, which must
stop cleanly and leave `partial.json` and its declared carry paths; session 2
with those paths restored by the runner's own `restore_carry()` from session
1's directory, handed only the remaining units, which must finish them.

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


#: The fix for a `--keep-rehearsal` directory the rehearsal cannot use.
KEEP_FIX = "rerun with --keep-rehearsal <new dir outside the target>"

#: The deadline rehearsal's session 1 gets a session limit whose deadline,
#: by the runner's own formula (`limit - max(10% of limit, 30 min)`), falls
#: this many seconds after the runner starts: already arrived, or about to,
#: by the time the target checks it.
DEADLINE_WINDOW_SECONDS = 1
DEADLINE_DIRNAME = "deadline"
DEADLINE_BLOCKS = ("smoke", "run")
#: The `carry` row session 2 receives, naming session 1's directory.
DEADLINE_CARRY_REF = "deadline-rehearsal-session-1"
DEADLINE_FIX = ("have the target read FORGE_SESSION_DEADLINE (epoch seconds) before each "
                "unit, epoch or trial, checkpoint into its declared carry paths, write "
                "partial.json {\"remaining\": [<unit ids>]} into its working directory "
                "and exit 0")


class RehearsalError(Exception):
    """The rehearsal could not even be set up (no smoke block, no code, no
    usable scratch directory). `fix`, when set, is the exact fix to show."""

    def __init__(self, message: str, *, fix: str | None = None) -> None:
        super().__init__(message)
        self.fix = fix


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
                                 "not to a smoke notebook",
                                 fix="rerun preflight without --local-smoke-kwargs")
        smoke["kwargs"] = dict(smoke_kwargs)
    config["mode"] = "smoke"
    if session_limit_seconds:
        config[INVOKE.SESSION_LIMIT_KEY] = int(session_limit_seconds)
    return config


def _scratch_dir(target: Path, keep: Path | None, prefix: str) -> Path:
    """A new scratch directory outside the target: `keep` when given (it
    must not exist yet), else a fresh temporary one. Refused, before
    anything is written, when it would lie inside the target."""
    resolved_target = Path(target).resolve()
    if keep is not None:
        keep = Path(keep).resolve()
        if resolved_target in [keep, *keep.parents]:
            raise RehearsalError(f"--keep-rehearsal {keep} lies inside the target "
                                 f"{resolved_target}", fix=KEEP_FIX)
        if keep.exists():
            raise RehearsalError(f"--keep-rehearsal {keep} already exists", fix=KEEP_FIX)
        try:
            keep.mkdir(parents=True)
        except OSError as exc:
            raise RehearsalError(f"--keep-rehearsal {keep} could not be created: {exc}",
                                 fix=KEEP_FIX) from exc
        return keep
    scratch = Path(tempfile.mkdtemp(prefix=prefix))
    if resolved_target in [scratch.resolve(), *scratch.resolve().parents]:
        shutil.rmtree(scratch, ignore_errors=True)
        raise RehearsalError(f"the scratch directory {scratch} lies inside the target",
                             fix=KEEP_FIX)
    return scratch


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
    exist yet and must lie outside the target; both are refused before
    anything is written); otherwise the scratch directory is removed, passing
    or failing -- the row's evidence carries what a failure left behind. An
    unexpected error after the scratch exists is a `fail` row, not a
    traceback.
    """
    required = list(((run_config.get("run") or {}).get("smoke") or {})
                    .get("requiredEvidence") or [])
    config = rehearsal_config(run_config, smoke_kwargs=smoke_kwargs,
                              session_limit_seconds=session_limit_seconds)
    resolved_target = Path(target).resolve()
    scratch = _scratch_dir(resolved_target, keep, "psmith-preflight-")
    details: dict[str, Any] = {"scratch": str(scratch), "interpreter": str(interpreter)}

    def finish(status: str, evidence: str, fix: str) -> dict:
        details["kept"] = keep is not None
        if not details["kept"]:
            shutil.rmtree(scratch, ignore_errors=True)
            if status != "pass":
                evidence = (f"{evidence}; rerun with --keep-rehearsal <new dir outside the "
                            "target> to read the scratch session")
        return {"status": status, "evidence": evidence, "fix": fix, "details": details}

    try:
        return _run(scratch=scratch, config=config, required=required, job_dir=Path(job_dir),
                    target=resolved_target, interpreter=interpreter,
                    completeness=completeness, timeout=timeout, details=details,
                    finish=finish)
    except Exception as exc:  # noqa: BLE001 -- a row, never a traceback
        return finish("fail", f"the rehearsal stopped on an unexpected error: "
                      f"{type(exc).__name__}: {exc}",
                      "fix what the error names (the job folder or the target's "
                      "interpreter), then rerun preflight")


def _run_session(session: Path, config: Mapping[str, Any], *, job_dir: Path, target: Path,
                 interpreter: Path, timeout: float, driver: Path) -> dict:
    """One runner session in `session`: the code materialized as the runner
    does it, `config` written beside it, and the runner's own `invoke()`
    started under `interpreter`. Returns `{how, seconds, exitCode, output,
    timedOut}`; a code that cannot be materialized raises."""
    session.mkdir(parents=True)
    clone, how = materialize(config, job_dir, target, session)
    (session / RUN_CONFIG_FILENAME).write_text(json.dumps(config, indent=2, sort_keys=True),
                                               encoding="utf-8")
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    env["PYTHONPATH"] = INVOKE.kernel_python_path(clone, None)
    env[INVOKE.CLONE_ROOT_ENV] = str(clone.resolve())
    env[INVOKE.CLONE_COMMIT_ENV] = str(config.get("commit", ""))
    argv = [str(interpreter), str(driver), str(ASSETS / "runner_invoke.py"), str(session),
            str((clone / INVOKE.SRC_DIRNAME).resolve())]
    started = time.monotonic()
    outcome: dict[str, Any] = {"how": how, "timedOut": False}
    try:
        result = subprocess.run(argv, cwd=session, env=env, capture_output=True,
                                text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        outcome.update(timedOut=True, exitCode=None,
                       output=_tail(exc.stderr) or _tail(exc.stdout))
    else:
        outcome.update(exitCode=result.returncode,
                       output=_tail(result.stderr) or _tail(result.stdout))
    outcome["seconds"] = round(time.monotonic() - started, 2)
    return outcome


def _deadline_config(run_config: Mapping[str, Any], block: str,
                     smoke_kwargs: Mapping[str, Any] | None) -> dict:
    """The worker's run-config for the chosen block, without whatever a
    submission adds (`mode`, `units`, a session limit, carry rows)."""
    if block not in DEADLINE_BLOCKS:
        raise RehearsalError(f"--deadline-block {block!r}: one of "
                             f"{', '.join(DEADLINE_BLOCKS)}")
    if block == "smoke":
        config = rehearsal_config(run_config, smoke_kwargs=smoke_kwargs)
    else:
        config = json.loads(json.dumps(dict(run_config)))
        config.pop("mode", None)
    for key in ("units", INVOKE.SESSION_LIMIT_KEY, INVOKE.CARRY_KEY, "carryProtected"):
        config.pop(key, None)
    return config


def _carried_layouts(session: Path, product: Any, carry_paths: list[str]) -> list[str]:
    """Where, of the two layouts `restore_carry()` reads, the declared carry
    paths sit under `session` (session-relative, in declaration order)."""
    found = []
    prefixes = [Path()]
    if INVOKE._carry_product(product) is not None:
        prefixes.insert(0, Path(INVOKE.CLONE_DIRNAME) / product)
    for raw in carry_paths:
        for prefix in prefixes:
            if (session / prefix / raw).exists():
                found.append((prefix / raw).as_posix())
    return found


def deadline_rehearse(
    *,
    job_dir: Path,
    target: Path,
    run_config: Mapping[str, Any],
    interpreter: Path,
    units: list[str],
    partial_marker,
    block: str = "smoke",
    smoke_kwargs: Mapping[str, Any] | None = None,
    session_limit_seconds: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    keep: Path | None = None,
) -> dict:
    """Two local runner sessions of the job's `block` (session-chains S1).

    Session 1 is handed `units` and a session limit whose deadline arrives
    `DEADLINE_WINDOW_SECONDS` after the runner starts. It must exit 0 within
    `timeout`, leave a `partial.json` (`partial_marker` is
    `shard_io.partial_marker`, the one `remaining` reads) whose ids are a
    subset of `units`, outside every declared carry path, and leave at least
    one declared carry path where `restore_carry()` looks. Session 2 is
    handed only the remaining ids, a `carry` row whose mount is session 1's
    directory, and the service's own limit; it must exit 0 and leave no
    marker. Each session gets `timeout` seconds.

    Returns `{status, evidence, fix, details}`. The scratch directory is
    `keep` when given (it must not exist yet), else removed afterwards.
    """
    units = [str(unit) for unit in units]
    carry_paths = [str(path) for path in run_config.get(INVOKE.CARRY_PATHS_KEY) or []]
    base = _deadline_config(run_config, block, smoke_kwargs)
    scratch = _scratch_dir(Path(target), keep, "psmith-deadline-")
    details: dict[str, Any] = {"scratch": str(scratch), "block": block, "units": units,
                               "interpreter": str(interpreter)}

    def finish(status: str, evidence: str, fix: str) -> dict:
        details["kept"] = keep is not None
        if not details["kept"]:
            shutil.rmtree(scratch, ignore_errors=True)
        return {"status": status, "evidence": evidence, "fix": fix, "details": details}

    driver = scratch / DRIVER_FILENAME
    driver.write_text(DRIVER_SOURCE, encoding="utf-8")
    first = scratch / "session-1"
    try:
        config = {**base, "units": units,
                  INVOKE.SESSION_LIMIT_KEY: INVOKE.SESSION_MARGIN_MIN_SECONDS
                  + DEADLINE_WINDOW_SECONDS}
        outcome = _run_session(first, config, job_dir=Path(job_dir), target=Path(target),
                               interpreter=interpreter, timeout=timeout, driver=driver)
        details["session1"] = outcome
        if outcome["timedOut"]:
            return finish("fail", f"session 1 did not stop within its {timeout:g} s local "
                          "budget under a deadline that had already arrived", DEADLINE_FIX)
        if outcome["exitCode"] != 0:
            return finish("fail", f"session 1 raised under its deadline (exit "
                          f"{outcome['exitCode']}): {outcome['output'].strip()[-300:]}",
                          DEADLINE_FIX)
        stopped, remaining = partial_marker(first)
        if not stopped:
            return finish("fail", f"session 1 ran past a deadline that had already arrived "
                          f"and left no partial.json, so a session cut at its limit would "
                          f"lose its units ({', '.join(units)})", DEADLINE_FIX)
        if remaining is None:
            return finish("fail", "session 1 left a partial.json that is not "
                          '{"remaining": [<unit id strings>]}', DEADLINE_FIX)
        foreign = sorted(remaining - set(units))
        if foreign:
            return finish("fail", f"partial.json lists {', '.join(foreign)}, which are not "
                          f"among the submitted units ({', '.join(units)}); `remaining` "
                          "would drop them", "write the ids from FORGE_RUN_UNITS unchanged: "
                          "partial.json ids must equal the submitted unit strings")
        left = [unit for unit in units if unit in remaining]
        details["remaining"] = left
        for marker in sorted(first.rglob("partial.json")):
            inside = marker.relative_to(first).as_posix()
            for carried in _carried_layouts(first, run_config.get("product"), carry_paths):
                if inside.startswith(carried.rstrip("/") + "/"):
                    return finish("fail", f"partial.json sits at {inside}, inside the declared "
                                  f"carry path {carried}: the next session would restore "
                                  "it and read its own work as unfinished",
                                  "write partial.json into the working directory, outside "
                                  "every carry path")
        carried = _carried_layouts(first, run_config.get("product"), carry_paths)
        details["carried"] = carried
        if carry_paths and not carried:
            return finish("fail", f"session 1 left none of the declared carry paths "
                          f"({', '.join(carry_paths)}) under clone/<product>/ or its working "
                          "directory, so the next session would start fresh",
                          "checkpoint into a declared carry path under FORGE_CLONE_ROOT's "
                          "product folder, or regenerate with the --carry-path it writes")
        if not left:
            return finish("warn", "session 1 finished every unit before its deadline and "
                          "left an empty partial.json; stopping early was not exercised",
                          "rehearse more units (--unit) or a slower --local-smoke-kwargs")
        second = scratch / "session-2"
        config = {**base, "units": left,
                  INVOKE.CARRY_KEY: [{"submissionId": DEADLINE_CARRY_REF,
                                      "ref": DEADLINE_CARRY_REF, "mount": str(first)}]}
        if session_limit_seconds:
            config[INVOKE.SESSION_LIMIT_KEY] = int(session_limit_seconds)
        outcome = _run_session(second, config, job_dir=Path(job_dir), target=Path(target),
                               interpreter=interpreter, timeout=timeout, driver=driver)
        details["session2"] = outcome
        if outcome["timedOut"] or outcome["exitCode"] != 0:
            reason = (f"did not finish within its {timeout:g} s local budget"
                      if outcome["timedOut"] else
                      f"raised (exit {outcome['exitCode']}): "
                      f"{outcome['output'].strip()[-300:]}")
            return finish("fail", f"session 2, handed {', '.join(left)} with session 1's "
                          f"carry paths restored, {reason}", DEADLINE_FIX)
        stopped, still = partial_marker(second)
        if stopped:
            listed = ", ".join(sorted(still)) if still is not None else "an unreadable list"
            return finish("fail", f"session 2, handed {', '.join(left)} with session 1's "
                          f"carry paths restored and no near deadline, still left a "
                          f"partial.json ({listed})", DEADLINE_FIX)
    except (BOOTSTRAP.BootstrapError, OSError) as exc:
        return finish("fail", f"the job's code could not be materialized as the runner "
                      f"would: {exc}", "regenerate the job (`generate-job --regenerate`) "
                      "and commit what it declares")
    except Exception as exc:  # noqa: BLE001 -- a row, never a traceback
        return finish("fail", f"the deadline rehearsal stopped on an unexpected error: "
                      f"{type(exc).__name__}: {exc}", "fix what the error names, then "
                      "rerun preflight")
    where = f" and {', '.join(carried)}" if carried else ""
    return finish("pass", f"session 1 stopped at its deadline leaving partial.json "
                  f"({', '.join(left)}){where}; session 2, handed only those with the carry "
                  "restored, finished them", "")


def _run(*, scratch: Path, config: Mapping[str, Any], required: list, job_dir: Path,
         target: Path, interpreter: Path, completeness, timeout: float,
         details: dict, finish) -> dict:
    """Everything after the scratch directory exists; `rehearse` turns any
    exception it lets through into a `fail` row and removes the scratch."""
    session = scratch / SESSION_DIRNAME
    session.mkdir()
    try:
        clone, how = materialize(config, job_dir, target, session)
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
