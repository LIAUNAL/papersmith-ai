"""paper_audit: verbatim `## Disqualifiers` extraction and the account-vs-
draft reconciliation that makes a contract's own prose enforceable rather
than decorative (`contract-audit` spec).

Zero interpretation of a bullet's wording happens in this module — every
bullet the auditor agent (`.claude/agents/contract-auditor.md`) judges is
passed through byte for byte, and this module's own job is the same shape
`paper_bindings.py` already establishes: the auditor's account (one verdict
per bullet) is checked against the contract's real bullets and the real
draft, never trusted about either.

Public surface:

    extract_disqualifiers(body_text, source_name=...) -> list[str]  (raises DISQUALIFIERS_ABSENT)
    bullet_blocks(bullet) -> tuple[str, ...] | None
    bullet_rule(bullet) -> str
    applicable_disqualifiers(bullets, block_id, declared_blocks=()) -> list[str]
    unresolved_markers(bullets, declared_blocks) -> list[str]
    reconcile_verdicts(bullets, verdict_entries, draft_latex, excluded=..., block_id=...) -> list[dict]  (raises VERDICT_MISSING, VERDICT_BULLET_UNKNOWN)
    compute_outcome(reconciled) -> dict
    cross_check_measurable(reconciled, draft_latex) -> list[dict]
    audit(contract_body, draft_latex, verdict_entries, source_name=..., block_id=..., declared_blocks=...) -> dict

Block markers (`odd/tasks/efficiency-stage-b.md`, S7): a bullet may open
with `[block: <id>]` or `[block: <id>, <id>, ...]`, naming the block(s) of
its own contract the rule is judged on. The marker is part of the bullet's
verbatim text -- extraction never strips it, the judge sees it and quotes
it back unchanged. An unmarked bullet applies to every block of the
section, so a contract with no marker is judged exactly as before. A marker
that does not parse, or that names any id the contract does not declare,
never removes a rule: that bullet applies to every block.
    count_table_works(latex) -> int | None
    row_count_finding(latex) -> str | None
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

_DISQUALIFIERS_HEADING = "## Disqualifiers"


def extract_disqualifiers(body_text: str, *, source_name: str = "<contract>") -> list[str]:
    """Every bullet under the first `## Disqualifiers` heading, literal text,
    stripped of its leading `- ` marker, with any wrapped continuation
    lines rejoined onto it separated by a single space — never
    paraphrased, never special-cased (`contract-audit` spec, `Requirement:
    Verbatim Disqualifier Extraction`: "the exact bullet text is what the
    audit evaluates against, byte for byte"). A bullet is prose that may
    wrap across source lines; stopping at the first line break would hand
    the audit a fragment of the bullet's own text rather than the bullet,
    which can invert a multi-clause rule's meaning. A continuation line is
    any non-empty, indented line that does not itself start a new bullet
    (stripped form beginning `- ` or `* `) — that check is what still lets
    a nested bullet start its own entry instead of being swallowed into the
    one above it. A blank line does not end the list; only a `## ` heading
    does. Refuses `DISQUALIFIERS_ABSENT` naming `source_name` when no such
    heading exists anywhere in `body_text`."""
    lines = body_text.splitlines()
    heading_index = None
    for index, line in enumerate(lines):
        if line.strip() == _DISQUALIFIERS_HEADING:
            heading_index = index
            break
    if heading_index is None:
        raise Refused(
            "DISQUALIFIERS_ABSENT", f"{source_name}: no '## Disqualifiers' heading"
        )
    bullets: list[str] = []
    for line in lines[heading_index + 1:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("- ") or stripped.startswith("* "):
            bullets.append(stripped[2:].strip())
        elif stripped and line != line.lstrip() and bullets:
            bullets[-1] = f"{bullets[-1]} {stripped}"
    return bullets


#: The one marker form: a leading `[block: <id>]`, ids comma-separated, each
#: in the block-id shape class (`references/safety-net.md`), then one space
#: before the rule. Anything else is no marker.
_MARKER_RE = re.compile(r"^\[block: ([A-Za-z0-9._-]+(?:, [A-Za-z0-9._-]+)*)\] (?=\S)")
_MARKER_PREFIX = "[block"


def bullet_blocks(bullet: str) -> tuple[str, ...] | None:
    """The block ids a bullet's leading marker names, in order; `None` for
    an unmarked bullet or one whose marker does not parse."""
    match = _MARKER_RE.match(bullet)
    if match is None:
        return None
    return tuple(match.group(1).split(", "))


def bullet_rule(bullet: str) -> str:
    """The bullet's rule text with a well-formed leading marker dropped.
    For matching a known rule only (`ROW_COUNT_BULLET`); every account and
    report carries the bullet verbatim, marker included."""
    match = _MARKER_RE.match(bullet)
    return bullet[match.end():] if match else bullet


def _bare_block_id(block_id: str) -> str:
    # `write` hands the qualified `<section>.<block>`; a marker names the
    # bare id the contract's own header declares. Section ids carry no dot.
    return block_id.split(".", 1)[1] if "." in block_id else block_id


def _resolved_blocks(bullet: str, declared_blocks) -> tuple[str, ...] | None:
    blocks = bullet_blocks(bullet)
    if blocks is None or not declared_blocks or not set(blocks) <= set(declared_blocks):
        return None
    return blocks


def unresolved_markers(bullets: list[str], declared_blocks) -> list[str]:
    """Bullets that look marked (they open with `[block`, in any case) but
    whose marker does not parse or names a block outside `declared_blocks`.
    Each is judged on every block, never on none."""
    return [
        bullet for bullet in bullets
        if bullet[:len(_MARKER_PREFIX)].lower() == _MARKER_PREFIX
        and _resolved_blocks(bullet, declared_blocks) is None
    ]


def applicable_disqualifiers(bullets: list[str], block_id: str, declared_blocks=()) -> list[str]:
    """The bullets the contract judge rules on for `block_id`, in contract
    order: every unmarked bullet, every bullet whose marker names this
    block, and every bullet whose marker is unresolved against
    `declared_blocks`. With no `declared_blocks` every marker is inert and
    every bullet applies, the behavior of a contract read before markers."""
    bare = _bare_block_id(block_id)
    applicable = []
    for bullet in bullets:
        blocks = _resolved_blocks(bullet, declared_blocks)
        if blocks is None or bare in blocks:
            applicable.append(bullet)
    return applicable


def reconcile_verdicts(
    bullets: list[str], verdict_entries: list[dict], draft_latex: str,
    *, excluded: list[str] = (), block_id: str | None = None,
) -> list[dict]:
    """Checks the auditor's account (`verdict_entries`, each
    `{"bullet": ..., "verdict": "fires"|"clear"|"undecidable", "span":
    ...}`) against `bullets`, the real extraction, in both directions:
    refuses `VERDICT_BULLET_UNKNOWN` naming an entry whose `bullet` text
    matches none of `bullets`; refuses `VERDICT_MISSING` naming a bullet
    with no corresponding entry. `excluded` holds the contract's bullets
    marked for another block: a verdict on one refuses
    `VERDICT_BULLET_UNKNOWN` too, naming `block_id`, so the account covers
    exactly the bullets that apply.

    A `fires` verdict citing no span, or citing a span not byte-present in
    `draft_latex`, downgrades to `undecidable` rather than being trusted
    (`contract-audit` spec, `Requirement: Per-Bullet Verdict With Quoted
    Span`; `design.md`, Decision D8) — the same "checked against the
    artefact, never trusted about it" mechanism `paper_bindings.reconcile`
    already applies to sentences.
    """
    by_bullet = {entry["bullet"]: entry for entry in verdict_entries}
    bullet_set = set(bullets)

    excluded_set = set(excluded)
    for entry in verdict_entries:
        if entry["bullet"] in excluded_set and entry["bullet"] not in bullet_set:
            raise Refused(
                "VERDICT_BULLET_UNKNOWN",
                f"verdict names a bullet marked for another block, which does not apply to "
                f"{block_id}: {entry['bullet']!r}",
            )
        if entry["bullet"] not in bullet_set:
            raise Refused(
                "VERDICT_BULLET_UNKNOWN",
                f"verdict names a bullet not in the contract: {entry['bullet']!r}",
            )

    results: list[dict] = []
    for bullet in bullets:
        entry = by_bullet.get(bullet)
        if entry is None:
            raise Refused("VERDICT_MISSING", f"no verdict for bullet: {bullet!r}")
        verdict = entry["verdict"]
        span = entry.get("span") or ""
        if verdict == "fires" and (not span or span not in draft_latex):
            verdict = "undecidable"
            span = ""
        results.append({"bullet": bullet, "verdict": verdict, "span": span if verdict == "fires" else ""})
    return results


def compute_outcome(reconciled: list[dict]) -> dict:
    """`contract-audit` spec, `Requirement: Undecidable Is Reported, Not
    Blocking On Its Own`: the outcome is decided solely by `any(fires)`. An
    all-`clear`/`undecidable` audit does not block; one `fires` blocks
    regardless of how many `undecidable` verdicts sit beside it."""
    fired = [entry for entry in reconciled if entry["verdict"] == "fires"]
    return {"blocks": bool(fired), "verdicts": reconciled, "fired": fired}


def audit(
    contract_body: str, draft_latex: str, verdict_entries: list[dict], *, source_name: str = "<contract>",
    block_id: str | None = None, declared_blocks=(),
) -> dict:
    """The whole-file entry point: extract, select the bullets that apply
    to `block_id` (every bullet when it is `None`), reconcile, decide."""
    bullets = extract_disqualifiers(contract_body, source_name=source_name)
    applicable = bullets if block_id is None else applicable_disqualifiers(bullets, block_id, declared_blocks)
    excluded = [bullet for bullet in bullets if bullet not in applicable]
    reconciled = reconcile_verdicts(
        applicable, verdict_entries, draft_latex, excluded=excluded, block_id=block_id,
    )
    return compute_outcome(cross_check_measurable(reconciled, draft_latex))


def cross_check_measurable(reconciled: list[dict], draft_latex: str) -> list[dict]:
    """Bullets whose breach a cheap deterministic measure can see are not
    taken on the auditor's word: a `clear` verdict the measure contradicts
    becomes `undecidable` carrying the measured finding under
    `deterministic`. It never turns a verdict into `fires` -- the measure
    reports, the auditor's quoted span still decides blocking (`Requirement:
    Undecidable Is Reported, Not Blocking On Its Own`). Today the only such
    bullet is contract 05's synthesis-table row count (spec S1 of
    `odd/tasks/manuscript-polish-0-54.md`)."""
    checked: list[dict] = []
    for entry in reconciled:
        if bullet_rule(entry["bullet"]) == ROW_COUNT_BULLET and entry["verdict"] == "clear":
            finding = row_count_finding(draft_latex)
            if finding is not None:
                entry = {**entry, "verdict": "undecidable", "deterministic": finding}
        checked.append(entry)
    return checked


# --- Section 05 synthesis table: deterministic work count -------------------
# Spec S1 of `odd/tasks/manuscript-polish-0-54.md`: contract 05 requires the
# synthesis table to place 7 to 12 works, the proposal's row not counted.
# Counting rule, per `tabular`/`tabular*`/`tabularx` environment in the draft:
# rows split on `\\`; rule commands dropped; rows before the first
# `\midrule` are the header; a row made of a single `\multicolumn` is a
# family group label; the last remaining row is the proposal. Works are the
# remaining rows, summed over every table in the draft.

MIN_WORKS = 7
MAX_WORKS = 12

# Verbatim bullet in `sections/05-related-work.md` `## Disqualifiers`.
ROW_COUNT_BULLET = (
    "Fewer than 7 or more than 12 works in the synthesis table, the proposal's row not counted."
)

