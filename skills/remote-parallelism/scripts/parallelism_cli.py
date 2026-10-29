#!/usr/bin/env python3
"""remote-parallelism: is a campaign worth spreading over several remote GPU
accounts, and what keeps the split reproducible.

Stdlib only, no network, no credentials. This CLI decides from MEASURED
numbers -- a pilot's per-unit duration, a rehearsal's setup overhead, the
accounts' own limits -- and writes nothing but an optional assessment or
estimate record. `estimate` turns a timing probe's `Results/timing.json` into a
processing-time range per stage and per host, and never estimates a host it has
no measurement of.

Accounts are counted under the team rule: one account per person per service,
so parallelism counts DISTINCT OWNERS (`--owners`), never accounts. On Colab
only paid compute joins a split (`--tiers`), and services do not mix inside one
campaign unless the shards' environment stamps are declared identical.
It never places a unit on an account (`remote-execution distribute` does),
never generates a job (`generate-job` does) and never launches one (`submit`,
behind the operator's consent, does).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

OBJECTIVE_FLOW = {
    "purpose": (
        "decide from measurements whether a proof of concept or an experiment "
        "campaign is worth spreading over several remote GPU accounts, and keep "
        "the split reproducible when it is"),
    "stages": [
        {"stage": "measured",
         "establishes": "per-unit duration comes from a pilot and setup overhead from a rehearsal, and the accounts' limits and quota are recorded with their date",
         "behindWhen": "an input to assess has no pilot, rehearsal or quota reading behind it"},
        {"stage": "assessed",
         "establishes": "assess turned those measurements into a verdict with its threshold stated, recorded in the tree it concerns",
         "behindWhen": "no .remote-parallelism/assessment-*.json exists in the product or experiments tree"},
        {"stage": "planned",
         "establishes": "every reproducibility checklist item holds for the split the verdict calls for",
         "behindWhen": "a checklist item is unmet: no declared axis, stamp fields missing from identicalAcrossShards, accelerator not pinned, or an account without a passing rehearsal"},
    ],
    "arrival": (
        "a recorded verdict — parallelize over N accounts or stay on one — with "
        "its reproducibility checklist satisfied, before any job is generated"),
    "humanStops": [
        "the launch itself, behind remote-execution's consent and gate",
        "which owners take part: one account per person per service, each owner registered in the team registry and validated",
    ],
}

VERBS = ("assess", "schedule", "estimate", "checklist", "stamp-fields")

ERROR_CODES = (
    "missing-input", "bad-argument", "units-file-missing", "units-file-invalid",
    "duplicate-unit", "units-mismatch", "axis-is-comparison",
    "record-outside-workspace", "record-missing", "timing-missing", "timing-invalid",
    "mixed-devices", "timing-outside-workspace", "accounts-invalid", "accounts-file-missing",
    "plan-missing", "plan-invalid", "no-eligible-account", "unit-over-session-limit",
    "unit-over-session-margin",
)

#: The verdict's thresholds. Stated in every output so the verdict can be read
#: against them rather than trusted.
MIN_SPEEDUP = 1.5
MIN_SAVED_MINUTES = 30

#: The session-fit margin: one unit plus its setup must end inside this share of
#: its account's session limit, so a slow node, a queue or a late checkpoint
#: never meets the service's continuous-run limit. A unit past it is split
#: along the declared axis (by fold, for instance) or declared resumable from a
#: checkpoint and chained over several sessions on the same account.
SESSION_MARGIN_PERCENT = 80


def usable_session(limit: float) -> float:
    """The minutes of one session a plan may fill: SESSION_MARGIN_PERCENT of its limit."""
    return limit * SESSION_MARGIN_PERCENT / 100


def margin_text(limit: float) -> str:
    return f"{SESSION_MARGIN_PERCENT}% of the {num(limit)}-minute session limit ({num(usable_session(limit))} minutes)"

#: Colab compute tiers. Only paid compute may be a worker of a split campaign:
#: the Colab FAQ disallows, on free runtimes without compute units, "running
#: distributed computing workers", and on any tier "using multiple accounts to
#: work around access or resource usage restrictions".
COLAB_SERVICE = "colab"
COLAB_TIERS = ("free", "pro", "payg", "enterprise")
PAID_COLAB_TIERS = ("pro", "payg", "enterprise")
COLAB_FAQ = "https://research.google.com/colaboratory/faq.html"
COLAB_FAQ_REASON = (
    'the Colab FAQ disallows "running distributed computing workers" on free runtimes '
    'without compute units, and "using multiple accounts to work around access or resource '
    f'usage restrictions" ({COLAB_FAQ}, verified 2026-10-25); a free Colab account runs '
    "interactive or proof-of-concept work in one session and is never a worker of a split campaign")

#: Axes a split may never run along: a shard boundary there puts a comparison
#: across a hardware boundary.
COMPARISON_AXES = ("arm", "arms", "comparison", "comparisons")

#: The fields every shard stamps and the distribution declaration names in
#: `identicalAcrossShards`, so a merge over shards that ran on different
#: software, code, data or accelerators is refused rather than averaged.
STAMP_FIELDS = (
    "python", "torch", "cuda", "cudnn", "accelerator", "commit",
    "requirementsDigest", "dataChecksum", "dataPreparationVersion",
)

CHECKLIST = (
    {"id": "axis-not-arm",
     "rule": "Split only along the declared distribution axis (seed, fold, subject block) — never by arm or by comparison.",
     "why": "every comparison subtracts two arms; splitting there puts the subtraction across a hardware boundary"},
    {"id": "seed-from-unit-id",
     "rule": "Derive each unit's seed from the unit id alone: int(sha256(unit_id).hexdigest()[:8], 16) % 2**31 — never from the account, the shard index or the launch order.",
     "why": "a unit then reruns identically wherever and whenever it lands"},
    {"id": "pin-commit",
     "rule": "Every account clones the same published commit.",
     "why": "two commits are two experiments"},
    {"id": "pin-environment",
     "rule": "Every account installs the same pinned requirements file; record its digest as requirementsDigest.",
     "why": "a library update changes numerics silently"},
    {"id": "pin-accelerator",
     "rule": "Request the same accelerator model (machine_shape) for every account and stamp the one that actually arrived.",
     "why": "different GPU models produce different floating-point results, so shards stamped with different accelerators are refused at merge"},
    {"id": "stamp-environment",
     "rule": "Each shard writes python, torch, CUDA, cuDNN, accelerator name, commit, requirements digest, data checksum and preparation version into its shard.json, and the distribution declaration lists them in identicalAcrossShards.",
     "why": "verify --shards then refuses a merge over shards that disagree on any of them"},
    {"id": "deterministic-flags",
     "rule": "Set torch.manual_seed(seed) per unit, torch.use_deterministic_algorithms(True), CUBLAS_WORKSPACE_CONFIG=:4096:8 and torch.backends.cudnn.benchmark=False.",
     "why": "GPU kernels are otherwise free to reorder floating-point sums",
     "cost": "deterministic kernels can run slower and some operations raise instead of running; measure the pilot with the flags on"},
    {"id": "same-dataset-version",
     "rule": "Every notebook mounts the same official dataset version and reads the one official preparation (datasets/<slug>/splits.json).",
     "why": "a shard on another data version answers another question"},
    {"id": "rehearse-each-account",
     "rule": "Rehearse once per account before any campaign: readiness is per worker and never carries over from another account.",
     "why": "a missing secret or quota on one account fails only that account's shards"},
    {"id": "no-pooled-timing",
     "rule": "Never pool wall time or memory across machines; they are perEnvironment measurements.",
     "why": "an average over two machines describes neither"},
    {"id": "one-account-per-person",
     "rule": "One account per person per service: every participating account is owned and operated by a distinct team member registered with `smith team`, and parallelism counts distinct owners, never accounts. On Colab only paid compute (Pro, Pay-As-You-Go compute units, Enterprise) joins a split campaign; where a service's terms are unverified the same one-per-person rule applies.",
     "why": "several accounts held by one person to get around per-user limits are a terms violation, not an optimisation"},
    {"id": "one-service-per-campaign",
     "rule": "Run one campaign on one service; mix services only when the shards' environment stamps (accelerator model, CUDA, torch) are declared identical, and let verify --shards confirm it.",
     "why": "two services rarely hand out the same accelerator and software, and a merge over different stamps is several experiments"},
    {"id": "launch-is-the-operator-s",
     "rule": "The verdict is never launch authorization: placement stays with distribute and the launch with submit behind the operator's consent.",
     "why": "a campaign is hours of somebody's quota"},
)


#: The estimate's one formula, its stages and its stated range.
STAGES = ("poc", "full")
SCALE_KEYS = ("arms", "folds", "seeds", "epochs")
ESTIMATE_RANGE = 0.20
RANGE_NOTE = "±20%, single-probe extrapolation"
UNMEASURED = "unmeasured"
#: Placement rules, read on each estimate's upper bound: a stage over this many
#: seconds locally runs on a cloud host, and a proof of concept is sized to fit
#: this budget on the host it runs on.
LOCAL_LIMIT_SECONDS = 20 * 60
POC_BUDGET_SECONDS = 5 * 60 * 60
PLACEMENT_RULES = {"localLimitSeconds": LOCAL_LIMIT_SECONDS, "pocBudgetSeconds": POC_BUDGET_SECONDS,
                   "bound": "high"}
TIMING_KEYS = {"schema", "measurements", "scales"}
MEASUREMENT_REQUIRED = ("measuredAt", "host", "device", "arm", "unit", "secondsPerUnit", "unitsMeasured")
MEASUREMENT_KEYS = set(MEASUREMENT_REQUIRED) | {"setupSeconds"}
#: Schema 2 adds, per record, what each host is (`hosts`), and per measurement
#: the candidate it ran as, its batch and loader settings, and the split of an
#: epoch into time spent waiting on data and time spent computing. Schema 1
#: records keep loading exactly as before.
TIMING_SCHEMAS = (1, 2)
TIMING_KEYS_V2 = TIMING_KEYS | {"hosts"}
HOST_INFO_KEYS = ("cpuCount", "ramGB", "mps", "cuda")
SETTING_KEYS = ("threads", "batchSize", "numWorkers", "pinMemory", "prefetch", "dtype", "dataSource")
MEASUREMENT_KEYS_V2 = MEASUREMENT_KEYS | {"candidate", "processes", "loadSeconds", "computeSeconds",
                                         *SETTING_KEYS}
#: `local-cpu-<processes>`, `local-mps`, `local-cuda`, or `<host>:<owner>/<machine>`
#: for a remote host, where a machine named `cpu` is a CPU-only session.
CANDIDATE_PATTERN = re.compile(r"^(local-cpu-[1-9][0-9]*|local-mps|local-cuda|"
                               r"[a-z0-9][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)$")
DTYPE_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")
DATA_SOURCES = ("raw", "cached")
#: loadSeconds + computeSeconds may exceed secondsPerUnit by at most this share
#: (clock granularity); past it the split does not describe the epoch it splits.
LOAD_SPLIT_TOLERANCE = 0.05
#: `local`, or `<host slug>:<owner slug>` for a remote host. The slug is never
#: a fixed list: this CLI does not name the services a team rents.
HOST_PATTERN = re.compile(r"^(local|[a-z0-9][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._-]*)$")
DEVICE_PATTERN = re.compile(r"^(cpu|mps|cuda:\S.*)$")


class Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def num(value: float) -> float | int:
    rounded = round(value, 2)
    return int(rounded) if rounded == int(rounded) else rounded


def unit_seed(unit_id: str) -> int:
    return int(hashlib.sha256(unit_id.encode("utf-8")).hexdigest()[:8], 16) % (2 ** 31)


def positive(name: str, raw: str | None, kind=float, allow_zero: bool = False):
    try:
        value = kind(raw)
    except (TypeError, ValueError):
        raise Refusal("bad-argument", f"{name} must be a {'whole ' if kind is int else ''}number, got {raw!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise Refusal("bad-argument", f"{name} must be finite, got {raw!r}")
    if value < 0 or (value == 0 and not allow_zero):
        raise Refusal("bad-argument", f"{name} must be {'non-negative' if allow_zero else 'positive'}, got {raw!r}")
    return value


def load_units(root: Path, name: str, default_minutes: float | None) -> list[dict]:
    path = Path(name)
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise Refusal("units-file-missing", f"{name} does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("units-file-invalid", f"{name} is not JSON: {exc}")
    if not isinstance(data, list) or not data:
        raise Refusal("units-file-invalid", f"{name} must be a non-empty JSON list of unit ids or {{id, minutes}} objects")
    units, seen = [], set()
    for item in data:
        if isinstance(item, str):
            unit_id, minutes = item, None
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            unit_id, minutes = item["id"], item.get("minutes")
        else:
            raise Refusal("units-file-invalid", f"{name}: {item!r} is neither an id nor an {{id, minutes}} object")
        if not unit_id:
            raise Refusal("units-file-invalid", f"{name}: a unit id is empty")
        if unit_id in seen:
            raise Refusal("duplicate-unit", f"{name}: unit {unit_id!r} appears twice")
        seen.add(unit_id)
        if minutes is None:
            if default_minutes is None:
                raise Refusal("missing-input", f"unit {unit_id!r} has no minutes and no --unit-minutes was given")
            minutes = default_minutes
        else:
            minutes = positive(f"minutes of {unit_id!r}", minutes)
        units.append({"id": unit_id, "minutes": float(minutes)})
    return units


def schedule(units: list[dict], slots: int, limit: float, setup: float) -> list[dict]:
    """Greedy longest-first packing onto `slots` concurrent sessions in a row."""
    return pack(units, [limit] * slots, setup)


def pack(units: list[dict], limits: list[float], setup: float) -> list[dict]:
    """Greedy longest-first packing onto one concurrent session per entry of
    `limits`, each with its own wall-time limit.

    Each slot runs sessions back to back; a session pays `setup` once and may
    not run past its slot's limit, and a slot whose usable session (the
    SESSION_MARGIN_PERCENT share of its limit) cannot hold the unit plus the
    setup never takes it. A unit goes to the slot where it finishes
    earliest, ties to the lowest slot, so the output is a pure function of the
    inputs.
    """
    state = [{"finish": 0.0, "used": None, "units": 0, "busy": 0.0, "limit": limit} for limit in limits]
    order = sorted(units, key=lambda unit: (-unit["minutes"], unit["id"]))
    for unit in order:
        best, best_finish, best_new = 0, None, False
        for index, slot in enumerate(state):
            if setup + unit["minutes"] > usable_session(slot["limit"]):
                continue
            if slot["used"] is not None and slot["used"] + unit["minutes"] <= slot["limit"]:
                finish, new = slot["finish"] + unit["minutes"], False
            else:
                finish, new = slot["finish"] + setup + unit["minutes"], True
            if best_finish is None or finish < best_finish:
                best, best_finish, best_new = index, finish, new
        if best_finish is None:
            raise Refusal("unit-over-session-limit", f"unit {unit['id']!r} fits no account's session: "
                                                     "split it along the declared axis")
        slot = state[best]
        cost = unit["minutes"] + (setup if best_new else 0.0)
        slot["used"] = (setup + unit["minutes"]) if best_new else slot["used"] + unit["minutes"]
        slot["finish"] = best_finish
        slot["units"] += 1
        slot["busy"] += cost
    return state


def per_account(state: list[dict], sessions: int, quota_hours: float) -> list[dict]:
    accounts = []
    for start in range(0, len(state), sessions):
        group = state[start:start + sessions]
        hours = sum(slot["busy"] for slot in group) / 60
        accounts.append({"account": start // sessions + 1,
                         "units": sum(slot["units"] for slot in group),
                         "gpuHours": num(hours),
                         "overQuota": hours > quota_hours})
    return accounts


def cmd_assess(args, root: Path, today: str) -> dict:
    if args.account or args.accounts_file is not None:
        return assess_per_account(args, root, today)
    required = {"--unit-minutes": args.unit_minutes, "--owners": args.owners,
                "--sessions-per-account": args.sessions_per_account,
                "--session-limit-hours": args.session_limit_hours,
                "--quota-hours": args.quota_hours, "--setup-minutes": args.setup_minutes}
    if args.units is None and args.units_file is None:
        required = {"--units or --units-file": None, **required}
    if args.units_file is not None:
        required.pop("--unit-minutes")
    missing = [flag for flag, value in required.items() if value is None]
    if missing:
        raise Refusal("missing-input", "measured inputs are required, never guessed; missing: " + ", ".join(missing))

    if args.axis is not None and args.axis.strip().lower() in COMPARISON_AXES:
        raise Refusal("axis-is-comparison", f"--axis {args.axis!r}: a split may run along a seed, fold or subject block, never by arm or comparison")

    unit_minutes = positive("--unit-minutes", args.unit_minutes) if args.unit_minutes is not None else None
    owners = positive("--owners", args.owners, int)
    held = positive("--accounts", args.accounts, int) if args.accounts is not None else owners
    if held < owners:
        raise Refusal("bad-argument", f"--accounts {held} is fewer than --owners {owners}: every owner holds an account")
    services, tiers, excluded = team_policy(args, owners)
    accounts = owners - len(excluded)
    sessions = positive("--sessions-per-account", args.sessions_per_account, int)
    limit_hours = positive("--session-limit-hours", args.session_limit_hours)
    quota_hours = positive("--quota-hours", args.quota_hours)
    setup = positive("--setup-minutes", args.setup_minutes, allow_zero=True)
    count = positive("--units", args.units, int) if args.units is not None else None

    from_file = args.units_file is not None
    if from_file:
        units = load_units(root, args.units_file, unit_minutes)
        if count is not None and count != len(units):
            raise Refusal("units-mismatch", f"--units {count} but {args.units_file} lists {len(units)} units")
    else:
        units = [{"id": f"unit-{index:04d}", "minutes": float(unit_minutes)} for index in range(1, count + 1)]

    limit = limit_hours * 60
    inputs = {"units": len(units), "unitMinutes": num(unit_minutes) if unit_minutes is not None else None,
              "unitsFile": args.units_file, "owners": owners, "accounts": held,
              "service": services, "tiers": tiers, "stampsIdentical": bool(args.stamps_identical),
              "sessionsPerAccount": sessions,
              "sessionLimitHours": num(limit_hours), "quotaHours": num(quota_hours),
              "quotaSource": args.quota_source, "quotaDate": args.quota_date,
              "setupMinutes": num(setup), "axis": args.axis}
    result = {
        "inputs": inputs,
        "thresholds": {"minSpeedup": MIN_SPEEDUP, "minSavedMinutes": MIN_SAVED_MINUTES,
                       "noAccountOverQuota": True},
        "serialMinutes": None, "singleAccountMinutes": None, "parallelMinutes": None,
        "speedup": None, "savedMinutes": None, "accountsUsed": None,
        "recommendedAccounts": None, "perAccount": [], "quotaOk": None,
        "unitsOverSessionLimit": [],
        "eligibleOwners": accounts, "excludedOwners": excluded,
    }
    over = [unit["id"] for unit in units if unit["minutes"] + setup > usable_session(limit)]
    reasons = []
    if held > owners:
        reasons.append(f"{held} accounts are held by {owners} owner(s): accounts beyond one per owner "
                       "never add parallelism, so the plan counts owners")
    if excluded:
        reasons.append(f"{len(excluded)} free-tier Colab owner(s) excluded from the split: {COLAB_FAQ_REASON}")
    mixed = len(services) > 1
    if mixed and args.stamps_identical:
        reasons.append(f"services {', '.join(services)} are mixed under declared identical stamps "
                       "(accelerator model, CUDA, torch): verify --shards must confirm them before any merge")
    if mixed and not args.stamps_identical:
        result["verdict"] = "do-not-mix"
        reasons.append(f"services {', '.join(services)} would be mixed in one campaign: shards on different "
                       "services run on different accelerators and software, so mixing is refused unless "
                       "their environment stamps are declared identical (--stamps-identical); run the "
                       "campaign on one service")
    elif over:
        result["unitsOverSessionLimit"] = over
        result["verdict"] = "split-first"
        reasons.append(f"{len(over)} unit(s) need more than {margin_text(limit)} "
                       f"including the {num(setup)}-minute setup: split them along the declared axis "
                       "(more seeds, folds or subject blocks per unit, never by arm) and assess again, "
                       "or declare the step resumable from a checkpoint in a schedule plan")
    elif accounts == 0:
        result["verdict"] = "single-account"
        result["recommendedAccounts"] = 1
        reasons.append("no owner may be a worker of a split campaign; run on one account, in one session")
    else:
        serial = max(slot["finish"] for slot in schedule(units, 1, limit, setup))
        single_state = schedule(units, sessions, limit, setup)
        single = max(slot["finish"] for slot in single_state)
        state = schedule(units, accounts * sessions, limit, setup)
        parallel = max(slot["finish"] for slot in state)
        spread = per_account(state, sessions, quota_hours)
        single_account = per_account(single_state, sessions, quota_hours)[0]
        quota_ok = not any(account["overQuota"] for account in spread)
        speedup = single / parallel
        saved = single - parallel
        used = sum(1 for account in spread if account["units"])
        result.update({"serialMinutes": num(serial), "singleAccountMinutes": num(single),
                       "parallelMinutes": num(parallel), "speedup": num(speedup),
                       "savedMinutes": num(saved), "accountsUsed": used,
                       "perAccount": spread, "quotaOk": quota_ok})
        if accounts == 1:
            reasons.append("one owner's account is available, so there is nothing to spread over")
        if speedup < MIN_SPEEDUP:
            reasons.append(f"speed-up {num(speedup)} is below the {MIN_SPEEDUP} threshold")
        if saved < MIN_SAVED_MINUTES:
            reasons.append(f"{num(saved)} saved minutes are below the {MIN_SAVED_MINUTES}-minute threshold")
        if not quota_ok:
            reasons.append("an account would exceed its weekly GPU quota of "
                           f"{num(quota_hours)} hours; reduce the units or wait for the quota to reset")
        if single_account["overQuota"]:
            reasons.append(f"one account alone would spend {single_account['gpuHours']} GPU hours, "
                           f"over its {num(quota_hours)}-hour weekly quota")
        go = accounts > 1 and speedup >= MIN_SPEEDUP and saved >= MIN_SAVED_MINUTES and quota_ok
        result["verdict"] = "parallelize" if go else "single-account"
        result["recommendedAccounts"] = used if go else 1
        if go:
            reasons.insert(0, f"speed-up {num(speedup)} >= {MIN_SPEEDUP}, {num(saved)} saved minutes "
                              f">= {MIN_SAVED_MINUTES}, and no account exceeds its quota: "
                              f"parallelize over {used} accounts once the checklist holds")
    result["reasons"] = reasons
    if from_file:
        result["unitSeeds"] = {unit["id"]: unit_seed(unit["id"]) for unit in sorted(units, key=lambda u: u["id"])}
    result["reproducibilityChecklist"] = [dict(item) for item in CHECKLIST]
    result["stampFields"] = list(STAMP_FIELDS)
    result["launchAuthorization"] = False
    if args.record is not None:
        result["recorded"] = record(root, args.record, result, today)
    return result


def record(root: Path, name: str, result: dict, today: str, prefix: str = "assessment") -> str:
    """Write the assessment inside `name`, which must stay inside `root`.

    Real paths are compared, so a symlink anywhere on the way that leads out of
    the workspace is refused, and the record folder itself may not be a link.
    A same-day record never overwrites an earlier one.
    """
    real, inside = resolved(root, name)
    if not inside:
        raise Refusal("record-outside-workspace", f"{name} resolves outside the workspace {root}")
    if not real.is_dir():
        raise Refusal("record-missing", f"{name} is not an existing directory inside the workspace")
    folder = real / ".remote-parallelism"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise Refusal("record-outside-workspace", f"{folder} is a link or not a directory")
    folder.mkdir(exist_ok=True)
    payload = dict(result, recordedOn=today)
    suffix = 1
    while True:
        path = folder / (f"{prefix}-{today}.json" if suffix == 1 else f"{prefix}-{today}-{suffix}.json")
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2) + "\n")
            break
        except FileExistsError:
            suffix += 1
    return path.relative_to(root).as_posix()


def resolved(root: Path, name: str) -> tuple[Path, bool]:
    """`name` as a real path, symlinks resolved, and whether it stays inside `root`."""
    candidate = Path(name)
    candidate = candidate if candidate.is_absolute() else root / candidate
    real = Path(os.path.realpath(candidate))
    return real, real == root or root in real.parents


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_timing(path: Path, name: str) -> dict:
    """The timing record, schema 1 exactly, or a `timing-invalid` refusal."""
    if not path.is_file():
        raise Refusal("timing-missing", f"{name} does not exist; run the timing probe first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("timing-invalid", f"{name} is not JSON: {exc}")

    def bad(message: str):
        raise Refusal("timing-invalid", f"{name}: {message}")

    if not isinstance(data, dict):
        bad("the record must be a JSON object")
    schema = data.get("schema")
    v2 = schema == 2 and not isinstance(schema, bool)
    unknown = sorted(set(data) - (TIMING_KEYS_V2 if v2 else TIMING_KEYS))
    if unknown:
        bad(f"unknown key(s) {', '.join(unknown)}; "
            + ("schema 2 holds schema, hosts, measurements and scales" if v2 else
               "schema 1 holds schema, measurements and scales"))
    if isinstance(schema, bool) or schema not in TIMING_SCHEMAS:
        bad(f"schema must be 1 or 2, got {schema!r}")
    if v2:
        check_hosts(data.get("hosts"), bad)
    measurements = data.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        bad("measurements must be a non-empty list")
    for index, item in enumerate(measurements):
        where = f"measurements[{index}]"
        if not isinstance(item, dict):
            bad(f"{where} must be an object")
        missing = [key for key in MEASUREMENT_REQUIRED if key not in item]
        if missing:
            bad(f"{where} is missing {', '.join(missing)}")
        extra = sorted(set(item) - (MEASUREMENT_KEYS_V2 if v2 else MEASUREMENT_KEYS))
        if extra:
            bad(f"{where} has unknown key(s) {', '.join(extra)}")
        stamp = item["measuredAt"]
        try:
            if not isinstance(stamp, str):
                raise ValueError
            datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            bad(f"{where}.measuredAt must be an ISO-8601 timestamp, got {stamp!r}")
        if not isinstance(item["host"], str) or not HOST_PATTERN.match(item["host"]):
            bad(f"{where}.host must be local or <host>:<owner>, got {item['host']!r}")
        if not isinstance(item["device"], str) or not DEVICE_PATTERN.match(item["device"]):
            bad(f"{where}.device must be cpu, mps or cuda:<gpu name>, got {item['device']!r}")
        if not isinstance(item["arm"], str) or not item["arm"].strip():
            bad(f"{where}.arm must be a non-empty arm id")
        if item["unit"] != "epoch":
            bad(f"{where}.unit must be epoch, got {item['unit']!r}")
        if not is_number(item["secondsPerUnit"]) or item["secondsPerUnit"] <= 0:
            bad(f"{where}.secondsPerUnit must be a positive number, got {item['secondsPerUnit']!r}")
        if not is_count(item["unitsMeasured"]):
            bad(f"{where}.unitsMeasured must be a positive whole number, got {item['unitsMeasured']!r}")
        if "setupSeconds" in item and (not is_number(item["setupSeconds"]) or item["setupSeconds"] < 0):
            bad(f"{where}.setupSeconds must be a non-negative number, got {item['setupSeconds']!r}")
        if v2:
            check_candidate_row(where, item, bad)
    scales = data.get("scales")
    if not isinstance(scales, dict) or sorted(scales) != sorted(STAGES):
        bad("scales must hold exactly poc and full, copied from the approved protocol and the declared pilot")
    for stage in STAGES:
        scale = scales[stage]
        if not isinstance(scale, dict) or sorted(scale) != sorted(SCALE_KEYS):
            bad(f"scales.{stage} must hold exactly {', '.join(SCALE_KEYS)}")
        for key in SCALE_KEYS:
            if not is_count(scale[key]):
                bad(f"scales.{stage}.{key} must be a positive whole number, got {scale[key]!r}")
    return data


def check_hosts(hosts, bad) -> None:
    """Schema 2's `hosts`: what each host is, keyed like a measurement's host."""
    if not isinstance(hosts, dict):
        bad("hosts must map each host (local or <host>:<owner>) to its cpuCount, ramGB, mps and cuda")
    for host, info in hosts.items():
        where = f"hosts[{host!r}]"
        if not HOST_PATTERN.match(host):
            bad(f"{where}: a host is local or <host>:<owner>")
        if not isinstance(info, dict) or sorted(info) != sorted(HOST_INFO_KEYS):
            bad(f"{where} must hold exactly {', '.join(HOST_INFO_KEYS)}")
        if not is_count(info["cpuCount"]):
            bad(f"{where}.cpuCount must be a positive whole number, got {info['cpuCount']!r}")
        if info["ramGB"] is not None and (not is_number(info["ramGB"]) or info["ramGB"] <= 0):
            bad(f"{where}.ramGB must be a positive number or null, got {info['ramGB']!r}")
        for key in ("mps", "cuda"):
            if not isinstance(info[key], bool):
                bad(f"{where}.{key} must be true or false, got {info[key]!r}")


def candidate_of(item: dict) -> str:
    """The candidate a measurement ran as: its own, or its host on schema 1."""
    return item.get("candidate") or item["host"]


def check_candidate_row(where: str, item: dict, bad) -> None:
    """A schema 2 measurement's candidate agrees with its host and device, and
    its settings and load/compute split are well formed."""
    host, device = item["host"], item["device"]
    if "candidate" in item:
        candidate = item["candidate"]
        if not isinstance(candidate, str) or not CANDIDATE_PATTERN.match(candidate):
            bad(f"{where}.candidate must be local-cpu-<processes>, local-mps, local-cuda or "
                f"<host>:<owner>/<machine>, got {candidate!r}")
        if candidate.startswith("local-"):
            if host != "local":
                bad(f"{where}: candidate {candidate} runs on local, not on {host}")
            wanted = {"local-mps": "mps", "local-cuda": "cuda"}.get(candidate, "cpu")
            if device.split(":", 1)[0] != wanted:
                bad(f"{where}: candidate {candidate} computes on {wanted}, but the device recorded is {device}")
            if candidate.startswith("local-cpu-") and "processes" in item \
                    and item["processes"] != int(candidate.rsplit("-", 1)[1]):
                bad(f"{where}: candidate {candidate} runs {candidate.rsplit('-', 1)[1]} process(es), "
                    f"not {item['processes']!r}")
        else:
            owner_host, machine = candidate.split("/", 1)
            if owner_host != host:
                bad(f"{where}: candidate {candidate} runs on {owner_host}, not on {host}; a candidate is "
                    "never measured on another host")
            if (machine.lower() == "cpu") != (device == "cpu"):
                bad(f"{where}: candidate {candidate} was measured on device {device}: a CPU-only machine "
                    "records cpu and an accelerator machine records the accelerator that arrived")
    for key in ("threads", "processes", "batchSize"):
        if key in item and not is_count(item[key]):
            bad(f"{where}.{key} must be a positive whole number, got {item[key]!r}")
    for key in ("numWorkers", "prefetch"):
        value = item.get(key)
        if key in item and value is not None and (not isinstance(value, int) or isinstance(value, bool)
                                                  or value < 0):
            bad(f"{where}.{key} must be a non-negative whole number, got {value!r}")
    if "pinMemory" in item and not isinstance(item["pinMemory"], bool):
        bad(f"{where}.pinMemory must be true or false, got {item['pinMemory']!r}")
    if "dtype" in item and (not isinstance(item["dtype"], str) or not DTYPE_PATTERN.match(item["dtype"])):
        bad(f"{where}.dtype must be a dtype name such as float32, got {item['dtype']!r}")
    if "dataSource" in item and item["dataSource"] not in DATA_SOURCES:
        bad(f"{where}.dataSource must be one of {', '.join(DATA_SOURCES)}, got {item['dataSource']!r}")
    for key in ("loadSeconds", "computeSeconds"):
        if key in item and (not is_number(item[key]) or item[key] < 0):
            bad(f"{where}.{key} must be a non-negative number, got {item[key]!r}")
    split = item.get("loadSeconds", 0) + item.get("computeSeconds", 0)
    if split > item["secondsPerUnit"] * (1 + LOAD_SPLIT_TOLERANCE):
        bad(f"{where}: loadSeconds + computeSeconds ({num(split)} s) exceed the epoch's secondsPerUnit "
            f"({num(item['secondsPerUnit'])} s)")


def settings_of(item: dict) -> tuple:
    return tuple(item.get(key) for key in SETTING_KEYS)


def per_unit_of(items: list[dict]) -> float:
    by_arm: dict[str, list[float]] = {}
    for item in items:
        by_arm.setdefault(item["arm"], []).append(float(item["secondsPerUnit"]))
    return sum(sum(values) / len(values) for values in by_arm.values()) / len(by_arm)


def best_setting(items: list[dict]) -> tuple[list[dict], int]:
    """The rows of a candidate's fastest measured setting, and how many settings
    it was measured under. Settings are never pooled: a sweep row is one try."""
    groups: dict[tuple, list[dict]] = {}
    for item in items:
        groups.setdefault(settings_of(item), []).append(item)
    best = min(groups.values(), key=per_unit_of)
    return best, len(groups)


def load_share(items: list[dict]) -> float | None:
    """The share of an epoch spent waiting on data, over the rows that split it."""
    split = [item for item in items if "loadSeconds" in item and "computeSeconds" in item]
    total = sum(item["loadSeconds"] + item["computeSeconds"] for item in split)
    return sum(item["loadSeconds"] for item in split) / total if split and total > 0 else None


def candidate_estimate(items: list[dict], scale: dict) -> dict:
    """A schema 2 candidate's estimate: the one formula over its fastest setting."""
    rows, tried = best_setting(items)
    estimate = host_estimate(rows, scale)
    candidate = candidate_of(rows[0])
    processes = (int(candidate.rsplit("-", 1)[1]) if candidate.startswith("local-cpu-")
                 else rows[0].get("processes", 1))
    share = load_share(rows)
    estimate.update({"candidate": candidate, "processes": processes,
                     "settings": {key: rows[0][key] for key in SETTING_KEYS if key in rows[0]},
                     "settingsMeasured": tried, "loadShare": None if share is None else num(share)})
    return estimate


