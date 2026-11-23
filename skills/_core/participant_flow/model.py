"""Participant flow templates, the ``study/flow.json`` model and its arithmetic check.

A template is an ordered chain of stages. A stage holds one count ``n``, or one
count per branch when it is *split* (the arms of a trial, the results of an
index test). A stage may carry reason groups, each a list of
``{"reason": <text>, "n": <count>}`` entered by the operator:

``leave``      people who left the flow before this stage: ``n`` equals the
               basis stage's count minus the group's total;
``note``       people reported inside this stage who stay in it (did not
               receive the allocated intervention, discontinued it): the
               group's total is at most ``n``;
``partition``  fixed categories (reference standard results) whose counts sum
               to ``n`` exactly; stored as ``{category: count}``.

The basis of a stage is the stage before it, or another stage the template
offers in ``basis_options`` (an intention-to-treat analysis counts from the
allocated arm). A split stage that follows a single stage shares that stage's
count among its branches. Every count is the operator's; nothing here derives
or fills one. Stdlib only.
"""

from __future__ import annotations

import copy
import hashlib
import json

SCHEMA = 1
FLOW_PATH = "study/flow.json"
FIGURE_PATH = "paper/Figures/participant-flow.svg"
SIGNOFFS_PATH = "study/flow-signoffs.json"
#: Top-level keys a tool may stamp on flow.json; they never change the signed state.
TIMESTAMP_KEYS = ("generated_at", "updated_at", "entered_at")
MAX_BRANCHES = 6


def has_control(text: str) -> bool:
    """True when ``text`` holds a character an SVG (XML 1.0) text node cannot carry."""
    return any(ord(ch) < 32 or 127 <= ord(ch) < 160 for ch in text)


def _leave(gid: str, label: str, reasons: tuple[str, ...] = ()) -> dict:
    return {"id": gid, "label": label, "effect": "leave", "reasons": list(reasons)}


def _note(gid: str, label: str) -> dict:
    return {"id": gid, "label": label, "effect": "note", "reasons": []}


TEMPLATES: dict[str, dict] = {
    "consort-2025": {
        "name": "CONSORT 2025 parallel-group randomised trial",
        "guideline": "CONSORT 2025",
        "url": "https://www.equator-network.org/reporting-guidelines/consort/",
        "branches": {"source": "operator", "noun": "arm", "default": ["Intervention", "Control"]},
        "stages": [
            {"id": "assessed", "band": "Enrolment", "label": "Assessed for eligibility"},
            {"id": "randomised", "band": "Enrolment", "label": "Randomised",
             "groups": [_leave("excluded", "Excluded",
                               ("Not meeting inclusion criteria", "Declined to participate", "Other reasons"))]},
            {"id": "allocated", "band": "Allocation", "label": "Allocated to {branch}", "split": True,
             "groups": [_note("not_received", "Did not receive the allocated intervention")],
             "remainder": "Received the allocated intervention"},
            {"id": "follow_up", "band": "Follow-up", "label": "{branch}: followed up", "split": True,
             "groups": [_leave("lost", "Lost to follow-up"), _note("discontinued", "Discontinued the intervention")]},
            {"id": "analysed", "band": "Analysis", "label": "{branch}: analysed", "split": True,
             "basis_options": ["follow_up", "allocated"],
             "groups": [_leave("excluded", "Excluded from analysis")]},
        ],
    },
    "strobe": {
        "name": "STROBE observational study (cohort or cross-sectional)",
        "guideline": "STROBE",
        "url": "https://www.equator-network.org/reporting-guidelines/strobe/",
        "stages": [
            {"id": "potentially_eligible", "band": "Eligibility", "label": "Potentially eligible"},
            {"id": "examined", "band": "Eligibility", "label": "Examined for eligibility",
             "groups": [_leave("excluded", "Not examined")]},
            {"id": "eligible", "band": "Eligibility", "label": "Confirmed eligible",
             "groups": [_leave("excluded", "Not eligible")]},
            {"id": "included", "band": "Participation", "label": "Included in the study",
             "groups": [_leave("excluded", "Not included")]},
            {"id": "followed", "band": "Follow-up", "label": "Completed follow-up", "optional": True,
             "groups": [_leave("excluded", "Did not complete follow-up")]},
            {"id": "analysed", "band": "Analysis", "label": "Analysed",
             "groups": [_leave("excluded", "Excluded from analysis")]},
        ],
    },
    "stard-2015": {
        "name": "STARD 2015 diagnostic accuracy study",
        "guideline": "STARD 2015",
        "url": "https://www.equator-network.org/reporting-guidelines/stard/",
        "branches": {"source": "fixed", "items": [("positive", "Index test positive"),
                                                  ("negative", "Index test negative"),
                                                  ("inconclusive", "Index test inconclusive")]},
        "stages": [
            {"id": "potentially_eligible", "band": "Eligibility", "label": "Potentially eligible participants"},
            {"id": "eligible", "band": "Eligibility", "label": "Eligible participants",
             "groups": [_leave("excluded", "Excluded")]},
            {"id": "index_test", "band": "Index test", "label": "Received the index test",
             "groups": [_leave("excluded", "Did not receive the index test")]},
            {"id": "index_result", "band": "Index test", "label": "{branch}", "split": True},
            {"id": "reference", "band": "Reference standard", "label": "{branch}: received the reference standard",
             "split": True,
             "groups": [_leave("no_reference", "No reference standard"),
                        {"id": "outcome", "label": "Reference standard result", "effect": "partition",
                         "categories": [("target_present", "Target condition present"),
                                        ("target_absent", "Target condition absent"),
                                        ("inconclusive", "Inconclusive")]}]},
        ],
    },
}


