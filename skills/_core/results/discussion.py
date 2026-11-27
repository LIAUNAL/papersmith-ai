"""The results-discussion contract: ``Results/discussion.json`` (schema 1).

A product folder (``implementations/<repo>/<Name>/``) closes its proof of
concept (``AGREED.md``) or its full experiments (``Experimental_AGREED.md``)
with one ``Results/discussion.json``: hypothesis verdicts backed by tests, the
novelty justification, the qualitative/interpretability analysis and a
summarised discussion. This module is the one place that knows the schema:
the CLI, the dashboard view and the phase gating all import it.

Stdlib only, and importable by file path (``importlib.util.spec_from_file_location``);
the folder deliberately has no package ``__init__``.

Public API: ``STAGES``, ``VERDICTS``, ``NOVELTY_VERDICTS``,
``QUALITATIVE_KINDS``, ``DISCUSSION_TYPES``, ``DiscussionRefusal``,
``product_stage``, ``check_discussion``, ``load_and_check``,
``significance_comparisons``, ``scaffold``, ``unread_fields``, ``latest_protocol``,
``protocol_version``, ``is_current``, ``proposal_map``, ``finding_ids``,
``hypothesis_status``, ``link_proposal_hypotheses`` and ``current_findings``.

The board follows the current iteration: only a product whose ``protocol`` is the
latest ``experiments/experiments-*-vNN.md`` counts as a current finding, and each
discussion hypothesis carries ``proposal_hypotheses``, the proposal hypothesis ids
whose ``experiments`` (in the latest ``proposals/research-concept-*-rNN.sky.json``)
name its protocol experiment. Findings are keyed by those ids.

Every read is bounded (bytes per file, files, rows) and contained in the
product folder: an absolute path, a ``..`` escape or a symlink resolving
outside is refused, never followed. ``check_discussion`` and
``load_and_check`` never raise on malformed input; they report it as errors.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = 1
DISCUSSION_FILE = "Results/discussion.json"

STAGES = ("poc", "full")
VERDICTS = ("supported", "partially_supported", "not_supported", "inconclusive", "pending")
NOVELTY_VERDICTS = ("justified", "partially_justified", "not_justified", "pending")
QUALITATIVE_KINDS = ("qualitative", "interpretability", "explainability")
DISCUSSION_TYPES = ("comparative", "ablation", "failure-analysis", "sensitivity",
                    "interpretability", "cost", "generalization")
METRIC_ROLES = ("primary", "secondary")

#: Verdicts that claim something about the hypothesis and therefore need evidence.
DECIDED_VERDICTS = ("supported", "partially_supported", "not_supported")
#: Verdicts that, at stage ``full``, also need a ``significance:`` test.
TESTED_VERDICTS = DECIDED_VERDICTS

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PROTOCOL_BYTES = 1024 * 1024
MAX_SIGNIFICANCE_ROWS = 200
MAX_SIGNIFICANCE_FILES = 100
MAX_SCANNED_FILES = 20000
MAX_LISTED = 200
MAX_HYPOTHESES = 200
MAX_METRICS = 100
MAX_QUALITATIVE = 100
MAX_EVIDENCE = 50
MAX_ERRORS = 100
MAX_SUMMARY = 2000
MAX_PATH = 1024

FIGURE_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".pdf"}
TABLE_EXTS = {".csv", ".md", ".json"}

_PROTOCOL_RE = re.compile(r"^experiments-.+-v(\d+)\.md$")
#: An experiment declares [exp:<id>] in its own heading, at any level
#: (skills/_core/conventions/experiments.json), as the Experiments tab reads it.
_EXPERIMENT_RE = re.compile(r"^#{1,6}\s+.*?\[exp:([^\]]+)\]")
#: The expected-report heading, in the languages a protocol may be written in
#: (English, Spanish, Portuguese, French); matched without accents or case.
_REPORT_RE = re.compile(r"^###\s+(?:expected report|reporte esperado|informe esperado|"
                        r"relatorio esperado|rapport attendu):?\s*(.*)$", re.IGNORECASE)
#: A labelled field: ``- **Label:** text`` on a list bullet, or ``**Label:** text`` at the
#: start of a paragraph line, which is experimental-deliberation's canonical form
#: (skills/experimental-deliberation/SKILL.md, "Preservation").
_BULLET_RE = re.compile(r"^(?:-\s+)?\*\*([^*]+?):?\*\*:?\s*(.*)$")
#: The bullet labels the scaffold copies, keyed by their accent-folded, lower-case
#: form: English first, then the Spanish, Portuguese and French equivalents, so a
#: protocol written in its declared language still yields its hypotheses (#184).
_BULLET_FIELDS = {
    "hypothesis": "statement", "hipotesis": "statement", "hipotese": "statement",
    "hypothese": "statement",
    "success criterion": "criterion", "criterio de exito": "criterion",
    "criterio de sucesso": "criterion", "critere de succes": "criterion",
    "critere de reussite": "criterion",
}
#: The English label of each copied field, used to name an unread one.
_FIELD_LABELS = {"statement": "Hypothesis", "criterion": "Success criterion"}

_KNOWN_KEYS = {
    "top": {"schema", "stage", "protocol", "generated_at", "summary", "discussion_type", "metrics",
            "hypotheses", "novelty", "qualitative", "qualitative_not_applicable", "limitations",
            "next_steps", "available_evidence", "contribution_type", "contribution_type_protocol"},
    "metric": {"name", "role", "why", "source"},
    "hypothesis": {"id", "experiment", "proposal_hypotheses", "statement", "metric", "test",
                   "criterion", "observed", "evidence", "verdict", "rationale"},
    "novelty": {"claim", "verdict", "evidence", "rationale"},
    "qualitative": {"title", "kind", "method", "figure", "reading"},
}


def _contribution_type():
    """The shared contribution-type contract (``contribution_type.py``), loaded by path."""
    import importlib.util
    import sys

    name = "papersmith_contribution_type"
    if name not in sys.modules:
        path = Path(__file__).resolve().parent / "contribution_type.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


class DiscussionRefusal(Exception):
    """A request the contract refuses; ``code`` is the stable refusal code the CLI prints."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# the approval holder
