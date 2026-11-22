"""The command center's board for a review workspace (``paper_kind: "review"``).

A review workspace (``smith init --kind review``) builds a PRISMA 2020
systematic review: no proposal, no experiments, no remote runs. Its board
shows the ten steps of the review flow
(``src/papersmith/templates/paper-flow-review.md.tpl``) instead of the
experimental line's eleven phases, each with its status read from the
``review/`` records and the paper tree, its actions (the ``/systematic-review``
slash command and the ``review_cli.py`` verbs the skill documents), its
evidence and its lock. The experimental line's definitions in
``phase_actions`` stay untouched: ``phase_actions.attach(..., kind="review")``
reads this module's instead.

The review gates are the operator's: G-PROTOCOL (``review/protocol.lock.json``
current while its sha256 matches the protocol), the screening sign-off
(G-SCREENING) and the synthesis acceptance (G-SYNTHESIS), both recorded in
``review/signoffs.json`` by ``review_cli.py signoff`` and current while the
state they signed is unchanged. An agent never signs on the operator's behalf.

The records are read through the workspace's own
``skills/systematic-review/scripts/review_cli.py`` (loaded by path: it lives
in a hyphenated directory and is absent from experimental workspaces), never
re-implemented here, and never through its slow ``checklist`` verb. Every
label is English; the dashboard's Spanish comes from
``static/i18n/server-es.json`` (see ``localize.py``).
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import re
import threading
from pathlib import Path
from typing import Any

from . import phase_actions
from . import state_extractor as _ex
from .phase_actions import _command, _prompt, _redirect

REVIEW_CLI = "python skills/systematic-review/scripts/review_cli.py"
#: The dashboard's own copy, used when the workspace carries none.
DASHBOARD_REVIEW_CLI = Path(__file__).resolve().parents[2] / "systematic-review" / "scripts" / "review_cli.py"

#: The ten steps of the review flow, in order; the phase id ``Fase N`` is index N-1.
REVIEW_STAGES: tuple[str, ...] = (
    "harness", "scoping", "protocol", "identification", "screening", "appraisal_extraction",
    "synthesis", "writing", "paper", "reporting_audit",
)

#: Short label of each step, in ``REVIEW_STAGES`` order.
REVIEW_LABELS: dict[str, str] = {
    "harness": "Harness",
    "scoping": "Scoping",
    "protocol": "Protocol",
    "identification": "Identification",
    "screening": "Screening",
    "appraisal_extraction": "Appraisal and extraction",
    "synthesis": "Synthesis",
    "writing": "Scaffolding, declarations and writing",
    "paper": "Figures and paper",
    "reporting_audit": "Reporting check and audit",
}

_PROTOCOL_GATE, _SCREENING_GATE, _SYNTHESIS_GATE = "G-PROTOCOL", "G-SCREENING", "G-SYNTHESIS"

REVIEW_ACTIONS: dict[str, dict[str, Any]] = {
    "harness": copy.deepcopy(phase_actions.ACTIONS["harness"]),
    "scoping": {
        "skills": ["systematic-review"],
        "agent": "systematic-review",
        "actions": [
            _prompt("/systematic-review", "Scope the topic", [
                "Write the topic in at least two sentences: the field and the question the review answers.",
                "The agent searches OpenAlex for existing reviews on the topic and keeps them in review/scope.json.",
                "Read their scopes and years with the agent: the new review's gap is what they leave unanswered.",
            ], "E.g.: Graph neural networks predict molecular properties. Which architectures are evaluated, and how?",
                min_sentences=2, prefix="scope "),
            _command(f'{REVIEW_CLI} scope --query "<topic words>"', "Search existing reviews from the CLI",
                     "Lists the existing reviews (OpenAlex, type:review) in review/scope.json."),
        ],
    },
    "protocol": {
        "skills": ["systematic-review"],
        "agent": "systematic-review & operator",
        "actions": [
            _prompt("/systematic-review", "Write the protocol with the agent", [
                "The agent fills review/protocol.json with you: the objective, the research questions with their PICOC, the criteria, one query per source, the dates, the languages, the screening, the appraisal and the extraction fields.",
                "Nothing is searched before you approve the protocol (G-PROTOCOL).",
                "A change after the approval is an amendment, recorded with its reason.",
            ], "E.g.: draft the protocol for the question on molecular property prediction.",
                optional=True, prefix="protocol "),
            _command(f"{REVIEW_CLI} protocol check", "Check the protocol",
                     "Lists what review/protocol.json still lacks."),
            _command(f'{REVIEW_CLI} protocol approve --by "<operator name>"', "Approve the protocol (operator, G-PROTOCOL)",
                     "Only the operator approves; the approval pins the protocol's sha256."),
            _command(f'{REVIEW_CLI} protocol amend --by "<operator name>" --reason "<why>"', "Record an amendment",
                     "A change after the approval, with its reason; the methods report it."),
        ],
    },
    "identification": {
        "skills": ["systematic-review"],
        "agent": "systematic-review",
        "actions": [
            _prompt("/systematic-review", "Run the searches", [
                "The agent runs the protocol's query on OpenAlex, Crossref and Europe PMC and logs each search in review/searches.jsonl.",
                "The exports you download from Scopus, Web of Science, IEEE Xplore or ACM enter with import, with the query as you ran it.",
                "Then dedupe marks the duplicates by DOI, then by normalized title and year.",
            ], "E.g.: search every open source of the protocol and remove the duplicates.",
                optional=True, prefix="search "),
            _command(f"{REVIEW_CLI} search --source <openalex|crossref|europepmc>", "Search one source",
                     "Runs that source's query from the protocol and logs its date, query and counts."),
            _command(f'{REVIEW_CLI} import --file <export> --source <name> --query "<as run>"',
                     "Import a database export", "A RIS or BibTeX export from Scopus, Web of Science, IEEE Xplore or ACM."),
            _command(f"{REVIEW_CLI} dedupe", "Remove the duplicates",
                     "Marks the duplicates by DOI, then by normalized title and year."),
        ],
    },
    "screening": {
        "skills": ["systematic-review", "paper-ingestion"],
        "agent": "systematic-review (one reviewer) & operator (the other)",
        "actions": [
            _prompt("/systematic-review", "Screen with the agent as one reviewer", [
                "Two independent reviewers decide every record: on title and abstract first, then on the full text of the ones kept.",
                "The agent may be one reviewer; you are always the other, and you settle every conflict (screen --final).",
                "A full-text exclusion names one exclusion criterion of the protocol; /paper-ingestion retrieves the full texts.",
                "When every record is decided and no conflict is left, you sign the screening off yourself (G-SCREENING).",
            ], "E.g.: screen the title/abstract queue as the agent reviewer.", optional=True, prefix="screen "),
            _command(f"{REVIEW_CLI} queue --stage ta --reviewer <name>", "What a reviewer still owes",
                     "The records a reviewer has not decided yet at that stage (ta, then ft)."),
            _command(f"{REVIEW_CLI} conflicts --stage ta", "List the conflicts",
                     "The records the reviewers disagree on; settle each with screen --final."),
            _command(f"{REVIEW_CLI} kappa --stage ta", "Agreement (Cohen's kappa)",
                     "The agreement between the two reviewers; the methods report it."),
            _command(f'{REVIEW_CLI} signoff --gate screening --by "<operator name>"',
                     "Sign the screening off (operator, G-SCREENING)",
                     "Refused while a record is undecided or in conflict; it stays current while review/screening.jsonl is unchanged."),
        ],
    },
    "appraisal_extraction": {
        "skills": ["systematic-review"],
        "agent": "systematic-review & operator",
        "actions": [
            _prompt("/systematic-review", "Appraise and extract with the agent", [
                "Every included study gets its quality answers with the protocol's checklist (appraise).",
                "Every extracted value carries the quote or page of the study that holds it (extract).",
                "The agent extracts from the ingested Markdown; you check a sample.",
            ], "E.g.: appraise and extract the included study R0001.", optional=True, prefix="appraise "),
            _command(f"{REVIEW_CLI} status", "Summarise the review's records",
                     "The protocol, the searches, the PRISMA counts, the studies appraised and extracted, and the sign-offs."),
        ],
    },
    "synthesis": {
        "skills": ["systematic-review"],
        "agent": "systematic-review, diagram-author & operator",
        "actions": [
            _prompt("/systematic-review", "Build the synthesis with the agent", [
                "prisma counts the flow into review/prisma.json and flow draws the PRISMA 2020 flow diagram.",
                "biblio writes the counts per year and venue and the keyword co-occurrence.",
                "The agent builds with you the themes, the problem classes and one comparison table per theme from review/extraction.jsonl.",
                "When you accept the synthesis, you record it yourself (G-SYNTHESIS); the writing starts after it.",
            ], "E.g.: count the PRISMA flow, draw it and propose the themes.", optional=True, prefix="synthesize "),
            _command(f"{REVIEW_CLI} prisma", "Count the PRISMA flow", "Writes review/prisma.json from the records."),
            _command(f"{REVIEW_CLI} flow", "Draw the PRISMA 2020 flow diagram",
                     "Writes paper/Figures/prisma-flow.svg from the counts."),
            _command(f"{REVIEW_CLI} biblio", "Bibliometrics",
                     "The counts per year and venue and the keyword co-occurrence, in review/biblio.json."),
            _command(f'{REVIEW_CLI} signoff --gate synthesis --by "<operator name>"',
                     "Accept the synthesis (operator, G-SYNTHESIS)",
                     "Refused before review/prisma.json and the flow diagram exist; it stays current while they are unchanged."),
        ],
    },
    "writing": {
        "skills": ["paper-writing"],
        "agent": "paper-writing",
        "actions": [
            *copy.deepcopy(phase_actions.ACTIONS["scaffolding"]["actions"][:1]),
            *copy.deepcopy(phase_actions.ACTIONS["declarations"]["actions"][:1]),
            *copy.deepcopy(phase_actions.ACTIONS["writing"]["actions"]),
        ],
    },
    "paper": {
        "skills": ["figure-review", "paper-writing"],
        "agent": "figure-review & pdflatex",
        "actions": [
            *copy.deepcopy(phase_actions.ACTIONS["figures"]["actions"][:1]),
            *copy.deepcopy(phase_actions.ACTIONS["paper"]["actions"]),
        ],
    },
    "reporting_audit": {
        "skills": ["systematic-review", "skill-audit"],
        "agent": "systematic-review, skill-audit & smith audit",
        "actions": [
            _command(f"{REVIEW_CLI} checklist", "PRISMA 2020 checklist",
                     "The 27 items with the record or block that satisfies each, and the ones still owed."),
            *copy.deepcopy(phase_actions.ACTIONS["audit"]["actions"]),
        ],
    },
}

#: The files that show a step's work, as (label, glob) pairs relative to the workspace.
REVIEW_EVIDENCE: dict[str, tuple[tuple[str, str], ...]] = {
    "harness": phase_actions.EVIDENCE["harness"],
    "scoping": (("Existing reviews", "review/scope.json"),),
    "protocol": (("Review protocol", "review/protocol.json"),
                 ("Protocol approval (G-PROTOCOL)", "review/protocol.lock.json")),
    "identification": (("Search log", "review/searches.jsonl"), ("Identified records", "review/records.jsonl")),
    "screening": (("Screening decisions", "review/screening.jsonl"), ("Operator sign-offs", "review/signoffs.json")),
    "appraisal_extraction": (("Appraisal", "review/appraisal.jsonl"), ("Extraction", "review/extraction.jsonl")),
    "synthesis": (("PRISMA flow counts", "review/prisma.json"),
                  ("PRISMA 2020 flow diagram", "paper/Figures/prisma-flow.svg"),
                  ("Bibliometrics", "review/biblio.json"), ("Operator sign-offs", "review/signoffs.json")),
    "writing": (("Manuscript", "paper/main.tex"), ("Section contracts", "sections/*.md")),
    "paper": (("Compiled figures", "paper/Figures/*.pdf"), ("Compiled PDF", "paper/main.pdf")),
    "reporting_audit": phase_actions.EVIDENCE["audit"],
}

#: Steps that need nothing before them: the harness starts everything and the
#: reporting check and audit are transversal.
REVIEW_UNGATED = frozenset({"harness", "reporting_audit"})
#: The transversal step a later step never waits for.
REVIEW_TRANSVERSAL = "reporting_audit"
#: The operator gate each step waits for, on top of the step before it.
REVIEW_PHASE_GATES = {"identification": _PROTOCOL_GATE, "appraisal_extraction": _SCREENING_GATE,
                      "writing": _SYNTHESIS_GATE}

_GATE_OF_STEP = {"harness": "G-HARNESS", "scoping": "G-SCOPE", "protocol": _PROTOCOL_GATE,
                 "identification": "G-SEARCH", "screening": _SCREENING_GATE, "appraisal_extraction": "G-EXTRACTION",
                 "synthesis": _SYNTHESIS_GATE, "writing": "G-WRITING", "paper": "G-PDF", "reporting_audit": "G-AUDIT"}

_STEPS: dict[str, dict[str, Any]] = {
    "harness": {
        "name": "Phase 1: Environment Setup & Harness",
        "desc": "Workspace structure, harness projections (.claude, .opencode, .pi, .agents), the micromamba environment and runtime validation.",
        "tools": ["read", "bash"], "outputs": [".papersmith/", "papersmith.yaml"]},
    "scoping": {
        "name": "Phase 2: Scoping & Existing Reviews",
        "desc": "A preliminary search for existing reviews on the topic, so the protocol states the gap they leave.",
        "tools": ["read", "write", "http"], "outputs": ["review/scope.json"]},
    "protocol": {
        "name": "Phase 3: Review Protocol (G-PROTOCOL)",
        "desc": "The review protocol (PRISMA items 5-7, 24): objective, research questions with their PICOC, criteria, sources and queries, dates, screening, appraisal and extraction plan. The operator approves it before any search; a later change is an amendment.",
        "tools": ["read", "write"], "outputs": ["review/protocol.json", "review/protocol.lock.json"]},
    "identification": {
        "name": "Phase 4: Identification (Searches & Imports)",
        "desc": "The protocol's queries run on the open sources and the operator's database exports imported, each logged with its date, query and counts; then the duplicates are removed (PRISMA item 16).",
        "tools": ["read", "write", "http"], "outputs": ["review/searches.jsonl", "review/records.jsonl"]},
    "screening": {
        "name": "Phase 5: Two-Reviewer Screening",
        "desc": "Two independent reviewers decide every record on title and abstract, then on full text (PRISMA item 8); the operator settles the conflicts and signs the screening off.",
        "tools": ["read", "write"], "outputs": ["review/screening.jsonl", "review/signoffs.json"]},
    "appraisal_extraction": {
        "name": "Phase 6: Appraisal & Extraction",
        "desc": "The quality answers of every included study with the protocol's checklist, and its data items, each value with the quote or page that holds it (PRISMA items 9-11).",
        "tools": ["read", "write"], "outputs": ["review/appraisal.jsonl", "review/extraction.jsonl"]},
    "synthesis": {
        "name": "Phase 7: Synthesis & PRISMA Flow",
        "desc": "The PRISMA flow counts and diagram, the bibliometrics, and the themes, problem classes and comparison tables built with the operator (PRISMA items 12-22); the operator accepts the synthesis before the writing.",
        "tools": ["read", "write"], "outputs": ["review/prisma.json", "paper/Figures/prisma-flow.svg", "review/biblio.json"]},
    "writing": {
        "name": "Phase 8: Scaffolding, Declarations & Writing",
        "desc": "The paper/ tree opened from the review section contracts, the declarations recorded (review-registration included) and one block written at a time; every count is copied from review/prisma.json.",
        "tools": ["read", "write"], "outputs": ["paper/main.tex", "sections/*.md"]},
    "paper": {
        "name": "Phase 9: Figures & PDF Manuscript",
        "desc": "Every figure reviewed with /figure-review and paper/main.tex compiled to paper/main.pdf.",
        "tools": ["read", "bash", "latexmk"], "outputs": ["paper/Figures/", "paper/main.pdf"]},
    "reporting_audit": {
        "name": "Phase 10: Reporting Check & Audit",
        "desc": "The 27 PRISMA 2020 items with the record or section that satisfies each (the supplementary checklist journals ask for), and the cross-cutting audit; audits report, they never repair.",
        "tools": ["read", "bash"], "outputs": [".papersmith/audit.json"]},
}

#: Telemetry is not recorded for the review steps: the rows keep the
#: experimental shape with no numbers, and say so.
TELEMETRY_NOTE = "No telemetry is recorded for the review steps yet"

ARTIFACT_CATEGORY = "Review Records"

#: Per review section contract (file stem): its writing principles, its relation
#: to the rest of the paper and whether it carries figures. Its blocks are read
#: from the contract itself.
_SECTION_TEXT: dict[str, tuple[str, str, bool]] = {
    "01-title-and-keywords": (
        "The title names the report as a systematic review and states its topic; the keywords come from the venue's bounds.",
        "Projects the contributions the abstract summarizes and the introduction states.", False),
    "02-abstract": (
        "A structured abstract after PRISMA 2020 for Abstracts: background and objectives, methods, results, discussion, other.",
        "Summarizes the whole review; its counts come from review/prisma.json.", False),
    "03-introduction": (
        "Why the topic needs a synthesis now, what existing reviews leave open, and the review's idea and objectives in one proposal paragraph.",
        "States the research questions the results answer and the conclusions close.", False),
    "04-background": (
        "The definitions the review uses, the field's evolution and its open problems, named as the problem classes the results use.",
        "Fixes the vocabulary and the problem classes of the thematic synthesis.", False),
    "05-methods": (
        "The protocol and its registration, the eligibility criteria, sources, search strategy, selection, data collection, risk of bias and synthesis methods, transcribed from review/.",
        "Every number and criterion comes from the review records; the protocol flow diagram draws them.", True),
    "06-results": (
        "The study selection with its PRISMA flow diagram, the study characteristics, the risk of bias and a comparative thematic synthesis with one comparison table per theme.",
        "Answers the research questions of the introduction along the problem classes of the background.", True),
    "07-discussion": (
        "The principal findings revisited one by one, the other evidence, the challenges and directions as linked paragraphs, and the implications.",
        "Interprets the results against the existing reviews named in the introduction.", False),
    "08-limitations": (
        "The limitations of the evidence (bias, heterogeneity) and of the review process (sources, languages, screening).",
        "Qualifies the conclusions and the directions of future work.", False),
    "09-conclusions": (
        "The answer to each research question in the order of the introduction, and the future work it opens.",
        "Closes the argument opened in the abstract and the introduction.", False),
}

_HEADING = re.compile(r"^##\s+(?:Block|Slot)\s+`(?P<id>[^`]+)`(?P<rest>[^\n]*)$", re.M)
_ITEMS = re.compile(r"\((?P<word>items?)\s+(?P<numbers>\d[\d\-–]*)")

_CACHE_LOCK = threading.Lock()
_LOADED: dict[str, tuple[int, Any]] = {}


# --------------------------------------------------------------------------- review_cli


def review_cli(root: Path) -> Any | None:
    """The workspace's ``review_cli.py`` (else the dashboard's own copy) as a
    module, or ``None`` when neither loads. Reloaded when the file changes."""
    for path in (Path(root) / "skills" / "systematic-review" / "scripts" / "review_cli.py", DASHBOARD_REVIEW_CLI):
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            continue
        key = str(path)
        with _CACHE_LOCK:
            cached = _LOADED.get(key)
            if cached and cached[0] == stamp:
                return cached[1]
            try:
                spec = importlib.util.spec_from_file_location(f"_papersmith_review_cli_{len(_LOADED)}", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except (Exception, SystemExit):
                continue
            _LOADED[key] = (stamp, module)
            return module
    return None


def _failure(rc: Any, exc: BaseException) -> str:
    if rc is not None and isinstance(exc, rc.Refusal):
        return f"Review records unreadable ({exc.code}): {exc.message}"
    return f"Review records unreadable ({type(exc).__name__}): {exc}"


def _sub(number: str, name: str, status: str, detail: str) -> dict[str, Any]:
    return {"id": number, "name": name, "status": status, "detail": detail, "desc": detail}


def _state(done: int, total: int, started: bool = False) -> str:
    if total and done >= total:
        return "PASS"
    return "ACTIVE" if done or started else "PENDING"


def _signoff_detail(signoff: dict | None, *, signed: str, stale: str, absent: str) -> str:
    if signoff is None:
        return absent
    return signed.format(by=signoff.get("by") or "?", at=signoff.get("at") or "?") if signoff["current"] else stale


# --------------------------------------------------------------------------- steps


def _scoping(rc: Any, root: Path) -> dict[str, Any]:
    path = rc.review_dir(root) / "scope.json"
    if not path.is_file():
        status, detail = "PENDING", "No scoping search yet (review/scope.json)"
    else:
        scope = rc._read_json(path, "SCOPE_CORRUPT")
        reviews = scope.get("reviews") if isinstance(scope, dict) else None
        status = "PASS"
        detail = f"{len(reviews) if isinstance(reviews, list) else 0} existing review(s) found (review/scope.json)"
    return {"status": status, "detail": detail,
            "subfases": [_sub("2.1", "Existing reviews (review/scope.json)", status, detail)]}


def _protocol(rc: Any, root: Path) -> dict[str, Any]:
    path = rc.protocol_path(root)
    valid_status = "PENDING"
    if not path.is_file():
        status, detail = "PENDING", "No protocol in review/protocol.json"
    else:
        problems = rc.check_protocol(rc._read_json(path, "PROTOCOL_ABSENT"))
        lock_file = rc.lock_path(root)
        lock = rc._read_json(lock_file, "PROTOCOL_LOCK_CORRUPT") if lock_file.is_file() else None
        valid_status = "ACTIVE" if problems else "PASS"
        status = "ACTIVE"
        if problems:
            detail = f"Protocol drafted; {len(problems)} problem(s) left (review_cli.py protocol check)"
        elif not isinstance(lock, dict):
            detail = "Protocol valid, awaiting the operator's approval (G-PROTOCOL)"
        elif lock.get("sha256") != rc._sha256(path):
            detail = "Protocol changed after its approval: record an amendment (review_cli.py protocol amend)"
        else:
            status = "PASS"
            detail = (f"Protocol approved by {lock.get('approved_by') or '?'}; "
                      f"{len(lock.get('amendments') or [])} amendment(s)")
    return {"status": status, "detail": detail, "gate": status, "subfases": [
        _sub("3.1", "Protocol written and checked", valid_status,
             "review/protocol.json with every field of the template filled (review_cli.py protocol check)"),
        _sub("3.2", "Operator approval (G-PROTOCOL)", status,
             "review_cli.py protocol approve --by <name>; current while the protocol's sha256 matches it"),
    ]}


def _identification(rc: Any, root: Path) -> dict[str, Any]:
    base = rc.review_dir(root)
    searches = rc._read_jsonl(base / "searches.jsonl")
    records = rc._read_jsonl(base / "records.jsonl")
    duplicates = sum(1 for record in records if record.get("duplicate_of"))
    if records:
        status = "PASS"
        detail = (f"{len(searches)} search(es) logged; {len(records)} records identified; "
                  f"{duplicates} marked as duplicates")
    elif searches:
        status, detail = "ACTIVE", f"{len(searches)} search(es) logged, no record retrieved yet"
    else:
        status, detail = "PENDING", "No search logged in review/searches.jsonl"
    return {"status": status, "detail": detail, "progress": 0.5 if status == "ACTIVE" else None, "subfases": [
        _sub("4.1", "Database searches and imports (review/searches.jsonl)", "PASS" if searches else "PENDING",
             f"{len(searches)} search(es) logged"),
        _sub("4.2", "Deduplication (by DOI, then title and year)", "PASS" if records else "PENDING",
             f"{duplicates} of {len(records)} records marked as duplicates"),
    ]}


def _screening(rc: Any, root: Path, signoffs: dict) -> dict[str, Any]:
    unique = rc._unique_records(root)
    required = rc._required_reviewers(root)
    ta = rc.stage_outcomes(root, "ta", required)
    ft = rc.stage_outcomes(root, "ft", required)
    kept = [r["id"] for r in unique if (ta.get(r["id"]) or {}).get("decision") == "include"]

    def counts(outcomes: dict, ids: list[str]) -> tuple[int, int, int]:
        decided = sum(1 for rid in ids if (outcomes.get(rid) or {}).get("decision"))
        conflicts = sum(1 for rid in ids if (outcomes.get(rid) or {}).get("state") == "conflict")
        return decided, len(ids), conflicts

    ta_done, ta_total, ta_conflicts = counts(ta, [r["id"] for r in unique])
    ft_done, ft_total, ft_conflicts = counts(ft, kept)
    try:
        kappa = rc.cmd_kappa(argparse.Namespace(root=str(root), stage="ta", reviewers=None)).get("kappa")
    except rc.Refusal:
        kappa = None
    signoff = signoffs.get("screening")
    current = bool(signoff and signoff["current"])
    gate = "PASS" if current else ("ACTIVE" if unique else "PENDING")
    if current:
        detail = (f"Screening signed off by {signoff.get('by') or '?'}: {ta_total} record(s) at title/abstract, "
                  f"{ft_total} at full text")
    elif signoff:
        detail = "The screening changed after its sign-off: sign it off again (review_cli.py signoff --gate screening)"
    elif unique:
        detail = (f"Title/abstract: {ta_done} of {ta_total} decided; full text: {ft_done} of {ft_total} decided; "
                  f"{ta_conflicts + ft_conflicts} conflict(s)")
    else:
        detail = "No record to screen yet"
    total = ta_total + ft_total
    return {"status": gate, "gate": gate, "detail": detail,
            "progress": round((ta_done + ft_done) / (total + 1), 3) if gate == "ACTIVE" else None, "subfases": [
        _sub("5.1", "Title/abstract screening", _state(ta_done, ta_total, ta_done > 0),
             f"{ta_done} of {ta_total} records decided; {ta_conflicts} conflict(s)"),
        _sub("5.2", "Full-text screening", _state(ft_done, ft_total, ft_done > 0),
             f"{ft_done} of {ft_total} records decided; {ft_conflicts} conflict(s)"),
        _sub("5.3", "Agreement (Cohen's kappa)", "PASS" if kappa is not None else "PENDING",
             f"Title/abstract kappa: {kappa}" if kappa is not None
             else "Needs two reviewers on the same records"),
        _sub("5.4", "Screening sign-off (G-SCREENING, operator)", gate, _signoff_detail(
            signoff, signed="Signed off by {by} at {at}",
            stale="Stale: the decisions changed after the sign-off",
            absent="Not signed off yet: every record decided and no conflict left first")),
    ]}


def _appraisal_extraction(rc: Any, root: Path) -> dict[str, Any]:
    base = rc.review_dir(root)
    included = {r["id"] for r in rc._included(root)}
    appraised = len(included & {r.get("record_id") for r in rc._read_jsonl(base / "appraisal.jsonl")})
    extracted = len(included & {r.get("record_id") for r in rc._read_jsonl(base / "extraction.jsonl")})
    n = len(included)
    if not n:
        status, detail = "PENDING", "No included study yet (full-text screening)"
    else:
        status = "PASS" if appraised == n and extracted == n else "ACTIVE"
        detail = f"{n} included stud(ies): {appraised} appraised, {extracted} extracted"
    return {"status": status, "detail": detail,
            "progress": round((appraised + extracted) / (2 * n), 3) if status == "ACTIVE" else None, "subfases": [
        _sub("6.1", "Appraisal (review/appraisal.jsonl)", _state(appraised, n),
             f"{appraised} of {n} included studies appraised"),
        _sub("6.2", "Extraction (review/extraction.jsonl)", _state(extracted, n),
             f"{extracted} of {n} included studies extracted"),
    ]}


def _synthesis(rc: Any, root: Path, signoffs: dict) -> dict[str, Any]:
    base = rc.review_dir(root)
    on_file = {"prisma": (base / "prisma.json").is_file(),
               "flow": (root / "paper" / "Figures" / "prisma-flow.svg").is_file(),
               "biblio": (base / "biblio.json").is_file()}
    signoff = signoffs.get("synthesis")
    current = bool(signoff and signoff["current"])
    present = sum(on_file.values())
    gate = "PASS" if current else ("ACTIVE" if present or signoff else "PENDING")
    if current:
        detail = f"Synthesis accepted by {signoff.get('by') or '?'}"
    elif signoff:
        detail = ("The synthesis changed after its acceptance: accept it again "
                  "(review_cli.py signoff --gate synthesis)")
    elif present:
        detail = f"{present} of 3 synthesis records on file; awaiting the operator's acceptance (G-SYNTHESIS)"
    else:
        detail = "No synthesis record yet (review_cli.py prisma, flow, biblio)"

    def done(key: str) -> str:
        return "PASS" if on_file[key] else "PENDING"

    return {"status": gate, "gate": gate, "detail": detail,
            "progress": round(present / 4, 3) if gate == "ACTIVE" else None, "subfases": [
        _sub("7.1", "PRISMA flow counts (review/prisma.json)", done("prisma"),
             "Counted from the records by review_cli.py prisma"),
        _sub("7.2", "PRISMA 2020 flow diagram (paper/Figures/prisma-flow.svg)", done("flow"),
             "Drawn from the counts by review_cli.py flow"),
        _sub("7.3", "Bibliometrics (review/biblio.json)", done("biblio"),
             "Counts per year and venue and keyword co-occurrence (review_cli.py biblio)"),
        _sub("7.4", "Synthesis accepted (G-SYNTHESIS, operator)", gate, _signoff_detail(
            signoff, signed="Accepted by {by} at {at}",
            stale="Stale: the counts or the flow diagram changed after the acceptance",
            absent="Not accepted yet: the counts and the flow diagram first")),
    ]}


def _harness(facts: dict[str, Any]) -> dict[str, Any]:
    status = "PASS" if facts["harness_ok"] else "PENDING"
    detail = "Harness projections in place" if status == "PASS" else "Environment awaiting initialization"
    return {"status": status, "detail": detail, "subfases": [
        _sub("1.1", "Workspace & Manifest", status, "papersmith.yaml and the versioned base structure"),
        _sub("1.2", "Agent Projection", status, "Symbolic links to the operational harnesses"),
    ]}


def _writing(facts: dict[str, Any]) -> dict[str, Any]:
    done, total = facts["blocks_written"], facts["blocks_total"]
    blocks = f"{done}/{total} canonical blocks written ({facts['words']} words)"
    if total and done >= total:
        status = "PASS"
    else:
        status = "ACTIVE" if facts["has_scaffold"] or done else "PENDING"
    detail = blocks if facts["has_scaffold"] else "paper/main.tex awaiting scaffolding"
    return {"status": status, "detail": detail,
            "progress": round(done / max(1, total), 3) if status == "ACTIVE" else None, "subfases": [
        _sub("8.1", "Scaffolding from the review contracts", "PASS" if facts["has_scaffold"] else "PENDING",
             "paper/main.tex opened from the section contracts in sections/"),
        _sub("8.2", "Declarations (review-registration included)", "PASS" if facts["has_decl"] else "PENDING",
             "Recorded with /paper-writing mark; the reporting check verifies review-registration"),
        _sub("8.3", "Blocks written", _state(done, total), blocks),
    ]}


def _paper(facts: dict[str, Any]) -> dict[str, Any]:
    if facts["pdf_exists"]:
        status = "PASS"
        detail = f"PDF manuscript compiled ({facts['pdf_pages']} pages, {facts['pdf_kb']} KB)"
    else:
        status = "ACTIVE" if facts["figures"] else "PENDING"
        detail = "paper/main.pdf not compiled yet"
    return {"status": status, "detail": detail, "subfases": [
        _sub("9.1", "Figures reviewed (/figure-review)", "PASS" if facts["figures"] else "PENDING",
             f"{facts['figures']} vector figure(s) in paper/Figures/"),
        _sub("9.2", "Compiled PDF (paper/main.pdf)", "PASS" if facts["pdf_exists"] else "PENDING",
             "paper/main.pdf not compiled yet" if not facts["pdf_exists"] else detail),
    ]}


def _reporting(facts: dict[str, Any]) -> dict[str, Any]:
    verdict = facts["audit"]
    status = "PASS" if verdict is True else "PENDING"
    detail = ("Cross-cutting audit run and passed" if verdict is True else
              "The last audit failed: check .papersmith/audit.json" if verdict is False else
              "Cross-cutting audit pending")
    return {"status": status, "detail": detail, "subfases": [
        _sub("10.1", "PRISMA 2020 checklist (review_cli.py checklist)", "PENDING",
             "Computed on demand, never on the board's refresh: the 27 items with the record or block that satisfies each"),
        _sub("10.2", "Workspace audit (smith audit .)", status, detail),
    ]}


def board(root: Path, facts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The review's phase cards and gates, before ``phase_actions.attach``.

    ``facts`` are the paper-tree values the server already measured:
    ``harness_ok``, ``has_scaffold``, ``has_decl``, ``blocks_written``,
    ``blocks_total``, ``words``, ``figures``, ``pdf_exists``, ``pdf_pages``,
    ``pdf_kb`` and ``audit`` (True, False or None)."""
    root = Path(root)
    rc = review_cli(root)
    absent = ("review_cli.py is not available in this workspace (skills/systematic-review/scripts/); "
              "the review records cannot be read")
    signoffs: dict = {}
    signoff_error: BaseException | None = None
    if rc is not None:
        try:
            signoffs = rc.signoff_status(root)
        except Exception as exc:  # a corrupt record degrades the steps that read it
            signoff_error = exc
    readers = {
        "scoping": lambda: _scoping(rc, root),
        "protocol": lambda: _protocol(rc, root),
        "identification": lambda: _identification(rc, root),
        "screening": lambda: _screening(rc, root, signoffs),
        "appraisal_extraction": lambda: _appraisal_extraction(rc, root),
        "synthesis": lambda: _synthesis(rc, root, signoffs),
    }
    computed: dict[str, dict[str, Any]] = {
        "harness": _harness(facts), "writing": _writing(facts), "paper": _paper(facts),
        "reporting_audit": _reporting(facts),
    }
    for stage, read in readers.items():
        if rc is None:
            computed[stage] = {"status": "PENDING", "detail": absent, "subfases": []}
            continue
        try:
            if signoff_error is not None and stage in ("screening", "synthesis"):
                raise signoff_error
            computed[stage] = read()
        except Exception as exc:
            computed[stage] = {"status": "PENDING", "detail": _failure(rc, exc), "subfases": []}

    fases = []
    for number, stage in enumerate(REVIEW_STAGES, 1):
        step, info = _STEPS[stage], computed[stage]
        status = info["status"]
        progress = info.get("progress")
        if progress is None:
            progress = 1.0 if status == "PASS" else (0.5 if status == "ACTIVE" else 0.0)
        subfases = info["subfases"] or [_sub(f"{number}.1", REVIEW_LABELS[stage], status, info["detail"])]
        fases.append({
            "id": f"Fase {number}", "stage_id": stage, "name": step["name"], "gate": _GATE_OF_STEP[stage],
            "desc": step["desc"], "tools": list(step["tools"]), "outputs": list(step["outputs"]),
            "status": status, "progress": progress, "detail": info["detail"], "subfases": subfases,
        })
    return fases, _gates(computed, facts)


