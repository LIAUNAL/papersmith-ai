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

VERBS = ("assess", "estimate", "checklist", "stamp-fields")

ERROR_CODES = (
    "missing-input", "bad-argument", "units-file-missing", "units-file-invalid",
    "duplicate-unit", "units-mismatch", "axis-is-comparison",
    "record-outside-workspace", "record-missing", "timing-missing", "timing-invalid",
    "mixed-devices", "timing-outside-workspace",
)

#: The verdict's thresholds. Stated in every output so the verdict can be read
#: against them rather than trusted.
MIN_SPEEDUP = 1.5
MIN_SAVED_MINUTES = 30

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
    """Greedy longest-first packing onto `slots` concurrent sessions in a row.

    Each slot runs sessions back to back; a session pays `setup` once and may
    not run past `limit`. A unit goes to the slot where it finishes earliest,
    ties to the lowest slot, so the output is a pure function of the inputs.
    """
    state = [{"finish": 0.0, "used": None, "units": 0, "busy": 0.0} for _ in range(slots)]
    order = sorted(units, key=lambda unit: (-unit["minutes"], unit["id"]))
    for unit in order:
        best, best_finish, best_new = 0, None, False
        for index, slot in enumerate(state):
            if slot["used"] is not None and slot["used"] + unit["minutes"] <= limit:
                finish, new = slot["finish"] + unit["minutes"], False
            else:
                finish, new = slot["finish"] + setup + unit["minutes"], True
            if best_finish is None or finish < best_finish:
                best, best_finish, best_new = index, finish, new
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
    over = [unit["id"] for unit in units if unit["minutes"] + setup > limit]
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
        reasons.append(f"{len(over)} unit(s) need more than one session's {num(limit)} minutes "
                       f"including the {num(setup)}-minute setup: split them along the declared axis "
                       "(more seeds, folds or subject blocks per unit, never by arm) and assess again")
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
    unknown = sorted(set(data) - TIMING_KEYS)
    if unknown:
        bad(f"unknown key(s) {', '.join(unknown)}; schema 1 holds schema, measurements and scales")
    if data.get("schema") != 1 or isinstance(data.get("schema"), bool):
        bad(f"schema must be 1, got {data.get('schema')!r}")
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
        extra = sorted(set(item) - MEASUREMENT_KEYS)
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

    by_host: dict[str, list[dict]] = {}
    for item in data["measurements"]:
        by_host.setdefault(item["host"], []).append(item)
    for host, items in by_host.items():
        devices = sorted({item["device"] for item in items})
        if len(devices) > 1:
            raise Refusal("mixed-devices", f"host {host} was timed on {', '.join(devices)}: timing is never "
                                           "pooled across machines; keep one device per host in the record")
    hosts = ["local", *sorted(host for host in by_host if host != "local")]
    hosts += [host for host in asked if host not in hosts]
    estimates = {
        name: {host: host_estimate(by_host[host], data["scales"][name]) if host in by_host else UNMEASURED
               for host in hosts}
        for name in stages}
    result = {"estimates": estimates, "placement": {name: placement(name, estimates[name]) for name in stages},
              "placementRules": PLACEMENT_RULES, "timing": args.timing, "range": RANGE_NOTE,
              "unmeasuredMeans": "no measurement on that host; a remote host is never estimated from local timings",
              "launchAuthorization": False}
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
    assess.set_defaults(func=cmd_assess)
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