# --------------------------------------------------------------------------
def product_stage(product: Path) -> str | None:
    """``"full"`` with ``Experimental_AGREED.md``, ``"poc"`` with ``AGREED.md``, else None."""
    try:
        product = Path(product)
        if (product / "Experimental_AGREED.md").is_file():
            return "full"
        if (product / "AGREED.md").is_file():
            return "poc"
    except (OSError, ValueError):
        pass
    return None


# --------------------------------------------------------------------------
# contained, bounded reads
# --------------------------------------------------------------------------
def _inside(base: Path, path: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve_in_product(base: Path, rel: str) -> tuple[Path | None, str | None]:
    """Resolve ``rel`` under the resolved product ``base``; return ``(path, None)`` or ``(None, reason)``."""
    if not rel.strip():
        return None, "path is empty"
    if "\x00" in rel:
        return None, "path contains a NUL byte"
    if len(rel) > MAX_PATH:
        return None, f"path is longer than {MAX_PATH} characters"
    if rel.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", rel):
        return None, "absolute paths are not allowed"
    normal = posixpath.normpath(rel.replace("\\", "/"))
    if normal == ".." or normal.startswith("../"):
        return None, "path is outside the product folder"
    try:
        resolved = (base / rel).resolve()
    except (OSError, ValueError, RuntimeError):
        return None, "path cannot be resolved"
    if not _inside(base, resolved):
        return None, "path is outside the product folder"
    return resolved, None


def _read_json(path: Path, base: Path) -> tuple[Any, str | None]:
    """Read and parse a JSON file inside ``base`` (resolved); ``(data, None)`` or ``(None, reason)``."""
    try:
        resolved = path.resolve()
        if not _inside(base, resolved):
            return None, "resolves outside the product folder, not read"
        if not resolved.is_file():
            return None, "is not a regular file"
        if resolved.stat().st_size > MAX_FILE_BYTES:
            return None, f"is larger than {MAX_FILE_BYTES // (1024 * 1024)} MiB, not read"
        with open(resolved, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except (OSError, ValueError, RuntimeError):
        return None, "is unreadable"
    if len(raw) > MAX_FILE_BYTES:
        return None, f"is larger than {MAX_FILE_BYTES // (1024 * 1024)} MiB, not read"
    try:
        return json.loads(raw.decode("utf-8")), None
    except UnicodeDecodeError:
        return None, "is not valid UTF-8"
    except (ValueError, RecursionError):
        return None, "is not valid JSON"


def _base(product: Path) -> Path:
    try:
        return Path(product).resolve()
    except (OSError, ValueError, RuntimeError):
        return Path(product)


def _results_dir(base: Path) -> Path | None:
    results = base / "Results"
    try:
        resolved = results.resolve()
    except (OSError, RuntimeError):
        return None
    return results if resolved.is_dir() and _inside(base, resolved) else None


def _walk_results(base: Path):
    """Yield ``(path, parts)`` for every file under ``Results/`` (bounded, symlinked directories not entered)."""
    results = _results_dir(base)
    if results is None:
        return
    visited = 0
    for current, dirs, files in os.walk(results, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            visited += 1
            if visited > MAX_SCANNED_FILES:
                return
            path = Path(current) / name
            try:
                resolved = path.resolve()
            except (OSError, RuntimeError):
                continue
            if not _inside(base, resolved) or not resolved.is_file():
                continue
            yield path, path.relative_to(results).parts


# --------------------------------------------------------------------------
# significance
# --------------------------------------------------------------------------
def _significance_rows(data: Any) -> list[Any]:
    """The test rows of a significance file: a list, or a dict wrapping one (as the dashboard reads it)."""
    if isinstance(data, dict):
        data = next((data[k] for k in ("tests", "comparisons", "results") if isinstance(data.get(k), list)),
                    [data])
    return data[:MAX_SIGNIFICANCE_ROWS] if isinstance(data, list) else []


def significance_comparisons(product: Path) -> list[str]:
    """Every ``comparison`` in the product's ``Results/**/significance*.json``, deduplicated, in file order."""
    base = _base(product)
    seen: dict[str, None] = {}
    files = 0
    for path, parts in _walk_results(base):
        name = parts[-1].lower()
        if not (name.startswith("significance") and name.endswith(".json")):
            continue
        files += 1
        if files > MAX_SIGNIFICANCE_FILES:
            break
        data, problem = _read_json(path, base)
        if problem is not None:
            continue
        for row in _significance_rows(data):
            comparison = row.get("comparison") if isinstance(row, dict) else None
            if isinstance(comparison, str) and comparison.strip():
                seen.setdefault(comparison.strip(), None)
    return list(seen)


# --------------------------------------------------------------------------
# the check
# --------------------------------------------------------------------------
def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class _Check:
    """Collects the errors and warnings of one run and resolves evidence lazily."""

    def __init__(self, product: Path, holder: str | None, stage: str) -> None:
        self.base = _base(product)
        self.holder = holder
        self.stage = stage
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.pending = False
        self._comparisons: set[str] | None = None

    def error(self, message: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(message)
        elif len(self.errors) == MAX_ERRORS:
            self.errors.append("more errors omitted")

    def warn(self, message: str) -> None:
        if len(self.warnings) < MAX_ERRORS:
            self.warnings.append(message)

    def comparisons(self) -> set[str]:
        if self._comparisons is None:
            self._comparisons = set(significance_comparisons(self.base))
        return self._comparisons

    def unknown_keys(self, where: str, item: dict, kind: str) -> None:
        for key in item:
            if key not in _KNOWN_KEYS[kind]:
                self.warn(f"{where}: unknown key {str(key)[:60]!r}")

    def path(self, where: str, value: Any) -> bool:
        """Check one product-relative path; True when it exists inside the product folder."""
        if not isinstance(value, str):
            self.error(f"{where}: must be a path relative to the product, got {type(value).__name__}")
            return False
        resolved, problem = _resolve_in_product(self.base, value)
        if problem is not None:
            self.error(f"{where}: {problem} ({value[:120]!r})")
            return False
        if not resolved.exists():
            self.error(f"{where}: {value} does not exist in the product folder")
            return False
        return True

    def evidence(self, where: str, value: Any) -> tuple[int, int] | None:
        """Check an evidence list; return ``(entries, significance entries)`` or None when it is not a list."""
        if not isinstance(value, list):
            self.error(f"{where}: must be a list of paths or 'significance:<comparison>'")
            return None
        if len(value) > MAX_EVIDENCE:
            self.error(f"{where}: more than {MAX_EVIDENCE} entries")
            return None
        significance = 0
        for index, entry in enumerate(value):
            here = f"{where}[{index}]"
            if isinstance(entry, str) and entry.startswith("significance:"):
                name = entry[len("significance:"):].strip()
                if not name:
                    self.error(f"{here}: 'significance:' needs a comparison name")
                elif name not in self.comparisons():
                    self.error(f"{here}: no comparison {name!r} in Results/**/significance*.json")
                else:
                    significance += 1
            else:
                self.path(here, entry)
        return len(value), significance


def _check_metrics(ctx: _Check, data: dict) -> None:
    metrics = data.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        ctx.error("metrics: at least one metric is required")
        return
    if len(metrics) > MAX_METRICS:
        ctx.error(f"metrics: more than {MAX_METRICS} entries")
        return
    for index, metric in enumerate(metrics):
        where = f"metrics[{index}]"
        if not isinstance(metric, dict):
            ctx.error(f"{where}: must be an object")
            continue
        for key in ("name", "why"):
            if not _text(metric.get(key)):
                ctx.error(f"{where}.{key}: required and non-empty")
        if "role" in metric and metric["role"] not in METRIC_ROLES:
            ctx.warn(f"{where}.role: expected one of {', '.join(METRIC_ROLES)}")
        ctx.unknown_keys(where, metric, "metric")


def _check_hypotheses(ctx: _Check, data: dict) -> list[str]:
    """Check the hypotheses; return their verdicts that were valid enum members."""
    hypotheses = data.get("hypotheses")
    verdicts: list[str] = []
    if not isinstance(hypotheses, list) or not hypotheses:
        ctx.error("hypotheses: at least one hypothesis is required")
        return verdicts
    if len(hypotheses) > MAX_HYPOTHESES:
        ctx.error(f"hypotheses: more than {MAX_HYPOTHESES} entries")
        return verdicts
    seen: set[str] = set()
    for index, hypothesis in enumerate(hypotheses):
        where = f"hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            ctx.error(f"{where}: must be an object")
            continue
        for key in ("id", "statement"):
            if not _text(hypothesis.get(key)):
                ctx.error(f"{where}.{key}: required and non-empty")
        identifier = hypothesis.get("id")
        if _text(identifier):
            if identifier in seen:
                ctx.warn(f"{where}.id: duplicate id {identifier!r}")
            seen.add(identifier)
        verdict = hypothesis.get("verdict")
        valid = isinstance(verdict, str) and verdict in VERDICTS
        if not valid:
            ctx.error(f"{where}.verdict: must be one of {', '.join(VERDICTS)}")
        else:
            verdicts.append(verdict)
        if "proposal_hypotheses" in hypothesis:
            linked = hypothesis["proposal_hypotheses"]
            if not isinstance(linked, list) or not all(_text(item) for item in linked):
                ctx.error(f"{where}.proposal_hypotheses: must be a list of proposal hypothesis ids")
        counted = ctx.evidence(f"{where}.evidence", hypothesis["evidence"]) if "evidence" in hypothesis else None
        if valid and verdict in DECIDED_VERDICTS:
            if "evidence" not in hypothesis or (counted is not None and counted[0] == 0):
                ctx.error(f"{where}.evidence: a {verdict} verdict needs at least one evidence entry")
            elif counted is not None and verdict in TESTED_VERDICTS and counted[1] == 0:
                if ctx.stage == "full":
                    ctx.error(f"{where}.evidence: at stage full a {verdict} verdict must cite a "
                              "'significance:<comparison>' entry (the hypothesis test is mandatory)")
                else:
                    ctx.warn(f"{where}.evidence: a {verdict} verdict cites no "
                             "'significance:<comparison>' entry (mandatory at stage full)")
        ctx.unknown_keys(where, hypothesis, "hypothesis")
    return verdicts


def _check_novelty(ctx: _Check, data: dict) -> str | None:
    novelty = data.get("novelty")
    if not isinstance(novelty, dict):
        ctx.error("novelty: required object with claim, verdict, evidence and rationale")
        return None
    verdict = novelty.get("verdict")
    valid = isinstance(verdict, str) and verdict in NOVELTY_VERDICTS
    if not valid:
        ctx.error(f"novelty.verdict: must be one of {', '.join(NOVELTY_VERDICTS)}")
    counted = ctx.evidence("novelty.evidence", novelty["evidence"]) if "evidence" in novelty else None
    if valid and verdict != "pending" and ("evidence" not in novelty or (counted is not None and counted[0] == 0)):
        ctx.error(f"novelty.evidence: a {verdict} verdict needs at least one evidence entry")
    ctx.unknown_keys("novelty", novelty, "novelty")
    return verdict if valid else None


def _check_qualitative(ctx: _Check, data: dict) -> None:
    entries = data.get("qualitative")
    reason = data.get("qualitative_not_applicable")
    if entries is not None and not isinstance(entries, list):
        ctx.error("qualitative: must be a list")
    elif not entries and not _text(reason):
        ctx.error("qualitative: add at least one entry or a non-empty qualitative_not_applicable reason")
    if "qualitative_not_applicable" in data and reason is not None and not isinstance(reason, str):
        ctx.error("qualitative_not_applicable: must be a string")
    if not isinstance(entries, list):
        return
    if len(entries) > MAX_QUALITATIVE:
        ctx.error(f"qualitative: more than {MAX_QUALITATIVE} entries")
        return
    for index, entry in enumerate(entries):
        where = f"qualitative[{index}]"
        if not isinstance(entry, dict):
            ctx.error(f"{where}: must be an object")
            continue
        kind = entry.get("kind")
        if not (isinstance(kind, str) and kind in QUALITATIVE_KINDS):
            ctx.error(f"{where}.kind: must be one of {', '.join(QUALITATIVE_KINDS)}")
        ctx.path(f"{where}.figure", entry.get("figure", ""))
        ctx.unknown_keys(where, entry, "qualitative")


def _run_check(product: Path, data: Any, holder: str | None) -> _Check:
    declared = data.get("stage") if isinstance(data, dict) else None
    stage = holder or (declared if declared in STAGES else "poc")
    ctx = _Check(product, holder, stage)
    if not isinstance(data, dict):
        ctx.error("discussion: the top level must be a JSON object")
        return ctx
    if type(data.get("schema")) is not int or data["schema"] != SCHEMA:
        ctx.error(f"schema: must be the integer {SCHEMA}")
    if holder is None:
        ctx.error("stage: the product has no AGREED.md or Experimental_AGREED.md")
    elif not (isinstance(declared, str) and declared in STAGES):
        ctx.error("stage: must be 'poc' or 'full'")
    elif declared != holder:
        ctx.error(f"stage: {declared!r} disagrees with the product's approval file ({holder!r})")
    summary = data.get("summary")
    if not _text(summary):
        ctx.error("summary: required and non-empty")
    elif len(summary) > MAX_SUMMARY:
        ctx.error(f"summary: longer than {MAX_SUMMARY} characters")
    types = data.get("discussion_type")
    if types is not None:
        if not isinstance(types, list):
            ctx.warn("discussion_type: expected a list")
        else:
            for item in types:
                if not (isinstance(item, str) and item in DISCUSSION_TYPES):
                    ctx.warn(f"discussion_type: unknown type {str(item)[:60]!r}")
    _check_metrics(ctx, data)
    verdicts = _check_hypotheses(ctx, data)
    novelty = _check_novelty(ctx, data)
    _check_qualitative(ctx, data)
    if "contribution_type" in data:
        for problem in _contribution_type().problems(data["contribution_type"]):
            ctx.error(problem)
    if "contribution_type_protocol" in data:
        # The protocol the paper-reviewer judged, beside the type (the shared contract
        # refuses unknown keys inside it), so the board can tell a stale type.
        judged = data["contribution_type_protocol"]
        if not _text(judged) or len(judged) > MAX_PATH:
            ctx.error(f"contribution_type_protocol: a non-empty path of at most {MAX_PATH} characters")
    ctx.unknown_keys("discussion", data, "top")
    ctx.pending = "pending" in verdicts or novelty == "pending"
    return ctx


def check_discussion(product: Path, data: Any) -> dict:
    """Validate ``data`` against schema 1 for ``product``; never raises.

    Returns ``{"status": "complete"|"draft"|"invalid", "errors": [...], "warnings": [...],
    "stage": <the approval holder's stage or None>}``. ``invalid`` is any error; ``draft`` is
    valid with a pending hypothesis or novelty; ``complete`` is valid with nothing pending.
    """
    holder = product_stage(product)
    try:
        ctx = _run_check(product, data, holder)
    except Exception as exc:  # The contract: malformed input is reported, never raised.
        return {"status": "invalid", "errors": [f"discussion: could not be checked ({type(exc).__name__})"],
                "warnings": [], "stage": holder}
    if ctx.errors:
        status = "invalid"
    else:
        status = "draft" if ctx.pending else "complete"
    return {"status": status, "errors": ctx.errors, "warnings": ctx.warnings, "stage": holder}


def load_and_check(product: Path) -> dict:
    """Read ``<product>/Results/discussion.json`` and check it; never raises.

    Returns ``{"present", "file", "data", "status", "errors", "warnings", "stage"}``. An absent
    file is ``present`` False with status ``"absent"``; an unreadable or malformed one is
    ``present`` True with status ``"invalid"`` and ``data`` None.
    """
    base = _base(product)
    path = base / DISCUSSION_FILE
    holder = product_stage(product)
    if not os.path.lexists(path):
        return {"present": False, "file": DISCUSSION_FILE, "data": None, "status": "absent",
                "errors": [], "warnings": [], "stage": holder}
    data, problem = _read_json(path, base)
    if problem is not None:
        return {"present": True, "file": DISCUSSION_FILE, "data": None, "status": "invalid",
                "errors": [f"{DISCUSSION_FILE}: {problem}"], "warnings": [], "stage": holder}
    return {"present": True, "file": DISCUSSION_FILE, "data": data, **check_discussion(product, data)}


# --------------------------------------------------------------------------
# the scaffold
# --------------------------------------------------------------------------
def _latest_protocol(root: Path) -> Path | None:
    folder = root / "experiments"
    best: tuple[int, str] | None = None
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        match = _PROTOCOL_RE.match(name)
        if not match:
            continue
        path = folder / name
        try:
            resolved = path.resolve()
            if not resolved.is_file() or not _inside(root.resolve(), resolved):
                continue
        except (OSError, RuntimeError):
            continue
        key = (int(match.group(1)), name)
        if best is None or key > best:
            best = key
    return folder / best[1] if best else None


def _fold(label: str) -> str:
    """``label`` lower-cased, accents stripped and spaces collapsed (``Hipótesis`` -> ``hipotesis``)."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", label)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.lower().split())


def _fold_heading(line: str) -> str:
    """A ``###`` heading with its title folded by ``_fold``, so the report regex matches any spelling."""
    if not line.startswith("### "):
        return line
    return "### " + _fold(line[4:])


def unread_fields(data: dict) -> list[str]:
    """One plain sentence per scaffolded hypothesis field the protocol did not yield.

    ``data`` is a ``scaffold`` result. A protocol bullet the scaffold cannot read
    (another language, another label) leaves its field empty; this names the
    experiment and the field instead of letting the empty value pass silently.
    """
    if not isinstance(data, dict):
        return []
    protocol = data.get("protocol") or "the protocol"
    out: list[str] = []
    for item in data.get("hypotheses") or []:
        if not isinstance(item, dict):
            continue
        for field, label in _FIELD_LABELS.items():
            if not item.get(field):
                out.append(f"experiment {item.get('experiment', '?')}: could not read its {label} "
                           f"from {protocol}; fill it by hand")
    return out


def _protocol_experiments(path: Path) -> list[dict[str, str]]:
    """Each experiment heading carrying ``[exp:<id>]`` (any level) with its first ``Hypothesis`` and ``Success criterion`` (bullet or paragraph line), verbatim."""
    try:
        with open(path, "rb") as handle:
            text = handle.read(MAX_PROTOCOL_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return []
    experiments: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_report = False
    for line in text.splitlines():
        stripped = line.strip()
        match = _EXPERIMENT_RE.match(stripped)
        if match:
            current = {"experiment": match.group(1).strip(), "statement": "", "criterion": ""}
            experiments.append(current)
            in_report = False
            continue
        if stripped.startswith("## "):
            current, in_report = None, False
            continue
        if current is None:
            continue
        if _REPORT_RE.match(_fold_heading(stripped)):
            in_report = True
            continue
        if stripped.startswith("### "):
            in_report = False
            continue
        if in_report:
            continue
        bullet = _BULLET_RE.match(stripped)
        if bullet:
            field = _BULLET_FIELDS.get(_fold(bullet.group(1)))
            if field and not current[field]:
                current[field] = bullet.group(2).strip()
    return experiments


def _available_evidence(product: Path) -> dict[str, list[str]]:
    base = _base(product)
    found: dict[str, list[str]] = {"figures": [], "tables": [], "qualitative": []}
    for path, parts in _walk_results(base):
        if parts[0] == "hpo":
            continue
        name, ext = parts[-1].lower(), path.suffix.lower()
        folders = parts[:-1]
        rel = path.relative_to(base).as_posix()
        if parts[0] == "qualitative" and len(parts) > 1:
            if ext in FIGURE_EXTS:
                found["qualitative"].append(rel)
        elif "figures" in folders and ext in FIGURE_EXTS:
            found["figures"].append(rel)
        elif ("tables" in folders and ext in TABLE_EXTS) or (len(parts) <= 2 and name == "summary.json"):
            found["tables"].append(rel)
    out = {key: sorted(values)[:MAX_LISTED] for key, values in found.items()}
    out["significance"] = significance_comparisons(base)[:MAX_LISTED]
    return out


def scaffold(product: Path, root: Path | None = None) -> dict:
    """Build the S1 skeleton for ``product``; writes nothing.

    ``root`` is the workspace holding ``experiments/`` (default ``product.parents[2]`` for
    ``implementations/<repo>/<Name>``). One hypothesis (``H1``..``Hn``) per
    ``## Experiment [exp:<id>]`` of the latest ``experiments-*-vNN.md``, its declared
    **Hypothesis** and **Success criterion** copied verbatim, and its ``proposal_hypotheses``
    read from the latest proposal sky overlay (``proposal_map``); the positional ids are a
    recorded contract and stay as they are; every verdict ``pending``; no
    number is ever invented. The skeleton is ``invalid`` until the author fills ``summary``,
    ``metrics`` and the qualitative analysis (or its reason): that is expected.

    Raises ``DiscussionRefusal`` (``PRODUCT_ABSENT`` or ``APPROVAL_ABSENT``).
    """
    base = _base(product)
    if not base.is_dir():
        raise DiscussionRefusal("PRODUCT_ABSENT", f"{product} is not a product folder")
    stage = product_stage(base)
    if stage is None:
        raise DiscussionRefusal("APPROVAL_ABSENT",
                                f"{product} has neither Experimental_AGREED.md nor AGREED.md")
    if root is None:
        root = base.parents[2] if len(base.parents) > 2 else base
    root = Path(root)
    protocol = _latest_protocol(root)
    experiments = _protocol_experiments(protocol) if protocol is not None else []
    mapping = proposal_map(root)
    hypotheses = [{
        "id": f"H{index}", "experiment": item["experiment"],
        "proposal_hypotheses": list(mapping.get(_exp_key(item["experiment"]), [])),
        "statement": item["statement"],
        "metric": "", "test": "", "criterion": item["criterion"], "observed": "",
        "evidence": [], "verdict": "pending", "rationale": "",
    } for index, item in enumerate(experiments, start=1)]
    relative = ""
    if protocol is not None:
        try:
            relative = protocol.relative_to(root).as_posix()
        except ValueError:
            relative = protocol.as_posix()
    return {
        "schema": SCHEMA,
        "stage": stage,
        "protocol": relative,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": "",
        "discussion_type": [],
        "metrics": [],
        "hypotheses": hypotheses,
        "novelty": {"claim": "", "verdict": "pending", "evidence": [], "rationale": ""},
        "qualitative": [],
        "qualitative_not_applicable": "",
        "limitations": [],
        "next_steps": [],
        "available_evidence": _available_evidence(base),
    }


# --------------------------------------------------------------------------
# the current iteration: the latest protocol and the proposal ids
# --------------------------------------------------------------------------
_REVISION_RE = re.compile(r"^research-concept-(?:.+-)?r(\d+)\.md$")
_VERSION_RE = re.compile(r"-v(\d+)\.md$")
_MERGER = Path(__file__).resolve().parents[2] / "proposal-deliberation" / "scripts" / "merge_proposal_sky.py"
#: Verdicts in the order a combined status reads them.
_SUPPORTING = ("supported", "partially_supported")


def _merger():
    """``merge_proposal_sky.py``, the one owner of the overlay's pillars and hypotheses."""
    import importlib.util
    import sys

    name = "papersmith_merge_proposal_sky"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _MERGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


def _workspace(product: Path, root: Path | None) -> Path:
    base = _base(product)
    if root is None:
        root = base.parents[2] if len(base.parents) > 2 else base
    return Path(root)


def latest_protocol(root: Path) -> str:
    """The latest published protocol, ``experiments/experiments-*-vNN.md``, relative to ``root``; ``""`` when none."""
    root = Path(root)
    path = _latest_protocol(root)
    if path is None:
        return ""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def protocol_version(protocol: Any) -> int | None:
    """``NN`` of a ``...-vNN.md`` protocol path, else None."""
    match = _VERSION_RE.search(str(protocol or "").strip())
    return int(match.group(1)) if match else None


def is_current(protocol: Any, latest: str) -> bool:
    """Whether a discussion's recorded ``protocol`` is ``latest``.

    Without a published protocol every product is current. With one, a product counts
    only when it names that file; a discussion that records no protocol cannot be
    shown to belong to the current iteration, so it is not current.
    """
    if not latest:
        return True
    recorded = str(protocol or "").strip().replace("\\", "/")
    return bool(recorded) and posixpath.basename(recorded) == posixpath.basename(latest)


def _exp_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("exp:"):
        text = text[4:].strip()
    return text.casefold()


def latest_sky(root: Path) -> Path | None:
    """The latest ``proposals/research-concept-*-rNN.sky.json``, else None."""
    root = Path(root)
    folder = root / "proposals"
    ranked: list[tuple[int, str]] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for name in names:
        match = _REVISION_RE.match(name)
        if not match:
            continue
        path = folder / name
        try:
            if path.is_file() and _inside(root.resolve(), path.resolve()):
                ranked.append((int(match.group(1)), name))
        except (OSError, RuntimeError):
            continue
    if not ranked:
        return None
    sky = folder / (max(ranked)[1][:-3] + ".sky.json")
    return sky if sky.is_file() else None


def _sky_hypotheses(root: Path) -> tuple[Path | None, list[dict] | None, str | None]:
    """``(sky path, its hypotheses, refusal)``; hypotheses None when there is no usable sky."""
    sky = latest_sky(root)
    if sky is None:
        return None, None, "no proposals/research-concept-*-rNN.sky.json"
    try:
        if sky.stat().st_size > MAX_FILE_BYTES:
            return sky, None, "the proposal sky is too large"
        overlay = json.loads(sky.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return sky, None, "the proposal sky is unreadable or not JSON"
    found, refusal = _merger().pillars_and_hypotheses(overlay)
    if found is None:
        return sky, None, refusal
    return sky, found["hypotheses"], None


def proposal_map(root: Path) -> dict[str, list[str]]:
    """Protocol experiment id (folded) -> the proposal hypothesis ids whose ``experiments`` name it.

    Read from the latest proposal sky overlay, in its order; ``{}`` without a usable sky.
    """
    _sky, hypotheses, _refusal = _sky_hypotheses(Path(root))
    mapping: dict[str, list[str]] = {}
    for hypothesis in hypotheses or []:
        for experiment in hypothesis.get("experiments", []):
            ids = mapping.setdefault(_exp_key(experiment), [])
            if hypothesis["id"] not in ids:
                ids.append(hypothesis["id"])
    return mapping


def finding_ids(hypothesis: dict, mapping: dict[str, list[str]] | None = None) -> list[tuple[str, bool]]:
    """The ids a discussion hypothesis is shown under: ``[(id, unmapped)]``.

    Each of its ``proposal_hypotheses`` (one finding per id); else, when ``mapping``
    (``proposal_map``) names its experiment, those proposal ids, derived on read so a
    discussion written before the field existed is shown under the current proposal
    ids without rewriting it; else its positional id marked unmapped.
    """
    linked = hypothesis.get("proposal_hypotheses")
    if isinstance(linked, list):
        ids = [item.strip() for item in linked if _text(item)]
        if ids:
            return [(item, False) for item in dict.fromkeys(ids)]
    if mapping:
        derived = mapping.get(_exp_key(str(hypothesis.get("experiment") or "")), [])
        if derived:
            return [(item, False) for item in dict.fromkeys(derived)]
    return [(str(hypothesis.get("id") or "").strip(), True)]


def hypothesis_status(verdicts: list[str]) -> str:
    """One status for a proposal hypothesis from the verdicts of its current findings.

    ``supported`` or ``not_supported`` when every finding says so; ``partially_supported``
    when the decided verdicts are mixed and one supports it; ``pending`` while nothing is
    decided (``inconclusive`` when every finding is); otherwise ``not_supported``.
    """
    verdicts = [v if v in VERDICTS else "pending" for v in verdicts]
    if not verdicts:
        return "pending"
    if len(set(verdicts)) == 1:
        return verdicts[0]
    decided = [v for v in verdicts if v in DECIDED_VERDICTS]
    if not decided:
        return "pending" if "pending" in verdicts else "inconclusive"
    if any(v in _SUPPORTING for v in decided):
        return "partially_supported"
    return "not_supported"


def _write_discussion(base: Path, data: dict) -> None:
    """Replace ``<base>/Results/discussion.json`` whole (temporary file, then rename)."""
    results = base / "Results"
    fd, temporary = tempfile.mkstemp(prefix=".discussion-", suffix=".json", dir=results)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary, base / DISCUSSION_FILE)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def link_proposal_hypotheses(product: Path, root: Path | None = None, *, write: bool = True) -> dict:
    """Backfill ``proposal_hypotheses`` on an existing ``Results/discussion.json``.

    Sets each hypothesis's ``proposal_hypotheses`` from ``proposal_map`` (by its
    ``experiment``) and touches no other field: ids, verdicts and evidence stay as they
    are. Writes the file only when something changed and ``write`` is true.

    Returns ``{"file", "sky", "changed": [{"id", "experiment", "before", "after"}],
    "written"}``. Raises ``DiscussionRefusal`` (``PRODUCT_ABSENT``, ``DISCUSSION_ABSENT``,
    ``DISCUSSION_UNREADABLE``, ``SKY_ABSENT``, ``SKY_REFUSED`` or ``WRITE_FAILED``).
    """
    base = _base(product)
    if not base.is_dir():
        raise DiscussionRefusal("PRODUCT_ABSENT", f"{product} is not a product folder")
    path = base / DISCUSSION_FILE
    if not os.path.lexists(path):
        raise DiscussionRefusal("DISCUSSION_ABSENT", f"{DISCUSSION_FILE} does not exist; run scaffold first")
    data, problem = _read_json(path, base)
    if problem is not None or not isinstance(data, dict):
        raise DiscussionRefusal("DISCUSSION_UNREADABLE",
                                f"{DISCUSSION_FILE}: {problem or 'the top level is not a JSON object'}")
    root = _workspace(base, root)
    sky, hypotheses, refusal = _sky_hypotheses(root)
    if sky is None:
        raise DiscussionRefusal("SKY_ABSENT", f"{refusal}: nothing to link the hypotheses to")
    if hypotheses is None:
        raise DiscussionRefusal("SKY_REFUSED", f"{sky.name}: {refusal}")
    mapping = proposal_map(root)
    changed: list[dict] = []
    for item in data.get("hypotheses") or []:
        if not isinstance(item, dict):
            continue
        after = list(mapping.get(_exp_key(item.get("experiment")), []))
        before = item.get("proposal_hypotheses")
        if before != after:
            item["proposal_hypotheses"] = after
            changed.append({"id": item.get("id"), "experiment": item.get("experiment"),
                            "before": before, "after": after})
    written = False
    if changed and write:
        try:
            _write_discussion(base, data)
        except OSError as exc:
            raise DiscussionRefusal("WRITE_FAILED",
                                    f"could not write {DISCUSSION_FILE}: {exc.strerror or exc}") from exc
        written = True
    try:
        sky_rel = sky.relative_to(root).as_posix()
    except ValueError:
        sky_rel = sky.as_posix()
    return {"file": DISCUSSION_FILE, "sky": sky_rel, "changed": changed, "written": written}


def _products_of(root: Path) -> list[Path]:
    folder = Path(root) / "implementations"
    out: list[Path] = []
    try:
        for repo in sorted(folder.iterdir()) if folder.is_dir() else []:
            if repo.is_dir() and not repo.name.startswith("."):
                out.extend(p for p in sorted(repo.iterdir()) if p.is_dir() and not p.name.startswith("."))
    except OSError:
        pass
    return out


def current_findings(root: Path, products: list[Path] | None = None) -> dict:
    """The findings of the current iteration; never raises on a malformed discussion.

    Only products whose ``protocol`` is the latest published one count; every other
    product with a discussion is listed in ``superseded`` with its protocol and never
    merges with the current findings. A hypothesis yields one finding per
    ``proposal_hypotheses`` id, else one under its positional id marked ``unmapped``.

    Returns ``{"protocol", "version", "findings": [...], "superseded": [...],
    "statuses": {id: {"status", "verdicts", "experiments", "products", "unmapped"}}}``.
    A status reads the full-stage findings of an id when it has any, else the pilot's.
    """
    root = Path(root)
    latest = latest_protocol(root)
    try:
        mapping = proposal_map(root)
    except Exception:  # noqa: BLE001 - without a usable sky the ids stay positional
        mapping = {}
    findings: list[dict] = []
    superseded: list[dict] = []
    for product in products if products is not None else _products_of(root):
        try:
            loaded = load_and_check(product)
        except Exception:  # noqa: BLE001 - an unreadable product is no finding
            continue
        data = loaded.get("data")
        if not isinstance(data, dict):
            continue
        try:
            rel = Path(product).resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            rel = Path(product).name
        stage = loaded.get("stage") or (data.get("stage") if data.get("stage") in STAGES else "poc")
        protocol = str(data.get("protocol") or "")
        entry = {"product": rel, "name": Path(product).name, "stage": stage, "protocol": protocol,
                 "version": protocol_version(protocol), "status": loaded.get("status")}
        if not is_current(protocol, latest):
            superseded.append(entry)
            continue
        for index, hypothesis in enumerate(h for h in data.get("hypotheses") or [] if isinstance(h, dict)):
            verdict = hypothesis.get("verdict") if hypothesis.get("verdict") in VERDICTS else "pending"
            for identifier, unmapped in finding_ids(hypothesis, mapping):
                if not identifier:
                    continue
                findings.append({"id": identifier, "unmapped": unmapped,
                                 "discussion_id": str(hypothesis.get("id") or ""),
                                 "experiment": str(hypothesis.get("experiment") or ""),
                                 "verdict": verdict, "index": index, **entry})
    statuses: dict[str, dict] = {}
    for identifier in dict.fromkeys(f["id"] for f in findings):
        mine = [f for f in findings if f["id"] == identifier]
        full = [f for f in mine if f["stage"] == "full"]
        chosen = full or mine
        statuses[identifier] = {
            "status": hypothesis_status([f["verdict"] for f in chosen]),
            "verdicts": [f["verdict"] for f in chosen],
            "experiments": list(dict.fromkeys(f["experiment"] for f in chosen if f["experiment"])),
            "products": list(dict.fromkeys(f["product"] for f in chosen)),
            "unmapped": all(f["unmapped"] for f in chosen),
        }
    return {"protocol": latest, "version": protocol_version(latest), "findings": findings,
            "superseded": superseded, "statuses": statuses}