def _gates(computed: dict[str, dict[str, Any]], facts: dict[str, Any]) -> list[dict[str, Any]]:
    def gate_of(stage: str) -> str:
        return computed[stage].get("gate") or ("PASS" if computed[stage]["status"] == "PASS" else "PENDING")

    done, total = facts["blocks_written"], facts["blocks_total"]
    return [
        {"id": _PROTOCOL_GATE, "name": "Protocol Approval Gate", "status": gate_of("protocol"),
         "criteria": "The operator approved review/protocol.json (review_cli.py protocol approve --by <name>); it stays current while the protocol's sha256 matches the approval, and a later change is an amendment with its reason. No search runs before it.",
         "reviewer": "operator", "phase": "Fase 3"},
        {"id": _SCREENING_GATE, "name": "Screening Sign-off Gate", "status": gate_of("screening"),
         "criteria": "Two reviewers decided every record at title/abstract and full text, no conflict is left, and the operator signed the screening off (review_cli.py signoff --gate screening --by <name>); it stays current while review/screening.jsonl is unchanged.",
         "reviewer": "operator", "phase": "Fase 5"},
        {"id": _SYNTHESIS_GATE, "name": "Synthesis Acceptance Gate", "status": gate_of("synthesis"),
         "criteria": "The PRISMA flow counts (review/prisma.json) and their flow diagram exist and the operator accepted the synthesis (review_cli.py signoff --gate synthesis --by <name>); it stays current while they are unchanged. The writing starts after it.",
         "reviewer": "operator", "phase": "Fase 7"},
        {"id": "G1", "name": "Writing Readiness Gate", "status": "PASS" if facts["has_scaffold"] else "PENDING",
         "criteria": "Section contracts validated with a closed grammar and resolved dependencies.",
         "reviewer": "contract-auditor", "phase": "Fase 8"},
        {"id": "G2", "name": "Coupling Verification Gate", "status": "PASS" if facts["has_decl"] else "PENDING",
         "criteria": "Demanded facts (formulation, design, results) coupled with the authorship and funding declarations.",
         "reviewer": "paper-graph-auditor", "phase": "Fase 8"},
        {"id": "G3", "name": "Grounding & Style Leak Gate",
         "status": "PASS" if total and done >= total else ("ACTIVE" if done else "PENDING"),
         "criteria": "No empty citations or placeholders; strict isolation of bibliographic sources.",
         "reviewer": "grounding-auditor", "phase": "Fase 8"},
        {"id": "G4", "name": "Diagram & Raster Gate", "status": "PASS" if facts["figures"] else "PENDING",
         "criteria": "Compilation check of TikZ diagrams, methodological schemes and vector figures.",
         "reviewer": "figure-auditor", "phase": "Fase 9"},
    ]


