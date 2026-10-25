#!/usr/bin/env python3
"""Write one summary.json and its figures per study of a hyperparameter search.

Runs under the TARGET's own interpreter (`<target>/.venv`), the only place the
search library and matplotlib are installed; `hpo_cli.py report` starts it with
`-I`. Every study in the storage is loaded, and for each one it writes
`<out>/<study>/summary.json` plus `contour`, `importance` and `history` figures
as PNG and PDF. Importance comes from the evaluator the plan names, never the
library's default, and is descriptive: it ranks which hyperparameters moved the
objective in this search, it tests no hypothesis. A figure that cannot be drawn
is `null` in the summary, with the reason in `notes`.

Prints one JSON object on stdout: `{"summaries": [...], "notes": [...]}`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import sys
import warnings
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

# Optuna and matplotlib belong to the target's venv, never to the forge: the
# guard keeps them out of the forge interpreter's required imports, and hpo_cli
# refuses `optuna-missing` before this script ever runs without them.
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import optuna
    from optuna.importance import (
        FanovaImportanceEvaluator,
        MeanDecreaseImpurityImportanceEvaluator,
        PedAnovaImportanceEvaluator,
        get_param_importances,
    )
    from optuna.trial import TrialState
except ImportError as exc:  # pragma: no cover - hpo_cli probes for these first
    sys.exit(f"optuna_report needs optuna and matplotlib in the target's venv: {exc}")

warnings.filterwarnings("ignore", category=optuna.exceptions.ExperimentalWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)

STUDY_PATTERN = re.compile(r"^(?P<arm>.+)-fold(?P<fold>\d+)$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
CONTOUR_PARAMS = 3


def evaluator_for(name: str, seed):
    if name == "fanova":
        return FanovaImportanceEvaluator(seed=seed)
    if name == "mean-decrease-impurity":
        return MeanDecreaseImpurityImportanceEvaluator(seed=seed)
    return PedAnovaImportanceEvaluator()


def finite(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def importances(study, name: str, seed, notes: list) -> dict:
    try:
        values = get_param_importances(study, evaluator=evaluator_for(name, seed), normalize=True)
    except Exception as exc:  # the library raises several kinds on too few trials
        notes.append(f"importance ({name}) could not be computed: {exc}")
        return {}
    return {param: float(value) for param, value in values.items()}


def save(figure_axes, folder: Path, stem: str) -> str:
    axes = figure_axes
    figure = axes.figure if hasattr(axes, "figure") else axes.flat[0].figure
    figure.savefig(folder / f"{stem}.png", dpi=150, bbox_inches="tight")
    figure.savefig(folder / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)
    return f"{stem}.png"


def draw(stem: str, folder: Path, notes: list, plot) -> str | None:
    try:
        return save(plot(), folder, stem)
    except Exception as exc:
        notes.append(f"{stem} figure could not be drawn: {exc}")
        plt.close("all")
        return None


def report_study(study, plan: dict, out: Path) -> Path:
    notes: list[str] = []
    trials = study.get_trials(deepcopy=False)
    complete = [trial for trial in trials if trial.state == TrialState.COMPLETE]
    pruned = sum(1 for trial in trials if trial.state == TrialState.PRUNED)
    failed = sum(1 for trial in trials if trial.state == TrialState.FAIL)
    match = STUDY_PATTERN.match(study.study_name)
    arm, fold = (match["arm"], int(match["fold"])) if match else (study.study_name, None)
    if arm not in plan["arms"]:
        notes.append(f"arm {arm} is not declared in the plan")
    importance = plan["importance"]
    evaluator, seed, check = importance["evaluator"], importance.get("seed"), importance.get("check")
    seed = seed if evaluator != "ped-anova" else None

    best_value, best_params = None, {}
    if complete:
        best = study.best_trial
        best_value, best_params = finite(best.value), dict(best.params)
    folder = out / study.study_name
    folder.mkdir(parents=True, exist_ok=True)

    values, check_values = {}, None
    if len(complete) >= 2:
        values = importances(study, evaluator, seed, notes)
        if check:
            check_values = importances(study, check, importance.get("seed"), notes)
    else:
        notes.append("fewer than two complete trials: no importance, contour or history figure")

    seen = sorted({param for trial in complete for param in trial.params})
    ranked = sorted(values, key=lambda param: -values[param]) if values else seen
    contour_params = ranked[:CONTOUR_PARAMS]
    figures = {"contour": None, "importance": None, "history": None}
    if len(complete) >= 2:
        if len(contour_params) >= 2:
            figures["contour"] = draw("contour", folder, notes, lambda: optuna.visualization.matplotlib
                                      .plot_contour(study, params=contour_params))
        else:
            notes.append("fewer than two parameters varied: no contour figure")
        if values:
            figures["importance"] = draw("importance", folder, notes, lambda: optuna.visualization
                                         .matplotlib.plot_param_importances(
                                             study, evaluator=evaluator_for(evaluator, seed)))
        figures["history"] = draw("history", folder, notes, lambda: optuna.visualization.matplotlib
                                  .plot_optimization_history(study))
    record = {
        "schema": 1, "study": study.study_name, "arm": arm, "fold": fold,
        "objective": dict(plan["objective"]),
        "sampler": {"name": plan["sampler"]["name"], "seed": plan["sampler"]["seed"]},
        "pruner": plan["pruner"]["name"], "nTrials": len(trials), "complete": len(complete),
        "pruned": pruned, "failed": failed, "bestValue": best_value, "bestParams": best_params,
        "space": plan["space"],
        "importance": {"evaluator": evaluator, "seed": seed, "values": values},
        "importanceCheck": ({"evaluator": check, "values": check_values}
                            if check and check_values is not None else None),
        "contourParams": contour_params if figures["contour"] else [],
        "figures": figures, "optunaVersion": optuna.__version__,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    if notes:
        record["notes"] = notes
    path = folder / "summary.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="optuna_report.py")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written, notes = [], []
    for name in sorted(optuna.get_all_study_names(storage=args.storage)):
        if not SAFE_NAME.match(name) or ".." in name:
            notes.append(f"study {name!r} skipped: not a safe folder name")
            continue
        study = optuna.load_study(study_name=name, storage=args.storage)
        written.append(str(report_study(study, plan, out)))
    if not written:
        notes.append("the storage holds no study")
    print(json.dumps({"summaries": written, "notes": notes}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