def item_host(estimate: dict) -> str:
    candidate = estimate["candidate"]
    return "local" if candidate.startswith("local-") else candidate.split("/", 1)[0]


def measured_candidates(data: dict) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """The record's rows per host and per candidate, or a `mixed-devices`
    refusal when one candidate was timed on two devices. On schema 1 the
    candidate is the host, so the refusal reads as it always has."""
    by_host: dict[str, list[dict]] = {}
    by_candidate: dict[str, list[dict]] = {}
    for item in data["measurements"]:
        by_host.setdefault(item["host"], []).append(item)
        by_candidate.setdefault(candidate_of(item), []).append(item)
    for candidate, items in by_candidate.items():
        devices = sorted({item["device"] for item in items})
        if len(devices) > 1:
            if data["schema"] == 1:
                raise Refusal("mixed-devices", f"host {candidate} was timed on {', '.join(devices)}: timing is "
                                               "never pooled across machines; keep one device per host in the record")
            raise Refusal("mixed-devices", f"candidate {candidate} was timed on {', '.join(devices)}: timing is "
                                           "never pooled across machines; keep one device per candidate")
    return by_host, by_candidate


def host_estimate(measurements: list[dict], scale: dict) -> dict:
    """The one formula: mean(secondsPerUnit, per arm) x epochs x folds x seeds x
    arms + setupSeconds x folds x seeds, reported as a +/-20% range."""
    by_arm: dict[str, list[float]] = {}
    for item in measurements:
        by_arm.setdefault(item["arm"], []).append(float(item["secondsPerUnit"]))
    per_arm = {arm: sum(values) / len(values) for arm, values in sorted(by_arm.items())}
    per_unit = sum(per_arm.values()) / len(per_arm)
    setups = [float(item["setupSeconds"]) for item in measurements if "setupSeconds" in item]
    setup = sum(setups) / len(setups) if setups else 0.0
    arms, folds, seeds, epochs = (scale[key] for key in SCALE_KEYS)
    seconds = per_unit * epochs * folds * seeds * arms + setup * folds * seeds
    formula = (f"mean secondsPerUnit per arm {num(per_unit)} s x {epochs} epochs x {folds} folds x "
               f"{seeds} seeds x {arms} arms + setupSeconds {num(setup)} s x {folds} folds x "
               f"{seeds} seeds = {num(seconds)} s; {RANGE_NOTE}")
    return {"seconds": num(seconds), "low": num(seconds * (1 - ESTIMATE_RANGE)),
            "high": num(seconds * (1 + ESTIMATE_RANGE)), "formula": formula,
            "measurements": len(measurements), "device": measurements[0]["device"],
            "secondsPerUnit": num(per_unit), "perArm": {arm: num(value) for arm, value in per_arm.items()},
            "setupSeconds": num(setup)}