# --------------------------------------------------------------------------- the rest of the status


def telemetry(fases: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    """One row per started step, in the experimental shape, with no numbers."""
    return [{"fase": phase["name"], "gate": phase["gate"], "tool_uses": None, "duracion": None, "tokens": None,
             "veredicto": phase["status"], "fecha": date, "note": TELEMETRY_NOTE}
            for phase in fases if phase["status"] in ("PASS", "ACTIVE")]


def artifacts(root: Path) -> list[dict[str, Any]]:
    """The review records under ``review/`` (JSON and JSONL), by name."""
    base = Path(root) / "review"
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.iterdir()):
        if path.name.startswith(".") or path.suffix not in (".json", ".jsonl") or not path.is_file():
            continue
        out.append({"rel_path": f"review/{path.name}", "name": path.name, "category": ARTIFACT_CATEGORY,
                    "size_kb": round(path.stat().st_size / 1024, 1)})
    return out


def _first_sentence(text: str, limit: int = 240) -> str:
    paragraph = " ".join(line.strip() for line in text.strip().split("\n\n", 1)[0].splitlines())
    match = re.search(r"^(.+?[.?!])(\s|$)", paragraph)
    sentence = match.group(1) if match else paragraph
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def _blocks(path: Path) -> list[dict[str, str]]:
    """The contract's blocks from its front matter, each with the PRISMA items
    its heading names and the first sentence of its rule as the question."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    meta, body = _ex._split_frontmatter(text)
    section = meta.get("section") if isinstance(meta, dict) else None
    if not isinstance(section, str):
        return []
    headings = {m.group("id"): m for m in _HEADING.finditer(body)}
    out = []
    for block in _ex._blocks_of(meta):
        block_id = str(block.get("id"))
        heading = headings.get(block_id)
        rest = heading.group("rest") if heading else ""
        items = _ITEMS.search(rest)
        if items:
            role = f"PRISMA 2020 {items.group('word')} {items.group('numbers')}"
        else:
            role = "Optional review block" if block.get("optional") or "optional" in rest else "Review block"
        question = ""
        if heading:
            following = body[heading.end():]
            nxt = re.search(r"^#{1,6}\s", following, re.M)
            question = _first_sentence(following[: nxt.start()] if nxt else following)
        out.append({"id": f"{section}.{block_id}", "role": role, "question": question or block_id})
    return out


def section_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """The review contracts' metadata keyed by file stem (the shared back
    matter keeps the experimental entry)."""
    sections = Path(root) / "sections"
    out = {}
    for stem, (principles, relations, figures) in _SECTION_TEXT.items():
        out[stem] = {"principles": principles, "cross_relations": relations, "has_figures": figures,
                     "blocks": _blocks(sections / f"{stem}.md")}
    return out


def stage_for(phase_id: str) -> str | None:
    """The review step a ``/api/phase/run`` id names: a step id or ``Fase N``."""
    text = str(phase_id or "").strip()
    if text in REVIEW_STAGES:
        return text
    parts = text.split()
    if len(parts) == 2 and parts[0].lower() == "fase" and parts[1].isdigit():
        index = int(parts[1]) - 1
        if 0 <= index < len(REVIEW_STAGES):
            return REVIEW_STAGES[index]
    return None


__all__ = ["ARTIFACT_CATEGORY", "REVIEW_ACTIONS", "REVIEW_EVIDENCE", "REVIEW_LABELS", "REVIEW_PHASE_GATES",
           "REVIEW_STAGES", "REVIEW_TRANSVERSAL", "REVIEW_UNGATED", "TELEMETRY_NOTE", "artifacts", "board",
           "review_cli", "section_metadata", "stage_for", "telemetry"]