class FlowError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def template(template_id: str) -> dict:
    if template_id not in TEMPLATES:
        raise FlowError("TEMPLATE_UNKNOWN", f"unknown template {template_id!r}; known: {', '.join(TEMPLATES)}")
    return TEMPLATES[template_id]


def branch_labels(tpl: dict, flow: dict) -> dict[str, str]:
    """branch id -> display label (an operator's arm is its own label)."""
    spec = tpl.get("branches")
    if not spec:
        return {}
    if spec["source"] == "fixed":
        return dict(spec["items"])
    return {name: name for name in flow.get("branches", [])}


def _empty_entry(stage: dict) -> dict:
    entry: dict = {"n": None}
    for group in stage.get("groups", []):
        if group["effect"] == "partition":
            entry[group["id"]] = {category: None for category, _ in group["categories"]}
        else:
            entry[group["id"]] = [{"reason": reason, "n": None} for reason in group["reasons"]]
    return entry


def empty_flow(template_id: str, arms: list[str] | None = None) -> dict:
    """The flow.json the operator fills: every count ``null``."""
    tpl = template(template_id)
    spec = tpl.get("branches")
    if arms and not (spec and spec["source"] == "operator"):
        raise FlowError("ARMS_NOT_APPLICABLE", f"{template_id} has no operator-named arms")
    flow: dict = {"schema": SCHEMA, "template": template_id}
    if spec and spec["source"] == "operator":
        flow["branches"] = list(arms or spec["default"])
    branches = list(branch_labels(tpl, flow))
    stages = {}
    for stage in tpl["stages"]:
        if stage.get("split"):
            body: dict = {}
            if stage.get("basis_options"):
                body["basis"] = stage["basis_options"][0]
            body["branches"] = {name: _empty_entry(stage) for name in branches}
        else:
            body = _empty_entry(stage)
        stages[stage["id"]] = body
    flow["stages"] = stages
    return flow


def flow_sha256(flow: dict) -> str:
    """The hash of the counts: canonical JSON, timestamp keys aside."""
    body = {key: value for key, value in flow.items() if key not in TIMESTAMP_KEYS} \
        if isinstance(flow, dict) else flow
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- check