def placement(stage: str, estimates: dict) -> dict:
    """Where a stage runs under the placement rules, never whether it launches."""
    local = estimates.get("local")
    if not isinstance(local, dict):
        return {"where": None, "host": None,
                "reason": "local unmeasured: run the local timing probe before placing this stage"}
    if local["high"] <= LOCAL_LIMIT_SECONDS:
        result = {"where": "local", "host": "local",
                  "reason": f"local upper bound {num(local['high'])} s is within 20 minutes"}
        best = local
    else:
        remote = sorted((item["high"], host) for host, item in estimates.items()
                        if host != "local" and isinstance(item, dict))
        best = estimates[remote[0][1]] if remote else None
        over = f"local upper bound {num(local['high'])} s exceeds 20 minutes, so it runs on a cloud host"
        result = ({"where": "cloud", "host": remote[0][1], "reason": f"{over}; {remote[0][1]} is the fastest measured"}
                  if remote else
                  {"where": "cloud", "host": None, "reason": f"{over}; run a timing probe on a cloud host first"})
    if stage == "poc":
        if best is None:
            result["pocBudget"] = UNMEASURED
        elif best["high"] <= POC_BUDGET_SECONDS:
            result["pocBudget"] = "within"
        else:
            result["pocBudget"] = "exceeds"
            result["reason"] += (f"; its upper bound {num(best['high'])} s exceeds the 5-hour proof-of-concept "
                                 "budget: reduce the design (subjects, epochs, folds, seeds, arms) before it runs")
    return result


