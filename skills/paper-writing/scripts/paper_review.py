"""The final judge's rounds: `.papersmith/paper_review.json`.

The `paper-reviewer` agent reviews the assembled manuscript and returns one
round to `/paper-writing`; it never writes a file. This module is the one
writer of that round: it validates it, numbers and dates it, checks that it
judges every revision the previous round asked for, and appends it, so the
dashboard's final-judge panel (`GET /api/paper/review`, read-only) shows how
the manuscript moved from round to round.

The file is `{"rounds": [...]}`. Each round:

- `round` (assigned here: previous + 1) and `date` (assigned here, ISO day);
- `overall` 1-6, `confidence` 1-5, `recommendation` (non-empty text);
- `ratings`: exactly `Quality`, `Clarity`, `Significance`, `Originality`, 1-4;
- `items`: one verdict per revision of the previous round, `{"rank",
  "verdict", "evidence"}`, `verdict` one of `resolved`, `partly`,
  `not resolved`; `item` is filled here from that revision's text. A first
  round carries none;
- `revisions`: what this round asks for, `{"rank", "text", "status",
  "note"}`, `status` defaulting to `pending`;
- `excluded` (optional list of text) and `report` (the full review form).

`rubric` names the form the round was judged on. `RUBRICS` is the registry:
per rubric its validator, the shape it stores and the paper lines
(`paper_kind` in `.papersmith/config.json`, `experimental` when unset) it
serves. A round whose rubric does not serve the workspace's line is refused
(`RUBRIC_KIND_MISMATCH`, naming the line's rubric), and a line no rubric
serves too (`RUBRIC_LINE_UNKNOWN`); a round without `rubric` is judged on its
line's rubric. `ml-conference` serves `experimental`: the main-track form of a
machine-learning conference above, and the stored round carries no `rubric`
key, exactly as before. For a review paper (`paper_kind: review`) it is
`systematic-review`: the round carries no `overall`, `confidence` or
`ratings`, and instead

- `amstar2`: one `{"item", "answer", "justification"}` per AMSTAR 2 item 1-16
  (Shea et al., 2017, BMJ 358:j4008), `answer` one of `yes`, `partial yes`
  (items 2, 4, 7, 8, 9 only), `no`, `not applicable` (items 11, 12, 15 only:
  no meta-analysis); `critical` is filled here for the seven critical domains;
- `overall_confidence` is derived here by the AMSTAR 2 rule from the `no`
  answers (`critical_flaws` and `non_critical_weaknesses`, also stored): no or
  one non-critical weakness is `high`, more than one `moderate`, one critical
  flaw `low`, more than one `critically low`. A round that asserts it must
  match the rule;
- `prisma_gaps`: the PRISMA 2020 reporting gaps (Page et al., 2021, BMJ
  372:n71), `{"item": 1-27, "gap"}`.

The empirical lines (observational-measurement, experiment-intervention,
qualitative-participatory, hardware, lab-simulation, data-resource) are judged
on `empirical-study`, which carries no `overall`, `confidence` or `ratings`:

- `protocol_adherence`: `{"primary_outcome", "analysis_plan", "deviations",
  "justification"}`, the first two one of `followed`, `deviated`, `no
  protocol` (against the locked study protocol), `deviations` a list of
  `{"deviation", "declared": true|false}` that may not be empty when either
  is `deviated`; `undeclared_deviations` (the count) is filled here;
- `design_validity`: `{"rating", "justification"}`, `rating` one of
  `adequate`, `limited`, `inadequate`;
- `risk_of_bias`: one `{"domain", "rating", "justification"}` per domain
  `selection`, `measurement`, `confounding`, `missing data`, `reporting`,
  `rating` one of `low`, `some concerns`, `high`;
- `overall_risk_of_bias`, derived here: any `high` domain is `high`, else any
  `some concerns` is `some concerns`, else `low`. A round that asserts it must
  match the rule;
- `checklist` (the reporting checklist the gaps refer to, e.g. `STROBE`;
  required when there are gaps) and `checklist_gaps`, `{"item", "gap"}`, the
  item by its number in that checklist (`12` or `12b`).

`recommendation`, `items`, `revisions`, `excluded` and `report` apply to every
rubric.

A refused round leaves the file byte for byte as it was, and a file that is
already malformed is reported, never overwritten.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The same cap the dashboard reads under (`server.PAPER_REVIEW_MAX_BYTES`):
#: a file the panel would refuse to read is never written.
MAX_BYTES = 2 * 1024 * 1024
RATINGS = ("Quality", "Clarity", "Significance", "Originality")
ITEM_VERDICTS = ("resolved", "partly", "not resolved")
REVISION_STATUSES = ("pending", "done", "applied", "not done", "skipped")
AMSTAR2_ITEMS = tuple(range(1, 17))
#: AMSTAR 2's seven critical domains (Shea et al., 2017, Box 2).
AMSTAR2_CRITICAL = (2, 4, 7, 9, 11, 13, 15)
AMSTAR2_ANSWERS = ("yes", "partial yes", "no", "not applicable")
#: The items whose AMSTAR 2 scale offers "partial yes", and those that offer
#: "no meta-analysis conducted" (stored as "not applicable").
AMSTAR2_PARTIAL = (2, 4, 7, 8, 9)
AMSTAR2_NOT_APPLICABLE = (11, 12, 15)
AMSTAR2_CONFIDENCE = ("high", "moderate", "low", "critically low")
#: PRISMA 2020 main checklist items run 1-27.
PRISMA_ITEMS = 27
#: The empirical-study rubric's scales.
ADHERENCE = ("followed", "deviated", "no protocol")
DESIGN_VALIDITY = ("adequate", "limited", "inadequate")
BIAS_DOMAINS = ("selection", "measurement", "confounding", "missing data", "reporting")
BIAS_LEVELS = ("low", "some concerns", "high")
#: A reporting-checklist item number: `12`, `12b`, `6a`.
CHECKLIST_ITEM = re.compile(r"[1-9][0-9]*[a-z]?")
CONFIG = Path(".papersmith") / "config.json"


def review_path(paper_dir: Path) -> Path:
    """The workspace's review file: `<paper>/../.papersmith/paper_review.json`."""
    return paper_dir.parent / ".papersmith" / "paper_review.json"