class _Check:
    def __init__(self) -> None:
        self.problems: list[dict] = []

    def add(self, code: str, where: str, message: str) -> None:
        self.problems.append({"code": code, "where": where, "message": message})

    def count(self, value, where: str) -> int | None:
        if value is None:
            self.add("COUNT_MISSING", where, "the operator has not entered this count yet")
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self.add("COUNT_INVALID", where, f"a count is a whole number, not {json.dumps(value)}")
            return None
        if value < 0:
            self.add("COUNT_INVALID", where, f"a count cannot be negative ({value})")
            return None
        return value

    def reasons(self, value, where: str) -> int | None:
        """The total of a reason list, ``None`` when any count is unknown."""
        if not isinstance(value, list):
            self.add("SCHEMA_INVALID", where, "a reason group is a list of {\"reason\", \"n\"} objects")
            return None
        total, seen = 0, set()
        for index, item in enumerate(value):
            at = f"{where}[{index}]"
            if not isinstance(item, dict) or set(item) != {"reason", "n"}:
                self.add("SCHEMA_INVALID", at, "each reason is an object with exactly \"reason\" and \"n\"")
                total = None
                continue
            text = item["reason"].strip() if isinstance(item["reason"], str) else ""
            if not text:
                self.add("REASON_MISSING", f"{at}.reason", "each exclusion names its reason")
            elif has_control(text):
                self.add("TEXT_INVALID", f"{at}.reason", "a reason holds no control characters or line breaks")
            elif text.casefold() in seen:
                self.add("REASON_DUPLICATE", f"{at}.reason", f"the reason {text!r} is listed twice in this group")
            seen.add(text.casefold())
            n = self.count(item["n"], f"{at}.n")
            total = None if n is None or total is None else total + n
        return total

    def entry(self, stage: dict, entry, where: str, extra: tuple[str, ...] = ()) -> tuple[int | None, int | None]:
        """Check one count with its groups; answer (n, leave total)."""
        groups = stage.get("groups", [])
        if not isinstance(entry, dict):
            self.add("SCHEMA_INVALID", where, "a stage entry is an object with \"n\" and its reason groups")
            return None, None
        expected = {"n", *(group["id"] for group in groups), *extra}
        for key in sorted(set(entry) - expected):
            self.add("SCHEMA_INVALID", f"{where}.{key}", f"unknown key; expected {', '.join(sorted(expected))}")
        for key in sorted(expected - set(entry) - set(extra)):
            self.add("SCHEMA_INVALID", f"{where}.{key}", "missing")
        n = self.count(entry.get("n"), f"{where}.n") if "n" in entry else None
        leave: int | None = 0
        for group in groups:
            at = f"{where}.{group['id']}"
            if group["id"] not in entry:
                leave = None if group["effect"] == "leave" else leave
                continue
            value = entry[group["id"]]
            if group["effect"] == "partition":
                categories = [category for category, _ in group["categories"]]
                if not isinstance(value, dict) or sorted(value) != sorted(categories):
                    self.add("SCHEMA_INVALID", at, f"the categories are exactly {', '.join(categories)}")
                    continue
                counts = [self.count(value[c], f"{at}.{c}") for c in categories]
                if n is not None and None not in counts and sum(counts) != n:
                    self.add("PARTITION_MISMATCH", at, f"{group['label']}: the categories sum to {sum(counts)}, "
                                                       f"the stage counts {n}")
                continue
            total = self.reasons(value, at)
            if group["effect"] == "note":
                if n is not None and total is not None and total > n:
                    self.add("NOTE_EXCEEDS_COUNT", at, f"{group['label']}: {total} people reported, "
                                                       f"the stage counts only {n}")
            else:
                leave = None if total is None or leave is None else leave + total
        return n, leave

    def against(self, n: int | None, leave: int | None, basis_n: int | None, basis_id: str, where: str) -> None:
        if n is None or leave is None or basis_n is None:
            return
        if n > basis_n:
            self.add("EXCEEDS_PREVIOUS_STAGE", where, f"{n} is more than the {basis_n} of {basis_id}")
        elif n != basis_n - leave:
            self.add("COUNT_MISMATCH", where, f"expected {basis_n - leave} ({basis_id} {basis_n} minus "
                                              f"{leave} excluded), found {n}")