def cmd_estimate(args, root: Path, today: str) -> dict:
    if args.timing is None:
        raise Refusal("missing-input", "--timing is required: the timing probe's Results/timing.json")
    stage = (args.stage or "both").strip().lower()
    if stage not in (*STAGES, "both"):
        raise Refusal("bad-argument", f"--stage {args.stage!r}: one of poc, full or both")
    stages = STAGES if stage == "both" else (stage,)
    asked = []
    for raw in args.host or []:
        for host in (part.strip() for part in raw.split(",")):
            if not HOST_PATTERN.match(host):
                raise Refusal("bad-argument", f"--host {host!r}: local or <host>:<owner>")
            asked.append(host)
    if args.record is not None:
        path, inside = resolved(root, args.timing)
        if not inside:
            raise Refusal("timing-outside-workspace", f"--timing {args.timing} resolves outside the "
                                                      f"workspace {root}; --record reads only a timing "
                                                      "record inside it")
    else:
        path = Path(args.timing)
        path = path if path.is_absolute() else root / path
    data = load_timing(path, args.timing)

    by_host, by_candidate = measured_candidates(data)
    hosts = ["local", *sorted(host for host in by_host if host != "local")]
    hosts += [host for host in asked if host not in hosts]
    if data["schema"] == 1:
        estimates = {
            name: {host: host_estimate(by_host[host], data["scales"][name]) if host in by_host else UNMEASURED
                   for host in hosts}
            for name in stages}
    else:
        per_candidate = {name: {candidate: candidate_estimate(items, data["scales"][name])
                                for candidate, items in sorted(by_candidate.items())} for name in stages}
        estimates = {name: {host: min((item for item in per_candidate[name].values()
                                       if item_host(item) == host),
                                      key=lambda item: (item["high"], item["candidate"]), default=UNMEASURED)
                            for host in hosts}
                     for name in stages}
    result = {"estimates": estimates, "placement": {name: placement(name, estimates[name]) for name in stages},
              "placementRules": PLACEMENT_RULES, "timing": args.timing, "range": RANGE_NOTE,
              "unmeasuredMeans": "no measurement on that host; a remote host is never estimated from local timings",
              "launchAuthorization": False}
    if data["schema"] == 2:
        result["candidateEstimates"] = per_candidate
        result["hostInfo"] = data["hosts"]
        result["candidateNote"] = ("each candidate is estimated from its own rows at its fastest measured "
                                   "setting; the estimate is serial work (processes and accounts are "
                                   "counted by plan)")
    if args.record is not None:
        result["recorded"] = record(root, args.record, result, today, prefix="estimate")
    return result