_TABLE_RE = re.compile(
    r"\\begin\{(tabularx|tabular\*|tabular)\}(.*?)\\end\{\1\}", re.DOTALL,
)
_RULE_RE = re.compile(
    r"\\(?:toprule|bottomrule|hline|addlinespace|midrule)(?:\[[^\]]*\])?"
    r"|\\cmidrule(?:\([^)]*\))?(?:\[[^\]]*\])?\{[^}]*\}"
)
_GROUP_ROW_RE = re.compile(r"^\\multicolumn\{\d+\}\{[^}]*\}\{.*\}$", re.DOTALL)


def _table_works(body: str) -> int:
    if "\\midrule" in body:
        body = body.split("\\midrule", 1)[1]
    else:
        # No header rule: the first row is the header.
        parts = body.split("\\\\", 1)
        body = parts[1] if len(parts) == 2 else ""
    rows = []
    for raw in body.split("\\\\"):
        row = _RULE_RE.sub("", raw).strip()
        if not row or _GROUP_ROW_RE.match(row):
            continue
        rows.append(row)
    return max(len(rows) - 1, 0)  # the last row is the proposal


def count_table_works(latex: str) -> int | None:
    """Works placed by every table in `latex`; `None` when it has no table."""
    tables = _TABLE_RE.findall(latex)
    if not tables:
        return None
    return sum(_table_works(body) for _, body in tables)


def row_count_finding(latex: str) -> str | None:
    """A one-line finding when the measured count is outside 7..12, else `None`."""
    works = count_table_works(latex)
    if works is None or MIN_WORKS <= works <= MAX_WORKS:
        return None
    return (
        f"synthesis table places {works} works, outside {MIN_WORKS}-{MAX_WORKS} "
        "(proposal row not counted)"
    )