def check(flow) -> list[dict]:
    """Every arithmetic and structure problem of a flow, ``[]`` when valid."""
    c = _Check()
    if not isinstance(flow, dict):
        c.add("SCHEMA_INVALID", "", "flow.json holds one JSON object")
        return c.problems
    if flow.get("template") not in TEMPLATES:
        c.add("TEMPLATE_UNKNOWN", "template", f"unknown template {flow.get('template')!r}; "
                                              f"known: {', '.join(TEMPLATES)}")
        return c.problems
    tpl = TEMPLATES[flow["template"]]
    spec = tpl.get("branches")
    allowed = {"schema", "template", "stages", *TIMESTAMP_KEYS}
    if spec and spec["source"] == "operator":
        allowed.add("branches")
    if flow.get("schema") != SCHEMA:
        c.add("SCHEMA_INVALID", "schema", f"schema is {SCHEMA}")
    for key in sorted(set(flow) - allowed):
        c.add("SCHEMA_INVALID", key, "unknown key")
    if spec and spec["source"] == "operator":
        names = flow.get("branches")
        if (not isinstance(names, list) or not 2 <= len(names) <= MAX_BRANCHES
                or not all(isinstance(x, str) and x.strip() for x in names) or len(set(names)) != len(names)):
            c.add("BRANCHES_INVALID", "branches", f"name 2 to {MAX_BRANCHES} distinct {spec['noun']}s")
            return c.problems
        if any(has_control(name) for name in names):
            c.add("TEXT_INVALID", "branches", "an arm name holds no control characters or line breaks")
            return c.problems
    branches = list(branch_labels(tpl, flow))
    stages = flow.get("stages")
    if not isinstance(stages, dict):
        c.add("SCHEMA_INVALID", "stages", "stages is an object keyed by stage id")
        return c.problems
    known = [stage["id"] for stage in tpl["stages"]]
    for key in sorted(set(stages) - set(known)):
        c.add("SCHEMA_INVALID", f"stages.{key}", f"unknown stage; the stages are {', '.join(known)}")

    totals: dict[str, object] = {}  # stage id -> n, {branch: n} or None when unknown
    previous = None
    for stage in tpl["stages"]:
        sid, where = stage["id"], f"stages.{stage['id']}"
        if sid not in stages:
            if not stage.get("optional"):
                c.add("SCHEMA_INVALID", where, "missing stage")
                totals[sid], previous = None, sid
            continue
        body = stages[sid]
        basis = previous
        options = stage.get("basis_options")
        if options and isinstance(body, dict) and "basis" in body:
            if body["basis"] not in options or body["basis"] not in totals:
                c.add("BASIS_INVALID", f"{where}.basis", f"the basis is one of {', '.join(options)}")
                basis = None
            else:
                basis = body["basis"]
        extra = ("basis",) if options else ()
        if stage.get("split"):
            if not isinstance(body, dict) or not isinstance(body.get("branches"), dict):
                c.add("SCHEMA_INVALID", where, "a split stage holds \"branches\": {<branch>: <entry>}")
                totals[sid], previous = None, sid
                continue
            for key in sorted(set(body) - {"branches", *extra}):
                c.add("SCHEMA_INVALID", f"{where}.{key}", "unknown key")
            if sorted(body["branches"]) != sorted(branches):
                c.add("BRANCH_MISMATCH", f"{where}.branches", f"the branches are {', '.join(branches)}")
                totals[sid], previous = None, sid
                continue
            results = {b: c.entry(stage, body["branches"][b], f"{where}.branches.{b}") for b in branches}
            basis_total = totals.get(basis) if basis else None
            if isinstance(basis_total, dict):
                for b, (n, leave) in results.items():
                    c.against(n, leave, basis_total.get(b), f"{basis} ({b})", f"{where}.branches.{b}.n")
            elif isinstance(basis_total, int) and all(n is not None and leave is not None
                                                      for n, leave in results.values()):
                shared = sum(n + leave for n, leave in results.values())
                if shared != basis_total:
                    c.add("BRANCH_SUM_MISMATCH", f"{where}.branches",
                          f"the branches account for {shared} people, {basis} counts {basis_total}")
            totals[sid] = {b: n for b, (n, _) in results.items()}
        else:
            n, leave = c.entry(stage, body, where, extra)
            if basis is not None:
                basis_total = totals.get(basis)
                c.against(n, leave, basis_total if isinstance(basis_total, int) else None, basis, f"{where}.n")
            totals[sid] = n
        previous = sid
    return c.problems


def stage_chain(flow: dict) -> list[dict]:
    """The template stages a (valid) flow holds, in order, each with its body."""
    tpl = TEMPLATES[flow["template"]]
    return [dict(copy.deepcopy(stage), body=flow["stages"][stage["id"]])
            for stage in tpl["stages"] if stage["id"] in flow["stages"]]