def team_policy(args, owners: int) -> tuple[list[str], list[str] | None, list[dict]]:
    """The campaign's services, its Colab tiers and the owners excluded by tier."""
    services: list[str] = []
    if args.service is not None:
        for name in (part.strip().lower() for part in args.service.split(",")):
            if not name or not all(ch.isalnum() or ch == "-" for ch in name):
                raise Refusal("bad-argument", f"--service {args.service!r}: a comma list of service names")
            if name not in services:
                services.append(name)
    has_colab = COLAB_SERVICE in services
    if args.tiers is None:
        if has_colab:
            raise Refusal("missing-input", "--tiers is required on colab: one compute tier per Colab owner "
                                           f"({', '.join(COLAB_TIERS)}), never guessed")
        return services, None, []
    if not has_colab:
        raise Refusal("bad-argument", "--tiers describes Colab owners; pass --service colab")
    tiers = [part.strip().lower() for part in args.tiers.split(",")]
    unknown = [tier for tier in tiers if tier not in COLAB_TIERS]
    if unknown:
        raise Refusal("bad-argument", f"--tiers {args.tiers!r}: each tier is one of {', '.join(COLAB_TIERS)}")
    expected_all = len(services) == 1
    if (expected_all and len(tiers) != owners) or (not expected_all and len(tiers) > owners):
        raise Refusal("bad-argument", f"--tiers lists {len(tiers)} tier(s) for {owners} owner(s): one per "
                                      "Colab owner" + ("" if expected_all else ", at most one per owner"))
    excluded = [{"owner": index, "tier": tier} for index, tier in enumerate(tiers, start=1)
                if tier not in PAID_COLAB_TIERS]
    return services, tiers, excluded


# ------------------------------------------------------------- per-service accounts
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SERVICE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
UNKNOWN_QUOTA = ("unknown", "?")
ACCOUNT_KEYS = {"owner", "service", "sessions", "sessionHours", "quotaHours", "tier", "quotaSource", "quotaDate"}
#: The uniform limit flags `--account` / `--accounts-file` replace.
UNIFORM_LIMIT_FLAGS = (("--owners", "owners"), ("--accounts", "accounts"),
                       ("--sessions-per-account", "sessions_per_account"),
                       ("--session-limit-hours", "session_limit_hours"),
                       ("--quota-hours", "quota_hours"), ("--tiers", "tiers"))
#: One quota week, in minutes: a plan longer than this spans more than one.
QUOTA_WEEK_MINUTES = 7 * 24 * 60
#: Above this many service assignments the search goes step by step.
EXHAUSTIVE_LIMIT = 4096


def account_entry(where: str, owner, service, sessions, hours, quota, tier, extra: dict | None = None) -> dict:
    """One account with its own limits, or an `accounts-invalid` refusal."""
    def bad(message: str):
        raise Refusal("accounts-invalid", f"{where}: {message}")

    if not isinstance(owner, str) or not OWNER_PATTERN.match(owner):
        bad(f"owner must be a team slug, got {owner!r}")
    if not isinstance(service, str) or not SERVICE_PATTERN.match(service):
        bad(f"service must be a lower-case service name, got {service!r}")
    if not is_count(sessions):
        bad(f"sessions must be a positive whole number, got {sessions!r}")
    if not is_number(hours) or hours <= 0:
        bad(f"session hours must be a positive number, got {hours!r}")
    if quota is None or (isinstance(quota, str) and quota.strip().lower() in UNKNOWN_QUOTA):
        quota = None
    elif not is_number(quota) or quota <= 0:
        bad(f"quota hours must be a positive number or unknown, got {quota!r}")
    if service == COLAB_SERVICE:
        if tier not in COLAB_TIERS:
            bad(f"a {COLAB_SERVICE} account needs its compute tier ({', '.join(COLAB_TIERS)}), never guessed; "
                f"got {tier!r}")
    elif tier is not None:
        bad(f"a tier describes a {COLAB_SERVICE} account, not {service}")
    entry = {"owner": owner, "service": service, "sessions": sessions, "sessionHours": float(hours),
             "quotaHours": None if quota is None else float(quota), "tier": tier}
    for key in ("quotaSource", "quotaDate"):
        if extra and extra.get(key) is not None:
            entry[key] = extra[key]
    return entry


def parse_account_flag(raw: str) -> dict:
    """`<owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>]`."""
    parts = raw.split(":")
    if len(parts) not in (5, 6):
        raise Refusal("accounts-invalid", f"--account {raw!r}: <owner>:<service>:<sessions>:"
                                          "<session_hours>:<quota_hours>[:<tier>]")

    def number(text: str, kind):
        try:
            value = kind(text)
        except ValueError:
            return text
        return value if math.isfinite(value) else text

    owner, service, sessions, hours, quota = parts[:5]
    tier = parts[5].strip().lower() if len(parts) == 6 else None
    quota_value = quota if quota.strip().lower() in UNKNOWN_QUOTA else number(quota, float)
    return account_entry(f"--account {raw!r}", owner, service.strip().lower(), number(sessions, int),
                         number(hours, float), quota_value, tier)


def load_accounts(root: Path, flags: list[str] | None, name: str | None,
                  fallback: list | None = None) -> list[dict]:
    """The accounts from repeated `--account`, an accounts file, or a plan."""
    if flags and name:
        raise Refusal("bad-argument", "give --account or --accounts-file, not both")
    if flags:
        return [parse_account_flag(raw) for raw in flags]
    if name:
        path = Path(name)
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            raise Refusal("accounts-file-missing", f"{name} does not exist")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Refusal("accounts-invalid", f"{name} is not JSON: {exc}")
        if isinstance(data, dict) and set(data) == {"accounts"}:
            data = data["accounts"]
        source = name
    else:
        data, source = fallback, "the plan's accounts"
    if data is None:
        raise Refusal("missing-input", "accounts are required, never guessed: --account, --accounts-file "
                                       "or the plan's accounts")
    if not isinstance(data, list) or not data:
        raise Refusal("accounts-invalid", f"{source} must be a non-empty list of accounts")
    entries = []
    for index, item in enumerate(data):
        where = f"{source}[{index}]"
        if not isinstance(item, dict):
            raise Refusal("accounts-invalid", f"{where} must be an object")
        unknown = sorted(set(item) - ACCOUNT_KEYS)
        if unknown:
            raise Refusal("accounts-invalid", f"{where} has unknown key(s) {', '.join(unknown)}")
        tier = item.get("tier")
        entries.append(account_entry(where, item.get("owner"), item.get("service"), item.get("sessions"),
                                     item.get("sessionHours"), item.get("quotaHours"),
                                     tier.strip().lower() if isinstance(tier, str) else tier, item))
    return entries


def account_pool(entries: list[dict], services: list[str] | None = None) -> dict:
    """The eligible accounts under the team rule: one per owner per service, and
    only paid compute on Colab. `services` filters the entries when given."""
    eligible, excluded, ignored, seen = [], [], [], set()
    for entry in entries:
        if services is not None and entry["service"] not in services:
            continue
        label = f"{entry['service']}:{entry['owner']}"
        if (entry["owner"], entry["service"]) in seen:
            ignored.append(label)
            continue
        seen.add((entry["owner"], entry["service"]))
        if entry["service"] == COLAB_SERVICE and entry["tier"] not in PAID_COLAB_TIERS:
            excluded.append({"account": label, "owner": entry["owner"], "tier": entry["tier"]})
            continue
        eligible.append(dict(entry, label=label))
    in_use = services if services is not None else list(dict.fromkeys(e["service"] for e in entries))
    return {"eligible": eligible, "excluded": excluded, "ignored": ignored, "services": in_use}


def pool_reasons(pool: dict) -> list[str]:
    reasons = []
    if pool["ignored"]:
        reasons.append(f"{', '.join(pool['ignored'])}: a second account of one owner on one service never "
                       "adds parallelism (one account per person per service), so it is left out")
    if pool["excluded"]:
        reasons.append(f"{len(pool['excluded'])} free-tier Colab owner(s) excluded from the split: {COLAB_FAQ_REASON}")
    return reasons


