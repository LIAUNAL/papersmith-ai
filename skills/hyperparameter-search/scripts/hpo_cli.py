#!/usr/bin/env python3
"""hyperparameter-search: a nested, equal-budget hyperparameter search that the
experimental deliberation judged worthwhile, recorded per arm and outer fold.

Stdlib only, no network, no credentials. `plan` validates the search plan
(`<target>/<Name>/hpo/plan.json`) against the rules that keep a search fair
and, given a timing probe, estimates its cost per host as an upper bound.
`report` runs `optuna_report.py` under the TARGET's own interpreter, which is
the only place the search library and matplotlib are installed, and `status`
reads the summaries that report wrote under `<Name>/Results/hpo/`.

It never runs the search itself and never launches anything: a remote search
is placed and launched like any full run, through remote-execution and behind
the operator's consent.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

OBJECTIVE_FLOW = {
    "purpose": (
        "tune the hyperparameters the experimental deliberation judged worth a "
        "search, inside each outer fold and with one trial budget for every arm, "
        "and record what the search found with its importance and contour figures"),
    "stages": [
        {"stage": "planned",
         "establishes": "plan accepts <Name>/hpo/plan.json: one trial budget for every arm, a seeded sampler, a search nested inside each outer fold, nothing the experiments test tuned, and the importance evaluator named",
         "behindWhen": "no <Name>/hpo/plan.json exists, or plan refuses it"},
        {"stage": "searched",
         "establishes": "one study per arm and outer fold, named <arm>-fold<k>, ran its declared trials into <Name>/hpo/studies.db where it was placed",
         "behindWhen": "<Name>/hpo/studies.db is missing or holds no study for an arm and fold the plan declares"},
        {"stage": "reported",
         "establishes": "report wrote Results/hpo/<study>/summary.json with its importance, contour and history figures for every study, and status read them back",
         "behindWhen": "status lists a missing study or a missing figure"},
    ],
    "arrival": (
        "a recorded search per arm and outer fold, with its importance and contour "
        "figures read back, whose tuned values are then frozen per outer fold for "
        "every seed of the full run"),
    "humanStops": [
        "whether a search is worthwhile at all: the experimental deliberation decides it, never this skill",
        "launching a remote search: the operator's, through remote-execution's consent and gate",
    ],
}

VERBS = ("plan", "report", "status")

ERROR_CODES = (
    "plan-missing", "plan-invalid", "unequal-budget", "unseeded-sampler", "bad-space",
    "tunes-fixed", "not-nested", "bad-evaluator", "timing-missing", "timing-invalid",
    "mixed-devices", "target-missing", "bad-name", "storage-missing", "venv-missing",
    "optuna-missing", "report-failed",
)

PLAN_KEYS = ("schema", "objective", "sampler", "pruner", "nTrials", "maxEpochs", "nested",
             "arms", "space", "fixed", "importance")
DIRECTIONS = ("minimize", "maximize")
PRUNERS = ("MedianPruner", "none")
KINDS = ("float", "int", "categorical")
EVALUATORS = ("fanova", "ped-anova", "mean-decrease-impurity")
SEEDED_EVALUATORS = ("fanova", "mean-decrease-impurity")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
STUDY_PATTERN = re.compile(r"^(?P<arm>.+)-fold(?P<fold>\d+)$")
FIGURES = ("contour", "importance", "history")

#: The estimate's spread, and what it is: an upper bound, because every trial
#: is counted at its full epoch budget.
ESTIMATE_RANGE = 0.20
RANGE_NOTE = ("±20%, single-probe extrapolation, an upper bound: every trial is counted at "
              "maxEpochs, and pruning and early stopping only lower it")
#: Schema 2 (the timing probe's) is estimated per candidate, at its fastest
#: measured setting.
RANGE_NOTE_V2 = RANGE_NOTE + "; each candidate is read at its fastest measured setting"

TIMING_HOST = re.compile(r"^(local|[a-z0-9-]+:[A-Za-z0-9_.-]+)$")
SKILL_SCRIPTS = Path(__file__).resolve().parent


class Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def num(value: float) -> float | int:
    rounded = round(value, 3)
    return int(rounded) if rounded == int(rounded) else rounded


# ------------------------------------------------------------- the plan
def load_plan(path: Path) -> dict:
    """The plan, schema 1, under every rule the skill enforces -- or a refusal."""
    if not path.is_file():
        raise Refusal("plan-missing", f"{path} does not exist; write the plan the deliberation declared")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("plan-invalid", f"{path} is not JSON: {exc}")

    def invalid(message: str):
        raise Refusal("plan-invalid", f"{path.name}: {message}")

    if not isinstance(plan, dict):
        invalid("the plan must be a JSON object")
    missing = [key for key in PLAN_KEYS if key not in plan]
    if missing:
        invalid(f"missing {', '.join(missing)}")
    if plan["schema"] != 1 or isinstance(plan["schema"], bool):
        invalid(f"schema must be 1, got {plan['schema']!r}")
    objective = plan["objective"]
    if (not isinstance(objective, dict) or not isinstance(objective.get("metric"), str)
            or not objective["metric"].strip() or objective.get("direction") not in DIRECTIONS):
        invalid("objective must be {metric: <name>, direction: minimize|maximize}")

    arms = plan["arms"]
    if (not isinstance(arms, list) or not arms
            or not all(isinstance(arm, str) and NAME_PATTERN.match(arm) for arm in arms)):
        invalid("arms must be a non-empty list of arm ids (letters, digits, '.', '_', '-')")
    if len(set(arms)) != len(arms):
        invalid("an arm id appears twice")
    if isinstance(plan["nTrials"], dict):
        raise Refusal("unequal-budget", "nTrials is one number for every arm, baselines included: a "
                                        "tuned arm compared with a less-tuned one measures the budget, "
                                        "not the method")
    if not is_int(plan["nTrials"]) or plan["nTrials"] <= 0:
        invalid(f"nTrials must be a positive whole number, got {plan['nTrials']!r}")
    if not is_int(plan["maxEpochs"]) or plan["maxEpochs"] <= 0:
        invalid(f"maxEpochs must be a positive whole number, got {plan['maxEpochs']!r}")

    sampler = plan["sampler"]
    if not isinstance(sampler, dict) or not isinstance(sampler.get("name"), str) or not sampler["name"]:
        invalid("sampler must be {name: <sampler>, seed: <int>}")
    if not is_int(sampler.get("seed")):
        raise Refusal("unseeded-sampler", "sampler.seed is required: an unseeded sampler proposes "
                                          "different trials on every run, so the search cannot be repeated")
    pruner = plan["pruner"]
    if not isinstance(pruner, dict) or pruner.get("name") not in PRUNERS:
        invalid(f"pruner.name must be one of {', '.join(PRUNERS)}")
    if pruner["name"] != "none":
        for key in ("nStartupTrials", "nWarmupSteps"):
            if not is_int(pruner.get(key)) or pruner[key] < 0:
                invalid(f"pruner.{key} must be a non-negative whole number")

    check_space(plan["space"])
    fixed = plan["fixed"]
    if not isinstance(fixed, list) or not all(isinstance(name, str) and name for name in fixed):
        invalid("fixed must be a list of the independent variables the experiments test")
    tuned = sorted({item["name"] for item in plan["space"]} & set(fixed))
    if tuned:
        raise Refusal("tunes-fixed", f"{', '.join(tuned)} is an independent variable the experiments "
                                     "test, so it is never tuned: take it out of space")

    nested = plan["nested"]
    if not isinstance(nested, dict) or not is_int(nested.get("outerFolds")) or nested["outerFolds"] <= 0:
        invalid("nested.outerFolds must be a positive whole number")
    statement = nested.get("innerValidation")
    if nested["outerFolds"] > 1 and (not isinstance(statement, str) or not statement.strip()):
        raise Refusal("not-nested", "nested.innerValidation must state the inner validation: the search "
                                    "runs inside each outer fold's training subjects only, and the outer "
                                    "fold's test subjects are never seen")

    importance = plan["importance"]
    if not isinstance(importance, dict) or importance.get("evaluator") not in EVALUATORS:
        raise Refusal("bad-evaluator", f"importance.evaluator must be one of {', '.join(EVALUATORS)}; "
                                       "it is always named, because the library's default changes the ranking")
    if importance["evaluator"] in SEEDED_EVALUATORS and not is_int(importance.get("seed")):
        raise Refusal("bad-evaluator", f"importance.seed is required for {importance['evaluator']}")
    check = importance.get("check")
    if check is not None and (check not in EVALUATORS or check == importance["evaluator"]):
        raise Refusal("bad-evaluator", "importance.check must be null or a second evaluator, different "
                                       f"from the first, one of {', '.join(EVALUATORS)}")
    if check in SEEDED_EVALUATORS and not is_int(importance.get("seed")):
        raise Refusal("bad-evaluator", f"importance.seed is required: the check evaluator {check} is seeded too")
    return plan


def check_space(space) -> None:
    def bad(message: str):
        raise Refusal("bad-space", message)

    if not isinstance(space, list) or not space:
        bad("space must hold at least one parameter")
    names = set()
    for index, item in enumerate(space):
        where = f"space[{index}]"
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            bad(f"{where} must be an object with a name")
        if item["name"] in names:
            bad(f"{where}: {item['name']} appears twice")
        names.add(item["name"])
        kind = item.get("kind")
        if kind not in KINDS:
            bad(f"{where}.kind must be one of {', '.join(KINDS)}, got {kind!r}")
        if kind == "categorical":
            choices = item.get("choices")
            if not isinstance(choices, list) or len(choices) < 2:
                bad(f"{where}: a categorical parameter needs at least two choices")
            continue
        low, high = item.get("low"), item.get("high")
        if not (is_number(low) and is_number(high)) or (kind == "int" and not (is_int(low) and is_int(high))):
            bad(f"{where}: low and high must be numbers ({kind})")
        if low >= high:
            bad(f"{where}: low {low} must be below high {high}")
        if item.get("log", False) not in (True, False):
            bad(f"{where}.log must be true or false")
        if item.get("log") and low <= 0:
            bad(f"{where}: a log-scaled parameter needs low > 0")


def study_names(plan: dict) -> list[str]:
    folds = plan["nested"]["outerFolds"]
    return [f"{arm}-fold{k}" for arm in plan["arms"] for k in range(1, folds + 1)]


# ------------------------------------------------------------- the estimate
def parallelism_cli():
    """`remote-parallelism`'s CLI module, for its schema 2 timing reader and
    its candidate rules -- never a second copy of them."""
    module_name = "hyperparameter_search_parallelism_cli"
    if module_name not in sys.modules:
        script = SKILL_SCRIPTS.parents[1] / "remote-parallelism" / "scripts" / "parallelism_cli.py"
        if not script.is_file():
            raise Refusal("timing-invalid", f"a schema 2 timing record is read by {script}, which is missing")
        spec = importlib.util.spec_from_file_location(module_name, script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module
    return sys.modules[module_name]


def load_timing(path: Path) -> list[dict] | dict:
    """Schema 1's measurements, or the whole schema 2 record the timing probe
    writes, validated by remote-parallelism's own reader."""
    if not path.is_file():
        raise Refusal("timing-missing", f"{path} does not exist; run the timing probe first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("timing-invalid", f"{path} is not JSON: {exc}")
    if isinstance(data, dict) and data.get("schema") == 2 and not isinstance(data.get("schema"), bool):
        reader = parallelism_cli()
        try:
            return reader.load_timing(path, path.name)
        except reader.Refusal as refusal:
            raise Refusal(refusal.code, refusal.message)
    if not isinstance(data, dict) or data.get("schema") != 1 or isinstance(data.get("schema"), bool):
        raise Refusal("timing-invalid", f"{path.name}: the timing record must be schema 1 or 2")
    measurements = data.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        raise Refusal("timing-invalid", f"{path.name}: measurements must be a non-empty list")
    for index, item in enumerate(measurements):
        if (not isinstance(item, dict) or not isinstance(item.get("host"), str)
                or not TIMING_HOST.match(item["host"]) or not isinstance(item.get("device"), str)
                or not item["device"] or item.get("unit") != "epoch"
                or not is_number(item.get("secondsPerUnit")) or item["secondsPerUnit"] <= 0):
            raise Refusal("timing-invalid", f"{path.name}: measurements[{index}] needs a host, a device, "
                                            "unit epoch and a positive secondsPerUnit")
    return measurements


def search_seconds(plan: dict, items: list[dict]) -> dict:
    trials, arms = plan["nTrials"], len(plan["arms"])
    folds, epochs = plan["nested"]["outerFolds"], plan["maxEpochs"]
    per_unit = sum(float(item["secondsPerUnit"]) for item in items) / len(items)
    seconds = trials * arms * folds * epochs * per_unit
    return {
        "seconds": num(seconds), "low": num(seconds * (1 - ESTIMATE_RANGE)),
        "high": num(seconds * (1 + ESTIMATE_RANGE)), "secondsPerUnit": num(per_unit),
        "measurements": len(items), "device": items[0]["device"],
        "formula": (f"{trials} trials x {arms} arms x {folds} outer folds x {epochs} epochs x "
                    f"mean secondsPerUnit {num(per_unit)} s = {num(seconds)} s"),
    }


def estimate_v2(plan: dict, data: dict, extra_hosts: list[str]) -> dict:
    """Schema 2: one row per candidate, from its own rows at its fastest measured
    setting, so one host's CPU and accelerator rows are never pooled. A host
    asked for (and `local`) with no candidate measured reads `unmeasured`."""
    reader = parallelism_cli()
    try:
        _, by_candidate = reader.measured_candidates(data)
    except reader.Refusal as refusal:
        raise Refusal(refusal.code, refusal.message)
    result: dict = {}
    hosts = set()
    for candidate, items in sorted(by_candidate.items()):
        rows, _ = reader.best_setting(items)
        host = rows[0]["host"]
        hosts.add(host)
        result[candidate] = dict(search_seconds(plan, rows), candidate=candidate, host=host,
                                 settings={key: rows[0][key] for key in reader.SETTING_KEYS if key in rows[0]})
    for host in sorted({"local", *extra_hosts} - hosts):
        result[host] = "unmeasured"
    return dict(sorted(result.items()))


def estimate(plan: dict, measurements: list[dict], extra_hosts: list[str]) -> dict:
    by_host: dict[str, list[dict]] = {}
    for item in measurements:
        by_host.setdefault(item["host"], []).append(item)
    for host, items in by_host.items():
        devices = sorted({item["device"] for item in items})
        if len(devices) > 1:
            raise Refusal("mixed-devices", f"{host} was timed on {', '.join(devices)}; timing is never "
                                           "pooled across machines")
    result: dict = {}
    for host in sorted({"local", *by_host, *extra_hosts}):
        items = by_host.get(host)
        result[host] = search_seconds(plan, items) if items else "unmeasured"
    return result


def cmd_plan(args) -> dict:
    path = Path(args.file).expanduser().resolve()
    plan = load_plan(path)
    studies = study_names(plan)
    result = {
        "plan": str(path), "valid": True, "studies": studies,
        "storage": f"sqlite:///{path.parent / 'studies.db'}",
        "trialsPerStudy": plan["nTrials"], "trialsTotal": plan["nTrials"] * len(studies),
        "arms": list(plan["arms"]), "outerFolds": plan["nested"]["outerFolds"],
        "sampler": plan["sampler"], "importance": plan["importance"], "fixed": list(plan["fixed"]),
        "launchAuthorization": False,
    }
    if args.host and args.timing is None:
        raise Refusal("timing-missing", "--host adds a row to the estimate, which needs --timing <timing.json>")
    if args.timing is not None:
        timing = load_timing(Path(args.timing).expanduser().resolve())
        if isinstance(timing, dict):
            result["estimate"] = estimate_v2(plan, timing, args.host or [])
            result["range"] = RANGE_NOTE_V2
        else:
            result["estimate"] = estimate(plan, timing, args.host or [])
            result["range"] = RANGE_NOTE
    return result


# ------------------------------------------------------------- report and status
def product(args) -> Path:
    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise Refusal("target-missing", f"{target} is not a directory")
    if not NAME_PATTERN.match(args.name) or ".." in args.name:
        raise Refusal("bad-name", f"--name {args.name!r} must be one product folder name")
    return target


def target_python(target: Path, override: str | None) -> Path:
    if override is not None:
        python = Path(override).expanduser()
        if not python.is_file():
            raise Refusal("venv-missing", f"--python {python} does not exist")
        return python
    for candidate in (target / ".venv" / "bin" / "python", target / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    raise Refusal("venv-missing", f"{target}/.venv has no interpreter: create the target's own venv "
                                  "and install the search library and matplotlib there, never system-wide")


def cmd_report(args) -> dict:
    target = product(args)
    folder = target / args.name
    plan_path = folder / "hpo" / "plan.json"
    load_plan(plan_path)
    storage = folder / "hpo" / "studies.db"
    if not storage.is_file():
        raise Refusal("storage-missing", f"{storage} does not exist: the search has not run, or it ran "
                                         "elsewhere and its storage was not fetched")
    python = target_python(target, args.python)
    probe = subprocess.run([str(python), "-I", "-c", "import optuna, matplotlib"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        raise Refusal("optuna-missing", f"{python} cannot import optuna and matplotlib: install them in "
                                        "the target's venv")
    out = folder / "Results" / "hpo"
    proc = subprocess.run([str(python), "-I", str(SKILL_SCRIPTS / "optuna_report.py"),
                           "--plan", str(plan_path), "--storage", f"sqlite:///{storage}", "--out", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        raise Refusal("report-failed", "optuna_report.py failed: " + " | ".join(tail))
    try:
        written = json.loads(proc.stdout)
    except ValueError:
        raise Refusal("report-failed", "optuna_report.py printed no JSON")
    return {"target": str(target), "name": args.name, "python": str(python), "results": str(out),
            "summaries": written.get("summaries", []), "notes": written.get("notes", [])}


def top_parameter(record: dict) -> str | None:
    values = (record.get("importance") or {}).get("values") or {}
    numeric = {name: value for name, value in values.items() if is_number(value)}
    return max(numeric, key=lambda name: numeric[name]) if numeric else None


def cmd_status(args) -> dict:
    target = product(args)
    folder = target / args.name
    rows, unreadable = [], []
    for path in sorted((folder / "Results" / "hpo").glob("*/summary.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            unreadable.append(str(path.relative_to(folder)))
            continue
        figures = record.get("figures") or {}
        missing = [kind for kind in FIGURES
                   if figures.get(kind) and not (path.parent / figures[kind]).is_file()]
        rows.append({
            "study": record.get("study", path.parent.name), "arm": record.get("arm"),
            "fold": record.get("fold"), "trials": record.get("nTrials"),
            "complete": record.get("complete"), "pruned": record.get("pruned"),
            "bestValue": record.get("bestValue"), "bestParams": record.get("bestParams"),
            "topParameter": top_parameter(record),
            "evaluator": (record.get("importance") or {}).get("evaluator"),
            "figures": {kind: figures.get(kind) for kind in FIGURES}, "missingFigures": missing,
            "notes": record.get("notes", []), "summary": str(path.relative_to(folder)),
        })
    plan_path = folder / "hpo" / "plan.json"
    planned, missing_studies = False, []
    try:
        plan = load_plan(plan_path)
        planned = True
        found = {row["study"] for row in rows}
        missing_studies = [name for name in study_names(plan) if name not in found]
    except Refusal:
        plan = None
    searched = (folder / "hpo" / "studies.db").is_file()
    complete = bool(rows) and not missing_studies and not unreadable and not any(
        row["missingFigures"] for row in rows)
    stage = ("reported" if complete else "searched" if searched or rows
             else "planned" if planned else None)
    return {"target": str(target), "name": args.name, "stage": stage, "studies": rows,
            "missingStudies": missing_studies, "unreadable": unreadable,
            "planValid": planned, "launchAuthorization": False}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hpo_cli.py", description=OBJECTIVE_FLOW["purpose"])
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="{" + ",".join(VERBS) + "}")
    plan = verbs.add_parser("plan", help="validate the search plan; with --timing, estimate its cost per host")
    plan.add_argument("--file", required=True)
    plan.add_argument("--timing", default=None)
    plan.add_argument("--host", action="append", default=None,
                      help="a host to report even without a measurement (<host>:<owner>)")
    plan.set_defaults(func=cmd_plan)
    report = verbs.add_parser("report", help="write summary.json and figures per study, under the target venv")
    report.add_argument("--target", required=True)
    report.add_argument("--name", required=True)
    report.add_argument("--python", default=None)
    report.set_defaults(func=cmd_report)
    status = verbs.add_parser("status", help="read Results/hpo/*/summary.json back")
    status.add_argument("--target", required=True)
    status.add_argument("--name", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
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