def _int_in(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _optional_text(value) -> str:
    """An optional free-text field: absent or JSON null is empty text."""
    return "" if value is None else str(value)


def load_rounds(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        if path.stat().st_size > MAX_BYTES:
            raise Refused("REVIEW_FILE_INVALID", f"{path} exceeds {MAX_BYTES} bytes")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("REVIEW_FILE_INVALID", f"{path} cannot be read as JSON: {exc}")
    rounds = data.get("rounds") if isinstance(data, dict) else None
    if not isinstance(rounds, list):
        raise Refused("REVIEW_FILE_INVALID", f'{path} holds no "rounds" list')
    if not all(isinstance(r, dict) for r in rounds):
        raise Refused("REVIEW_FILE_INVALID", f"{path} holds a round that is not a JSON object")
    return rounds


def read_input(raw: str) -> dict:
    try:
        text = sys.stdin.read() if raw == "-" else Path(raw).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused("REVIEW_INPUT_UNREADABLE", f"{raw}: {exc}")
    if not isinstance(data, dict):
        raise Refused("REVIEW_INPUT_UNREADABLE", f"{raw}: the round must be a JSON object")
    return data


def workspace_line(paper_dir: Path) -> str:
    """The workspace's line (`paper_kind`), `experimental` when unset or unreadable.

    The same reading as `skills/_core/paper_types/decision.py` `current_line`,
    repeated here so this script keeps running on its own.
    """
    try:
        config = json.loads((paper_dir.parent / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "experimental"
    kind = config.get("paper_kind") if isinstance(config, dict) else None
    return kind if isinstance(kind, str) and kind else "experimental"


def amstar2_confidence(answers: dict[int, str]) -> tuple[str, list[int], list[int]]:
    """The AMSTAR 2 overall confidence, its critical flaws and non-critical weaknesses.

    A flaw or weakness is a `no` (a critical or a non-critical item); `partial
    yes` and `not applicable` count as neither.
    """
    flaws = sorted(i for i, a in answers.items() if a == "no" and i in AMSTAR2_CRITICAL)
    weaknesses = sorted(i for i, a in answers.items() if a == "no" and i not in AMSTAR2_CRITICAL)
    if len(flaws) > 1:
        level = "critically low"
    elif flaws:
        level = "low"
    elif len(weaknesses) > 1:
        level = "moderate"
    else:
        level = "high"
    return level, flaws, weaknesses


def _validate_ml_conference(data: dict) -> list[str]:
    errors = []
    if not _int_in(data.get("overall"), 1, 6):
        errors.append("overall must be an integer 1-6")
    if not _int_in(data.get("confidence"), 1, 5):
        errors.append("confidence must be an integer 1-5")
    if not _text(data.get("recommendation")):
        errors.append("recommendation must be non-empty text")
    ratings = data.get("ratings")
    if not isinstance(ratings, dict) or sorted(ratings) != sorted(RATINGS):
        errors.append(f"ratings must hold exactly {', '.join(RATINGS)}")
    else:
        errors += [f"ratings.{k} must be an integer 1-4" for k in RATINGS if not _int_in(ratings[k], 1, 4)]
    return errors


def _validate_systematic_review(data: dict) -> list[str]:
    errors = []
    if not _text(data.get("recommendation")):
        errors.append("recommendation must be non-empty text")
    answers = data.get("amstar2")
    numbers = [a.get("item") for a in answers if isinstance(a, dict)] if isinstance(answers, list) else []
    if (not isinstance(answers, list) or len(numbers) != len(answers)
            or not all(_int_in(n, 1, 16) for n in numbers) or sorted(numbers) != list(AMSTAR2_ITEMS)):
        errors.append("amstar2 must answer each item 1-16 once")
    else:
        for a in sorted(answers, key=lambda a: a["item"]):
            item, answer = a["item"], a.get("answer")
            if answer not in AMSTAR2_ANSWERS:
                errors.append(f"amstar2 item {item} answer must be one of {', '.join(AMSTAR2_ANSWERS)}")
            elif answer == "partial yes" and item not in AMSTAR2_PARTIAL:
                errors.append(f'amstar2 item {item} cannot be "partial yes" (only items '
                              f'{", ".join(map(str, AMSTAR2_PARTIAL))})')
            elif answer == "not applicable" and item not in AMSTAR2_NOT_APPLICABLE:
                errors.append(f'amstar2 item {item} cannot be "not applicable" (only items '
                              f'{", ".join(map(str, AMSTAR2_NOT_APPLICABLE))}, without a meta-analysis)')
            if not _text(a.get("justification")):
                errors.append(f"amstar2 item {item} needs a non-empty justification")
        asserted = data.get("overall_confidence")
        if not errors and asserted is not None:
            level = amstar2_confidence({a["item"]: a["answer"] for a in answers})[0]
            if asserted != level:
                errors.append(f'overall_confidence "{asserted}" does not match the AMSTAR 2 rule: {level}')
    gaps = data.get("prisma_gaps", [])
    if not isinstance(gaps, list):
        errors.append("prisma_gaps must be a list")
    else:
        for n, gap in enumerate(gaps, 1):
            if not isinstance(gap, dict) or not _int_in(gap.get("item"), 1, PRISMA_ITEMS) or not _text(gap.get("gap")):
                errors.append(f"prisma_gaps[{n}] needs an item 1-27 and non-empty gap text")
    return errors


def overall_risk_of_bias(ratings) -> str:
    """Any `high` domain is `high`; else any `some concerns` is `some concerns`; else `low`."""
    ratings = list(ratings)
    if "high" in ratings:
        return "high"
    return "some concerns" if "some concerns" in ratings else "low"


def _checklist_item(value) -> bool:
    if isinstance(value, str):
        return CHECKLIST_ITEM.fullmatch(value) is not None
    return _int_in(value, 1, 10**6)


def _validate_empirical_study(data: dict) -> list[str]:
    errors = []
    if not _text(data.get("recommendation")):
        errors.append("recommendation must be non-empty text")
    adherence = data.get("protocol_adherence")
    if not isinstance(adherence, dict):
        errors.append("protocol_adherence must be an object")
    else:
        for field in ("primary_outcome", "analysis_plan"):
            if adherence.get(field) not in ADHERENCE:
                errors.append(f"protocol_adherence.{field} must be one of {', '.join(ADHERENCE)}")
        deviations = adherence.get("deviations", [])
        if not isinstance(deviations, list):
            errors.append("protocol_adherence.deviations must be a list")
        else:
            for n, dev in enumerate(deviations, 1):
                if (not isinstance(dev, dict) or not _text(dev.get("deviation"))
                        or not isinstance(dev.get("declared"), bool)):
                    errors.append(f"protocol_adherence.deviations[{n}] needs non-empty deviation text "
                                  "and declared true or false")
            for field in ("primary_outcome", "analysis_plan"):
                if adherence.get(field) == "deviated" and not deviations:
                    errors.append(f"protocol_adherence lists no deviation although {field} is deviated")
        if not _text(adherence.get("justification")):
            errors.append("protocol_adherence needs a non-empty justification")
    design = data.get("design_validity")
    if not isinstance(design, dict):
        errors.append("design_validity must be an object")
    else:
        if design.get("rating") not in DESIGN_VALIDITY:
            errors.append(f"design_validity.rating must be one of {', '.join(DESIGN_VALIDITY)}")
        if not _text(design.get("justification")):
            errors.append("design_validity needs a non-empty justification")
    domains = data.get("risk_of_bias")
    names = [d.get("domain") for d in domains if isinstance(d, dict)] if isinstance(domains, list) else []
    if (not isinstance(domains, list) or len(names) != len(domains)
            or sorted(map(str, names)) != sorted(BIAS_DOMAINS)):
        errors.append(f"risk_of_bias must rate each domain once: {', '.join(BIAS_DOMAINS)}")
    else:
        bias_errors = []
        for d in sorted(domains, key=lambda d: BIAS_DOMAINS.index(d["domain"])):
            if d.get("rating") not in BIAS_LEVELS:
                bias_errors.append(f"risk_of_bias {d['domain']} rating must be one of {', '.join(BIAS_LEVELS)}")
            if not _text(d.get("justification")):
                bias_errors.append(f"risk_of_bias {d['domain']} needs a non-empty justification")
        asserted = data.get("overall_risk_of_bias")
        if not bias_errors and asserted is not None:
            level = overall_risk_of_bias(d["rating"] for d in domains)
            if asserted != level:
                bias_errors.append(f'overall_risk_of_bias "{asserted}" does not match the rule: {level}')
        errors += bias_errors
    gaps = data.get("checklist_gaps", [])
    if not isinstance(gaps, list):
        errors.append("checklist_gaps must be a list")
    else:
        for n, gap in enumerate(gaps, 1):
            if not isinstance(gap, dict) or not _checklist_item(gap.get("item")) or not _text(gap.get("gap")):
                errors.append(f"checklist_gaps[{n}] needs an item number (e.g. 12 or 12b) and non-empty gap text")
        checklist = data.get("checklist")
        if (gaps or checklist is not None) and not _text(checklist):
            errors.append("checklist must name the reporting checklist the gaps refer to")
    return errors


def _shape_ml_conference(data: dict) -> dict:
    return {
        "overall": data["overall"],
        "confidence": data["confidence"],
        "recommendation": data["recommendation"].strip(),
        "ratings": {k: data["ratings"][k] for k in RATINGS},
    }


def _shape_systematic_review(data: dict) -> dict:
    answers = sorted(data["amstar2"], key=lambda a: a["item"])
    level, flaws, weaknesses = amstar2_confidence({a["item"]: a["answer"] for a in answers})
    return {
        "recommendation": data["recommendation"].strip(),
        "amstar2": [{"item": a["item"], "critical": a["item"] in AMSTAR2_CRITICAL, "answer": a["answer"],
                     "justification": a["justification"].strip()} for a in answers],
        "critical_flaws": flaws,
        "non_critical_weaknesses": weaknesses,
        "overall_confidence": level,
        "prisma_gaps": [{"item": g["item"], "gap": g["gap"].strip()} for g in data.get("prisma_gaps", [])],
    }


def _shape_empirical_study(data: dict) -> dict:
    adherence = data["protocol_adherence"]
    deviations = [{"deviation": d["deviation"].strip(), "declared": d["declared"]}
                  for d in adherence.get("deviations", [])]
    domains = sorted(data["risk_of_bias"], key=lambda d: BIAS_DOMAINS.index(d["domain"]))
    return {
        "recommendation": data["recommendation"].strip(),
        "protocol_adherence": {
            "primary_outcome": adherence["primary_outcome"],
            "analysis_plan": adherence["analysis_plan"],
            "deviations": deviations,
            "undeclared_deviations": sum(1 for d in deviations if not d["declared"]),
            "justification": adherence["justification"].strip(),
        },
        "design_validity": {"rating": data["design_validity"]["rating"],
                            "justification": data["design_validity"]["justification"].strip()},
        "risk_of_bias": [{"domain": d["domain"], "rating": d["rating"], "justification": d["justification"].strip()}
                         for d in domains],
        "overall_risk_of_bias": overall_risk_of_bias(d["rating"] for d in domains),
        "checklist": (data.get("checklist") or "").strip(),
        "checklist_gaps": [{"item": g["item"], "gap": g["gap"].strip()} for g in data.get("checklist_gaps", [])],
    }


@dataclass(frozen=True)
class Rubric:
    """One final-judge form: what it validates, what it stores, which lines it serves."""

    validate: Callable[[dict], list[str]]
    shape: Callable[[dict], dict]
    lines: tuple[str, ...]
    #: Whether the stored round names its rubric (`ml-conference` rounds never did).
    stores_id: bool = True


#: The final judge's forms, by id. A line is served by exactly one rubric; a
#: new paper line joins a rubric by adding its id to `lines`.
RUBRICS: dict[str, Rubric] = {
    "ml-conference": Rubric(_validate_ml_conference, _shape_ml_conference, ("experimental",), stores_id=False),
    "systematic-review": Rubric(_validate_systematic_review, _shape_systematic_review, ("review",)),
    "empirical-study": Rubric(_validate_empirical_study, _shape_empirical_study,
                              ("observational-measurement", "experiment-intervention", "qualitative-participatory",
                               "hardware", "lab-simulation", "data-resource")),
}


def rubric_for_line(line: str) -> str | None:
    """The rubric that serves a paper line, or None when none does."""
    return next((rubric_id for rubric_id, rubric in RUBRICS.items() if line in rubric.lines), None)


def rubric_of(data: dict, line: str) -> str:
    """The rubric a round is judged on: the one it declares, else its line's.

    Raises `Refused` for an unknown rubric, a line no rubric serves, or a rubric
    that does not serve the line.
    """
    if "rubric" in data and data["rubric"] not in RUBRICS:
        raise Refused("REVIEW_ROUND_INVALID", f"rubric must be one of {', '.join(RUBRICS)}")
    expected = rubric_for_line(line)
    if expected is None:
        raise Refused("RUBRIC_LINE_UNKNOWN", f'no rubric serves the line "{line}" (paper_kind in '
                      f'.papersmith/config.json); known lines: '
                      f'{", ".join(l for r in RUBRICS.values() for l in r.lines)}')
    rubric = data.get("rubric", expected)
    if line not in RUBRICS[rubric].lines:
        raise Refused("RUBRIC_KIND_MISMATCH", f'rubric "{rubric}" does not serve the line "{line}" '
                      f'(paper_kind in .papersmith/config.json); the line\'s rubric is "{expected}"')
    return rubric


def _validate(data: dict, rubric: str) -> list[str]:
    errors = RUBRICS[rubric].validate(data)
    items = data.get("items", [])
    if not isinstance(items, list):
        errors.append("items must be a list")
    else:
        item_ranks = []
        for n, item in enumerate(items, 1):
            if not isinstance(item, dict) or not _int_in(item.get("rank"), 1, 10**6):
                errors.append(f"items[{n}] needs an integer rank")
                continue
            item_ranks.append(item["rank"])
            if item.get("verdict") not in ITEM_VERDICTS:
                errors.append(f"items[{n}].verdict must be one of {', '.join(ITEM_VERDICTS)}")
        if len(item_ranks) != len(set(item_ranks)):
            errors.append("items must give one verdict per rank")
    revisions = data.get("revisions", [])
    if not isinstance(revisions, list):
        errors.append("revisions must be a list")
    else:
        ranks = []
        for n, rev in enumerate(revisions, 1):
            if not isinstance(rev, dict) or not _int_in(rev.get("rank"), 1, 10**6) or not _text(rev.get("text")):
                errors.append(f"revisions[{n}] needs an integer rank and non-empty text")
                continue
            ranks.append(rev["rank"])
            if rev.get("status", "pending") not in REVISION_STATUSES:
                errors.append(f"revisions[{n}].status must be one of {', '.join(REVISION_STATUSES)}")
        if len(ranks) != len(set(ranks)):
            errors.append("revisions ranks must be distinct")
    excluded = data.get("excluded", [])
    if not isinstance(excluded, list) or not all(isinstance(e, str) for e in excluded):
        errors.append("excluded must be a list of text")
    if not _text(data.get("report")):
        errors.append("report must be non-empty text (the full review form)")
    return errors


def _judged_items(items: list[dict], previous: dict | None) -> list[dict]:
    raised = {r["rank"]: r.get("text", "") for r in (previous or {}).get("revisions", [])
              if isinstance(r, dict) and "rank" in r}
    unknown = sorted({i["rank"] for i in items} - set(raised))
    if unknown:
        raise Refused("REVIEW_ITEM_UNKNOWN",
                      f"verdicts on revisions the previous round did not raise: {unknown}")
    missing = sorted(set(raised) - {i["rank"] for i in items})
    if missing:
        raise Refused("REVIEW_ITEMS_MISSING",
                      f"the previous round's revisions {missing} carry no verdict")
    return [{"rank": i["rank"], "item": raised[i["rank"]], "verdict": i["verdict"],
             "evidence": _optional_text(i.get("evidence"))} for i in sorted(items, key=lambda i: i["rank"])]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def record(paper_dir: Path, data: dict, *, today: _dt.date | None = None) -> dict:
    """Validate one round, number and date it, and append it to the file."""
    path = review_path(paper_dir)
    rounds = load_rounds(path)
    rubric = rubric_of(data, workspace_line(paper_dir))
    errors = _validate(data, rubric)
    if errors:
        raise Refused("REVIEW_ROUND_INVALID", "; ".join(errors))
    previous = rounds[-1] if rounds else None
    number = (max((r.get("round") for r in rounds if _int_in(r.get("round"), 1, 10**6)), default=0)) + 1
    entry = {"round": number, "date": (today or _dt.date.today()).isoformat()}
    if RUBRICS[rubric].stores_id:
        entry["rubric"] = rubric
    entry.update(RUBRICS[rubric].shape(data))
    entry.update({
        "items": _judged_items(data.get("items", []), previous),
        "revisions": [{"rank": r["rank"], "text": r["text"].strip(), "status": r.get("status", "pending"),
                       "note": _optional_text(r.get("note"))} for r in sorted(data.get("revisions", []),
                                                                     key=lambda r: r["rank"])],
        "excluded": list(data.get("excluded", [])),
        "report": data["report"],
    })
    payload = (json.dumps({"rounds": rounds + [entry]}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise Refused("REVIEW_FILE_INVALID", f"recording this round would exceed {MAX_BYTES} bytes")
    _atomic_write(path, payload)
    return {"round": number, "path": str(path), "rounds": len(rounds) + 1,
            "pending_revisions": sum(1 for r in entry["revisions"] if r["status"] == "pending")}