def parse_services(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    services = []
    for name in (part.strip().lower() for part in raw.split(",")):
        if not name or not SERVICE_PATTERN.match(name):
            raise Refusal("bad-argument", f"--service {raw!r}: a comma list of service names")
        if name not in services:
            services.append(name)
    return services


def assess_per_account(args, root: Path, today: str) -> dict:
    """`assess` with each account's own sessions, session wall time and quota."""
    given = [flag for flag, attr in UNIFORM_LIMIT_FLAGS if getattr(args, attr) is not None]
    if given:
        raise Refusal("bad-argument", "--account and --accounts-file carry each account's own limits; drop "
                                      + ", ".join(given))
    required = {"--setup-minutes": args.setup_minutes}
    if args.units is None and args.units_file is None:
        required = {"--units or --units-file": None, **required}
    if args.units_file is None:
        required["--unit-minutes"] = args.unit_minutes
    missing = [flag for flag, value in required.items() if value is None]
    if missing:
        raise Refusal("missing-input", "measured inputs are required, never guessed; missing: " + ", ".join(missing))
    if args.axis is not None and args.axis.strip().lower() in COMPARISON_AXES:
        raise Refusal("axis-is-comparison", f"--axis {args.axis!r}: a split may run along a seed, fold or subject block, never by arm or comparison")
    unit_minutes = positive("--unit-minutes", args.unit_minutes) if args.unit_minutes is not None else None
    setup = positive("--setup-minutes", args.setup_minutes, allow_zero=True)
    count = positive("--units", args.units, int) if args.units is not None else None
    entries = load_accounts(root, args.account, args.accounts_file)
    pool = account_pool(entries, parse_services(args.service))
    services, eligible = pool["services"], pool["eligible"]

    from_file = args.units_file is not None
    if from_file:
        units = load_units(root, args.units_file, unit_minutes)
        if count is not None and count != len(units):
            raise Refusal("units-mismatch", f"--units {count} but {args.units_file} lists {len(units)} units")
    else:
        units = [{"id": f"unit-{index:04d}", "minutes": float(unit_minutes)} for index in range(1, count + 1)]

    inputs = {"units": len(units), "unitMinutes": num(unit_minutes) if unit_minutes is not None else None,
              "unitsFile": args.units_file, "perServiceLimits": True,
              "accountLimits": [{key: value for key, value in entry.items() if key != "label"} for entry in entries],
              "owners": len({entry["owner"] for entry in eligible}), "accounts": len(entries),
              "service": services, "stampsIdentical": bool(args.stamps_identical),
              "quotaSource": args.quota_source, "quotaDate": args.quota_date,
              "setupMinutes": num(setup), "axis": args.axis}
    result = {
        "inputs": inputs,
        "thresholds": {"minSpeedup": MIN_SPEEDUP, "minSavedMinutes": MIN_SAVED_MINUTES,
                       "noAccountOverQuota": True},
        "serialMinutes": None, "singleAccountMinutes": None, "parallelMinutes": None,
        "speedup": None, "savedMinutes": None, "accountsUsed": None,
        "recommendedAccounts": None, "perAccount": [], "quotaOk": None,
        "unitsOverSessionLimit": [],
        "eligibleOwners": len(eligible),
        "excludedOwners": [{"owner": item["owner"], "tier": item["tier"]} for item in pool["excluded"]],
    }
    longest = max((entry["sessionHours"] * 60 for entry in eligible), default=None)
    over = [unit["id"] for unit in units
            if longest is not None and unit["minutes"] + setup > usable_session(longest)]
    reasons = pool_reasons(pool)
    mixed = len(services) > 1
    if mixed and args.stamps_identical:
        reasons.append(f"services {', '.join(services)} are mixed under declared identical stamps "
                       "(accelerator model, CUDA, torch): verify --shards must confirm them before any merge")
    if mixed and not args.stamps_identical:
        result["verdict"] = "do-not-mix"
        reasons.append(f"services {', '.join(services)} would be mixed in one campaign: shards on different "
                       "services run on different accelerators and software, so mixing is refused unless "
                       "their environment stamps are declared identical (--stamps-identical); run the "
                       "campaign on one service (--service filters the accounts)")
    elif over:
        result["unitsOverSessionLimit"] = over
        result["verdict"] = "split-first"
        reasons.append(f"{len(over)} unit(s) need more than {margin_text(longest)} of the longest "
                       f"session, including the {num(setup)}-minute setup: split them along the declared axis "
                       "(more seeds, folds or subject blocks per unit, never by arm) and assess again, "
                       "or declare the step resumable from a checkpoint in a schedule plan")
    elif not eligible:
        result["verdict"] = "single-account"
        result["recommendedAccounts"] = 1
        reasons.append("no owner may be a worker of a split campaign; run on one account, in one session")
    else:
        biggest = max(unit["minutes"] for unit in units)
        baseline, single_state = None, None
        for entry in eligible:
            limit = entry["sessionHours"] * 60
            if biggest + setup > usable_session(limit):
                continue
            state = pack(units, [limit] * entry["sessions"], setup)
            if single_state is None or max(s["finish"] for s in state) < max(s["finish"] for s in single_state):
                baseline, single_state = entry, state
        serial = max(slot["finish"] for slot in pack(units, [baseline["sessionHours"] * 60], setup))
        single = max(slot["finish"] for slot in single_state)
        limits = [entry["sessionHours"] * 60 for entry in eligible for _ in range(entry["sessions"])]
        state = pack(units, limits, setup)
        parallel = max(slot["finish"] for slot in state)
        spread, cursor = [], 0
        for index, entry in enumerate(eligible, start=1):
            group = state[cursor:cursor + entry["sessions"]]
            cursor += entry["sessions"]
            hours = sum(slot["busy"] for slot in group) / 60
            quota = entry["quotaHours"]
            spread.append({"account": index, "owner": entry["owner"], "service": entry["service"],
                           "sessions": entry["sessions"], "sessionLimitHours": num(entry["sessionHours"]),
                           "quotaHours": None if quota is None else num(quota),
                           "units": sum(slot["units"] for slot in group), "gpuHours": num(hours),
                           "overQuota": None if quota is None else hours > quota})
        quota_ok = not any(account["overQuota"] for account in spread)
        speedup = single / parallel
        saved = single - parallel
        used = sum(1 for account in spread if account["units"])
        result.update({"serialMinutes": num(serial), "singleAccountMinutes": num(single),
                       "parallelMinutes": num(parallel), "speedup": num(speedup),
                       "savedMinutes": num(saved), "accountsUsed": used,
                       "baselineAccount": baseline["label"], "perAccount": spread, "quotaOk": quota_ok})
        if len(eligible) == 1:
            reasons.append("one owner's account is available, so there is nothing to spread over")
        if speedup < MIN_SPEEDUP:
            reasons.append(f"speed-up {num(speedup)} is below the {MIN_SPEEDUP} threshold")
        if saved < MIN_SAVED_MINUTES:
            reasons.append(f"{num(saved)} saved minutes are below the {MIN_SAVED_MINUTES}-minute threshold")
        for account in spread:
            if account["overQuota"]:
                reasons.append(f"{account['service']}:{account['owner']} would spend {account['gpuHours']} GPU "
                               f"hours, over its {account['quotaHours']}-hour weekly quota; reduce the units "
                               "or wait for the quota to reset")
            elif account["overQuota"] is None and account["units"]:
                reasons.append(f"{account['service']}:{account['owner']} has an unknown weekly quota: not "
                               "checked; record it (--quota-source, --quota-date) before the launch")
        baseline_hours = sum(slot["busy"] for slot in single_state) / 60
        if baseline["quotaHours"] is not None and baseline_hours > baseline["quotaHours"]:
            reasons.append(f"one account alone ({baseline['label']}) would spend {num(baseline_hours)} GPU hours, "
                           f"over its {num(baseline['quotaHours'])}-hour weekly quota")
        go = len(eligible) > 1 and speedup >= MIN_SPEEDUP and saved >= MIN_SAVED_MINUTES and quota_ok
        result["verdict"] = "parallelize" if go else "single-account"
        result["recommendedAccounts"] = used if go else 1
        if go:
            reasons.insert(0, f"speed-up {num(speedup)} >= {MIN_SPEEDUP}, {num(saved)} saved minutes "
                              f">= {MIN_SAVED_MINUTES}, and no account exceeds its quota: "
                              f"parallelize over {used} accounts once the checklist holds")
    result["reasons"] = reasons
    if from_file:
        result["unitSeeds"] = {unit["id"]: unit_seed(unit["id"]) for unit in sorted(units, key=lambda u: u["id"])}
    result["reproducibilityChecklist"] = [dict(item) for item in CHECKLIST]
    result["stampFields"] = list(STAMP_FIELDS)
    result["launchAuthorization"] = False
    if args.record is not None:
        result["recorded"] = record(root, args.record, result, today)
    return result


# ------------------------------------------------------------- schedule
PLAN_KEYS = {"schema", "steps", "accounts", "setupMinutes"}
STEP_KEYS = {"id", "units", "unitMinutes", "timing", "services", "requires", "setupMinutes",
             "stampsIdentical", "axis", "resumable", "checkpointMinutes"}


def per_service(where: str, value, services: list[str], allow_zero: bool) -> dict:
    """A number for every service, or a {service: number} map."""
    def check(name: str, item):
        if not is_number(item) or item < 0 or (item == 0 and not allow_zero):
            raise Refusal("plan-invalid", f"{where}{name} must be a {'non-negative' if allow_zero else 'positive'} "
                                          f"number, got {item!r}")
        return float(item)

    if isinstance(value, dict):
        return {svc: check(f".{svc}", item) for svc, item in value.items()}
    return {svc: check("", value) for svc in services}


def timing_unit_minutes(root: Path, where: str, service: str, spec, units: int) -> tuple[float, str]:
    """A step's per-unit minutes on one service from that service's own timing
    record: the stage's work at the estimate's upper bound, over the step's units."""
    if not isinstance(spec, dict) or not {"path", "host", "stage"} <= set(spec) <= {"path", "host", "stage",
                                                                                      "candidate"}:
        raise Refusal("plan-invalid", f"{where}: timing.{service} holds path, host and stage, and a "
                                      "candidate when its host holds several")
    host, stage = spec["host"], spec["stage"]
    if not isinstance(host, str) or not HOST_PATTERN.match(host) or host.split(":")[0] != service:
        raise Refusal("plan-invalid", f"{where}: timing.{service}.host must be {service}:<owner>, the service's "
                                      f"own host; got {host!r} (timing is never pooled across machines)")
    if stage not in STAGES:
        raise Refusal("plan-invalid", f"{where}: timing.{service}.stage must be one of {', '.join(STAGES)}")
    if not isinstance(spec["path"], str):
        raise Refusal("plan-invalid", f"{where}: timing.{service}.path must be a path")
    path = Path(spec["path"])
    data = load_timing(path if path.is_absolute() else root / path, spec["path"])
    items = [item for item in data["measurements"] if item["host"] == host]
    if "candidate" in spec:
        items = [item for item in items if candidate_of(item) == spec["candidate"]]
    if not items:
        raise Refusal("plan-invalid", f"{where}: {spec['path']} has no measurement on "
                                      f"{spec.get('candidate', host)} ({UNMEASURED}); "
                                      "a remote host is never estimated from another host's timings")
    candidates = sorted({candidate_of(item) for item in items})
    if len(candidates) > 1:
        raise Refusal("plan-invalid", f"{where}: {host} holds candidates {', '.join(candidates)}: name one as "
                                      f"timing.{service}.candidate (timing is never pooled across machines)")
    devices = sorted({item["device"] for item in items})
    if len(devices) > 1:
        raise Refusal("mixed-devices", f"host {host} was timed on {', '.join(devices)}: timing is never "
                                       "pooled across machines; keep one device per host in the record")
    items = best_setting(items)[0]
    estimate = host_estimate(items, data["scales"][stage])
    scale = data["scales"][stage]
    work = estimate["secondsPerUnit"] * scale["epochs"] * scale["folds"] * scale["seeds"] * scale["arms"]
    minutes = work * (1 + ESTIMATE_RANGE) / units / 60
    return minutes, (f"{spec['path']} {host} {stage}: upper bound of {num(work)} s of work "
                     f"(+{int(ESTIMATE_RANGE * 100)}%) over {units} units")


def load_plan(root: Path, name: str) -> dict:
    path = Path(name)
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise Refusal("plan-missing", f"{name} does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("plan-invalid", f"{name} is not JSON: {exc}")
    if not isinstance(data, dict):
        raise Refusal("plan-invalid", f"{name} must be a JSON object")
    unknown = sorted(set(data) - PLAN_KEYS)
    if unknown:
        raise Refusal("plan-invalid", f"{name}: unknown key(s) {', '.join(unknown)}")
    if data.get("schema") != 1 or isinstance(data.get("schema"), bool):
        raise Refusal("plan-invalid", f"{name}: schema must be 1, got {data.get('schema')!r}")
    if not isinstance(data.get("steps"), list) or not data["steps"]:
        raise Refusal("plan-invalid", f"{name}: steps must be a non-empty list")
    default_setup = data.get("setupMinutes")
    steps, ids = [], set()
    for index, item in enumerate(data["steps"]):
        where = f"{name}: steps[{index}]"
        if not isinstance(item, dict):
            raise Refusal("plan-invalid", f"{where} must be an object")
        extra = sorted(set(item) - STEP_KEYS)
        if extra:
            raise Refusal("plan-invalid", f"{where} has unknown key(s) {', '.join(extra)}")
        sid = item.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise Refusal("plan-invalid", f"{where}.id must be a non-empty step id")
        if sid in ids:
            raise Refusal("plan-invalid", f"{where}: step {sid!r} appears twice")
        ids.add(sid)
        where = f"{name}: step {sid!r}"
        axis = item.get("axis")
        if axis is not None and (not isinstance(axis, str) or axis.strip().lower() in COMPARISON_AXES):
            raise Refusal("axis-is-comparison", f"{where}: axis {axis!r}: a campaign's units run along a seed, "
                                                "fold or subject block, never by arm or comparison")
        if not is_count(item.get("units")):
            raise Refusal("plan-invalid", f"{where}.units must be a positive whole number")
        services = item.get("services")
        if (not isinstance(services, list) or not services or len(set(services)) != len(services)
                or not all(isinstance(s, str) and SERVICE_PATTERN.match(s) for s in services)):
            raise Refusal("plan-invalid", f"{where}.services must be a non-empty list of distinct service names")
        requires = item.get("requires", [])
        if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
            raise Refusal("plan-invalid", f"{where}.requires must be a list of step ids")
        stamps = item.get("stampsIdentical", False)
        if not isinstance(stamps, bool):
            raise Refusal("plan-invalid", f"{where}.stampsIdentical must be true or false")
        resumable = item.get("resumable", False)
        if not isinstance(resumable, bool):
            raise Refusal("plan-invalid", f"{where}.resumable must be true or false")
        checkpoint = item.get("checkpointMinutes")
        if resumable and checkpoint is None:
            raise Refusal("plan-invalid", f"{where}: a resumable step declares checkpointMinutes, the minutes "
                                          "of work between two checkpoints its units write and resume from")
        if not resumable and checkpoint is not None:
            raise Refusal("plan-invalid", f"{where}: checkpointMinutes is declared only with \"resumable\": true")
        if checkpoint is not None and (not is_number(checkpoint) or checkpoint <= 0):
            raise Refusal("plan-invalid", f"{where}.checkpointMinutes must be a positive number, got {checkpoint!r}")
        explicit = item.get("unitMinutes") or {}
        timing = item.get("timing") or {}
        if not isinstance(explicit, dict) or not isinstance(timing, dict):
            raise Refusal("plan-invalid", f"{where}: unitMinutes and timing map a service to its duration")
        minutes, sources = {}, {}
        for svc in services:
            if svc in explicit and svc in timing:
                raise Refusal("plan-invalid", f"{where}: {svc} has both unitMinutes and timing; give one")
            if svc in explicit:
                minutes[svc] = per_service(f"{where}.unitMinutes", {svc: explicit[svc]}, services, False)[svc]
                sources[svc] = "explicit"
            elif svc in timing:
                minutes[svc], sources[svc] = timing_unit_minutes(root, where, svc, timing[svc], item["units"])
            else:
                raise Refusal("missing-input", f"{where}: no per-unit duration on {svc}, never guessed: give "
                                               "unitMinutes or a timing record measured on that service")
        setup = item.get("setupMinutes", default_setup)
        if setup is None:
            raise Refusal("missing-input", f"{where}: setupMinutes is required (a rehearsal's measured setup), "
                                           "per step or for the plan")
        setups = per_service(f"{where}.setupMinutes", setup, services, True)
        missing = [svc for svc in services if svc not in setups]
        if missing:
            raise Refusal("missing-input", f"{where}: no setupMinutes on {', '.join(missing)}")
        steps.append({"id": sid, "units": item["units"], "services": list(services), "requires": list(requires),
                      "stampsIdentical": stamps, "axis": axis, "minutes": minutes, "sources": sources,
                      "setup": {svc: setups[svc] for svc in services}, "resumable": resumable,
                      "checkpoint": None if checkpoint is None else float(checkpoint)})
    for entry in steps:
        unknown = [r for r in entry["requires"] if r not in ids or r == entry["id"]]
        if unknown:
            raise Refusal("plan-invalid", f"{name}: step {entry['id']!r} requires unknown step(s) {', '.join(unknown)}")
    order, done = [], set()
    while len(order) < len(steps):
        ready = [s for s in steps if s["id"] not in done and all(r in done for r in s["requires"])]
        if not ready:
            raise Refusal("plan-invalid", f"{name}: the steps' requires form a cycle")
        order.append(ready[0]["id"])
        done.add(ready[0]["id"])
    return {"steps": steps, "accounts": data.get("accounts")}


def unit_sessions(entry: dict, svc: str, limit: float) -> int | None:
    """How many sessions of `limit` minutes one of the step's units needs on
    `svc`: 1 when the unit plus its setup ends inside the usable session, the
    chained sessions ceil(minutes / (usable session - setup)) when the step is
    resumable from a checkpoint that lands inside one session's work, and None
    when the unit cannot be planned on such a session."""
    minutes, setup, usable = entry["minutes"][svc], entry["setup"][svc], usable_session(limit)
    if minutes + setup <= usable:
        return 1
    work = usable - setup
    if not entry["resumable"] or work <= 0 or entry["checkpoint"] > work:
        return None
    return math.ceil(minutes / work)


def margin_refusal(entry: dict, slots: list[dict]) -> Refusal:
    """The step's units fit no eligible session with the margin."""
    parts, beyond = [], True
    for svc in entry["services"]:
        limits = [slot["limit"] for slot in slots if slot["service"] == svc]
        if not limits:
            continue
        longest = max(limits)
        minutes, setup = entry["minutes"][svc], entry["setup"][svc]
        beyond = beyond and minutes + setup > longest
        parts.append(f"on {svc} one unit takes {num(minutes)} minutes plus a {num(setup)}-minute setup "
                     f"against {margin_text(longest)}")
    detail = "; ".join(parts)
    if entry["resumable"]:
        return Refusal("unit-over-session-margin", f"step {entry['id']!r} is resumable, but its checkpoint every "
                                                   f"{num(entry['checkpoint'])} minutes never lands inside one "
                                                   f"session's usable work ({detail}): checkpoint more often or "
                                                   "split the unit along the declared axis and schedule again")
    advice = ("split it along the declared axis (by fold, seed or subject block, never by arm) or declare the "
              "step resumable from a checkpoint (\"resumable\": true, \"checkpointMinutes\": <minutes>) "
              "and schedule again")
    if beyond:
        return Refusal("unit-over-session-limit", f"step {entry['id']!r}: one unit plus its setup exceeds every "
                                                  f"eligible account's session limit ({detail}): {advice}")
    return Refusal("unit-over-session-margin", f"step {entry['id']!r}: one unit plus its setup exceeds "
                                               f"{SESSION_MARGIN_PERCENT}% of every eligible account's session "
                                               f"limit ({detail}), so it is not plannable as one session: {advice}")


def step_options(entry: dict, slots: list[dict]) -> list[tuple[str, ...]]:
    """The services one step may run on: each allowed service alone, or every
    usable one together only when the step declares identical stamps."""
    usable, present = [], False
    for svc in entry["services"]:
        mine = [slot for slot in slots if slot["service"] == svc]
        present = present or bool(mine)
        if any(unit_sessions(entry, svc, slot["limit"]) is not None for slot in mine):
            usable.append(svc)
    if not present:
        raise Refusal("no-eligible-account", f"step {entry['id']!r}: no eligible account on "
                                             f"{', '.join(entry['services'])} (free-tier Colab owners never "
                                             "join a split, and one account per person per service counts)")
    if not usable:
        raise margin_refusal(entry, slots)
    options = [(svc,) for svc in usable]
    if entry["stampsIdentical"] and len(usable) > 1:
        options.append(tuple(usable))
    return options


def simulate(steps: list[dict], assignment: dict, slots: list[dict]) -> dict:
    """List scheduling of the assigned steps: a step becomes ready when the
    steps it requires end, and each of its units goes to the slot of its
    services where it finishes earliest (ties to the lowest slot). A slot that
    changes step, or would run past its limit, opens a new session and pays
    that service's setup."""
    state = [{"free": 0.0, "step": None, "used": 0.0, "busy": 0.0} for _ in slots]
    timeline, remaining = {}, [s for s in steps if s["id"] in assignment]
    while remaining:
        candidates = [(max((timeline[r]["end"] for r in s["requires"]), default=0.0), index, s)
                      for index, s in enumerate(remaining) if all(r in timeline for r in s["requires"])]
        ready, index, entry = min(candidates, key=lambda c: (c[0], c[1]))
        remaining.pop(index)
        services = assignment[entry["id"]]
        start, end, shares = None, ready, {}
        for _ in range(entry["units"]):
            best = None
            for position, slot in enumerate(slots):
                svc = slot["service"]
                if svc not in services:
                    continue
                minutes, setup = entry["minutes"][svc], entry["setup"][svc]
                chain = unit_sessions(entry, svc, slot["limit"])
                if chain is None:
                    continue
                current = state[position]
                begin = max(current["free"], ready)
                same = (chain == 1 and current["step"] == entry["id"]
                        and current["used"] + minutes <= slot["limit"])
                finish = begin + minutes + (0.0 if same else setup * chain)
                if best is None or finish < best[0]:
                    best = (finish, position, begin, same, minutes, setup, chain)
            finish, position, begin, same, minutes, setup, chain = best
            current = state[position]
            # A chained unit fills its last session: the next unit opens a new one.
            current["used"] = (current["used"] + minutes if same else
                               setup + minutes if chain == 1 else slots[position]["limit"])
            current["busy"] += minutes + (0.0 if same else setup * chain)
            current["free"], current["step"] = finish, entry["id"]
            start = begin if start is None else min(start, begin)
            end = max(end, finish)
            share = shares.setdefault(slots[position]["account"], {"units": 0, "slots": set(), "sessions": 0})
            share["units"] += 1
            share["slots"].add(position)
            share["sessions"] += 0 if same else chain
        timeline[entry["id"]] = {"start": start, "end": end, "ready": ready, "shares": shares}
    busy: dict[int, float] = {}
    for position, slot in enumerate(slots):
        busy[slot["account"]] = busy.get(slot["account"], 0.0) + state[position]["busy"]
    makespan = max((item["end"] for item in timeline.values()), default=0.0)
    return {"timeline": timeline, "busy": busy, "makespan": makespan}


def serial_minutes(entry: dict, accounts: list[dict]) -> float:
    """One step on one session at a time of its fastest eligible account."""
    best = None
    for account in accounts:
        svc = account["service"]
        if svc not in entry["services"]:
            continue
        limit, minutes, setup = account["sessionHours"] * 60, entry["minutes"][svc], entry["setup"][svc]
        chain = unit_sessions(entry, svc, limit)
        if chain is None:
            continue
        if chain == 1:
            per_session = int((limit - setup) // minutes)
            sessions = math.ceil(entry["units"] / per_session)
            total = entry["units"] * minutes + sessions * setup
        else:
            total = entry["units"] * (minutes + chain * setup)
        best = total if best is None else min(best, total)
    return best


def cmd_schedule(args, root: Path, today: str) -> dict:
    if args.plan is None:
        raise Refusal("missing-input", "--plan is required: the project's remote steps, their units, per-unit "
                                       "durations per service, dependencies and allowed services")
    plan = load_plan(root, args.plan)
    entries = load_accounts(root, args.account, args.accounts_file, plan["accounts"])
    pool = account_pool(entries)
    accounts = pool["eligible"]
    slots = [{"account": index, "service": entry["service"], "limit": entry["sessionHours"] * 60}
             for index, entry in enumerate(accounts) for _ in range(entry["sessions"])]
    steps = plan["steps"]
    options = {entry["id"]: step_options(entry, slots) for entry in steps}
    combos = 1
    for entry in steps:
        combos *= len(options[entry["id"]])

    def quota_over(busy: dict) -> int:
        return sum(1 for index, entry in enumerate(accounts)
                   if entry["quotaHours"] is not None and busy.get(index, 0.0) / 60 > entry["quotaHours"])

    def score(sim: dict, picks: tuple) -> tuple:
        return (round(sim["makespan"], 6), quota_over(sim["busy"]), round(sum(sim["busy"].values()), 6), picks)

    best, evaluated = None, 0
    if combos <= EXHAUSTIVE_LIMIT:
        mode = "exhaustive"
        for picks in _product([range(len(options[e["id"]])) for e in steps]):
            assignment = {e["id"]: options[e["id"]][pick] for e, pick in zip(steps, picks)}
            sim = simulate(steps, assignment, slots)
            evaluated += 1
            key = score(sim, picks)
            if best is None or key < best[0]:
                best = (key, assignment, sim)
    else:
        mode = "greedy"
        assignment, picks = {}, ()
        for entry in steps:
            choice = None
            for pick, option in enumerate(options[entry["id"]]):
                trial = dict(assignment, **{entry["id"]: option})
                sim = simulate(steps, trial, slots)
                evaluated += 1
                key = score(sim, picks + (pick,))
                if choice is None or key < choice[0]:
                    choice = (key, pick, option, sim)
            assignment[entry["id"]] = choice[2]
            picks += (choice[1],)
            best = (choice[0], assignment, choice[3])
    _, assignment, sim = best

    reasons = pool_reasons(pool)
    report_steps, multi = [], []
    for entry in steps:
        chosen = list(assignment[entry["id"]])
        if len(chosen) > 1:
            multi.append(entry["id"])
        line = sim["timeline"][entry["id"]]
        shares = []
        for index in sorted(line["shares"]):
            share = line["shares"][index]
            shares.append({"account": accounts[index]["label"], "owner": accounts[index]["owner"],
                           "service": accounts[index]["service"], "units": share["units"],
                           "slotsUsed": len(share["slots"]), "sessions": share["sessions"]})
        report_steps.append({
            "id": entry["id"], "units": entry["units"], "requires": entry["requires"], "services": chosen,
            "allowedServices": entry["services"],
            "unitMinutes": {svc: num(entry["minutes"][svc]) for svc in chosen},
            "unitMinutesSource": {svc: entry["sources"][svc] for svc in chosen},
            "setupMinutes": {svc: num(entry["setup"][svc]) for svc in chosen},
            "readyMinutes": num(line["ready"]), "startMinutes": num(line["start"]),
            "endMinutes": num(line["end"]), "durationMinutes": num(line["end"] - line["start"]),
            "shares": shares})
        if entry["resumable"]:
            limits = {svc: max(a["sessionHours"] * 60 for a in accounts if a["service"] == svc) for svc in chosen}
            chains = {svc: unit_sessions(entry, svc, limits[svc]) for svc in chosen}
            report_steps[-1].update({"resumable": True, "checkpointMinutes": num(entry["checkpoint"]),
                                     "sessionsPerUnit": chains})
            for svc in chosen:
                if chains[svc] and chains[svc] > 1:
                    reasons.append(f"step {entry['id']!r}: each {num(entry['minutes'][svc])}-minute unit on {svc} "
                                   f"exceeds {margin_text(limits[svc])} and runs {chains[svc]} chained sessions "
                                   f"on the same account, resuming from its checkpoint every "
                                   f"{num(entry['checkpoint'])} minutes; each session pays the "
                                   f"{num(entry['setup'][svc])}-minute setup")
    for step_id in multi:
        reasons.append(f"step {step_id!r} runs on {', '.join(assignment[step_id])} under declared identical stamps "
                       "(accelerator model, CUDA, torch): verify --shards must confirm them before any merge")
    quota, units_per = [], {}
    for line in sim["timeline"].values():
        for index, share in line["shares"].items():
            units_per[index] = units_per.get(index, 0) + share["units"]
    for index, entry in enumerate(accounts):
        hours = sim["busy"].get(index, 0.0) / 60
        limit = entry["quotaHours"]
        over = None if limit is None else hours > limit
        quota.append({"account": entry["label"], "owner": entry["owner"], "service": entry["service"],
                      "units": units_per.get(index, 0), "gpuHours": num(hours),
                      "quotaHours": None if limit is None else num(limit), "overQuota": over,
                      "quotaSource": entry.get("quotaSource"), "quotaDate": entry.get("quotaDate")})
        if over:
            reasons.append(f"{entry['label']} would spend {num(hours)} GPU hours, over its {num(limit)}-hour weekly "
                           "quota: reduce the units, add an owner's account or wait for the quota to reset")
        elif over is None and units_per.get(index):
            reasons.append(f"{entry['label']} has an unknown weekly quota: not checked; record it before the launch")
    serial = sum(serial_minutes(entry, accounts) for entry in steps)
    makespan = sim["makespan"]
    if makespan > QUOTA_WEEK_MINUTES:
        reasons.append(f"the plan runs {num(makespan / 60)} hours, more than one quota week: quotas reset during it")
    used = [entry["label"] for index, entry in enumerate(accounts) if units_per.get(index)]
    checks = [
        {"id": "axis-not-arm", "held": True,
         "detail": "every step's units run along its declared axis; a step whose axis is an arm or a comparison is refused"},
        {"id": "one-service-per-campaign", "held": True,
         "detail": ("every step runs on one service" if not multi else
                    f"every step runs on one service except {', '.join(multi)}, under declared identical stamps")},
        {"id": "one-account-per-person", "held": True,
         "detail": (f"{len(accounts)} eligible account(s), one per owner per service; "
                    f"left out: {', '.join(pool['ignored']) or 'none'}; free-tier Colab excluded: "
                    f"{', '.join(item['account'] for item in pool['excluded']) or 'none'}")},
        {"id": "no-pooled-timing", "held": True,
         "detail": "each service's per-unit duration is its own (explicit or its own host's timing record); none is pooled or scaled from another"},
        {"id": "rehearse-each-account", "held": None,
         "detail": "not checkable here: every account the plan uses needs its own passing rehearsal before its "
                   f"campaign's gate: {', '.join(used)}"},
        {"id": "launch-is-the-operator-s", "held": True,
         "detail": "this plan is never launch authorization: placement stays with distribute and each step's launch with its own gate and the operator's consent"},
    ]
    return {"plan": args.plan, "accounts": [entry["label"] for entry in accounts],
            "excludedAccounts": [{"account": item["account"], "tier": item["tier"]} for item in pool["excluded"]],
            "ignoredAccounts": pool["ignored"], "steps": report_steps,
            "makespanMinutes": num(makespan), "makespanHours": num(makespan / 60),
            "serialMinutes": num(serial), "serialHours": num(serial / 60),
            "speedup": num(serial / makespan) if makespan else None, "savedMinutes": num(serial - makespan),
            "quota": quota, "quotaOk": not any(item["overQuota"] for item in quota),
            "search": {"mode": mode, "assignmentsEvaluated": evaluated, "objective":
                       "minimal makespan, then fewest accounts over quota, then fewest GPU hours"},
            "doctrineChecks": checks, "reasons": reasons, "launchAuthorization": False}


def _product(ranges: list) -> list[tuple]:
    combos = [()]
    for values in ranges:
        combos = [combo + (value,) for combo in combos for value in values]
    return combos


def cmd_checklist(args, root: Path, today: str) -> dict:
    return {"checklist": [dict(item) for item in CHECKLIST]}


def cmd_stamp_fields(args, root: Path, today: str) -> dict:
    return {"identicalAcrossShards": list(STAMP_FIELDS)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parallelism_cli.py", description=OBJECTIVE_FLOW["purpose"])
    parser.add_argument("--root", default=".", help="workspace root (default: the current directory)")
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="{" + ",".join(VERBS) + "}")
    assess = verbs.add_parser("assess", help="serial vs parallel makespan, quota, verdict and checklist")
    for flag in ("--units", "--unit-minutes", "--owners", "--accounts", "--sessions-per-account",
                 "--session-limit-hours", "--quota-hours", "--setup-minutes", "--units-file",
                 "--axis", "--quota-source", "--quota-date", "--record", "--service", "--tiers"):
        assess.add_argument(flag, default=None)
    assess.add_argument("--stamps-identical", action="store_true",
                        help="the shards of a mixed-service campaign declare identical environment stamps")
    assess.add_argument("--account", action="append", default=None,
                        help="<owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>], repeated")
    assess.add_argument("--accounts-file", default=None, help="a JSON list of accounts with their own limits")
    assess.set_defaults(func=cmd_assess)
    plan = verbs.add_parser("schedule", help="place remote steps on services and units on accounts, read-only")
    plan.add_argument("--plan", default=None)
    plan.add_argument("--account", action="append", default=None)
    plan.add_argument("--accounts-file", default=None)
    plan.set_defaults(func=cmd_schedule)
    estimate = verbs.add_parser("estimate", help="processing-time range per stage and host from a timing probe")
    estimate.add_argument("--timing", default=None)
    estimate.add_argument("--stage", default=None)
    estimate.add_argument("--host", action="append", default=None)
    estimate.add_argument("--record", default=None)
    estimate.add_argument("--json", action="store_true", help="JSON output (the only output; accepted for symmetry)")
    estimate.set_defaults(func=cmd_estimate)
    verbs.add_parser("checklist", help="the reproducibility checklist").set_defaults(func=cmd_checklist)
    verbs.add_parser("stamp-fields", help="the fields to declare identicalAcrossShards").set_defaults(
        func=cmd_stamp_fields)
    return parser


def run(argv: list[str] | None = None, today: str | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(os.path.realpath(Path(args.root).expanduser()))
    today = today or datetime.date.today().isoformat()
    try:
        result = args.func(args, root, today)
    except Refusal as refusal:
        print(json.dumps({"error": refusal.code, "message": refusal.message, "objective": OBJECTIVE_FLOW},
                         indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
