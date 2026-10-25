#!/usr/bin/env python3
"""The mechanism behind `skill-audit`: derive both halves of a closed set.

Stdlib only, no venv, no network except through `structure`'s opt-in `driver`
step. Every subcommand writes JSON to stdout with
sorted keys and returns an integer status, so a caller can hold the output to a
schema instead of to a paragraph.

Two exit codes carry two different meanings and are never merged. `0` means the
tool looked and is reporting what it saw, findings included. `2` means it could
not look: the probe would not run, the recipe was unreadable, or the extraction
matched nothing. An empty result and an inability to produce a result are not
the same claim, and a tool that spells them the same way turns a broken probe
into a page of confident findings.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from ast import walk as ast_walk
from fnmatch import fnmatch
from pathlib import Path

#: Cardinal words a document might use to state the size of a list. Digits are
#: matched separately. Nothing above twelve is included: past that, prose
#: overwhelmingly switches to digits, and admitting the long tail buys noise.
CARDINALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

#: A numeral wearing one of these is not claiming to size anything, and a check
#: that fired on it would be noise. Noise gets exempted until the check means
#: nothing, so the exemption is declared here once rather than grown case by
#: case. Measured need: a neighbouring engine's own header says "~63 TS files"
#: and "roughly 0.72s" two lines apart.
HEDGES = ("~", "about", "approximately", "around", "roughly", "nearly",
          "almost", "at least", "at most", "up to", "over", "under",
          "more than", "fewer than", "some", "several", "or so")

_CARDINAL_RE = re.compile(
    r"\b(" + "|".join(CARDINALS) + r"|\d{1,3})\b", re.IGNORECASE)


class Unprobeable(Exception):
    """The tool could not look. Distinct from having looked and found nothing.

    Raised rather than returned, and mapped to exit `2` at the boundary, so that
    no code path can accidentally hand an empty set to a comparison as though it
    were an observation.
    """


# --------------------------------------------------------------------------
# Documented side. Nothing in this section may reference the producer: not the
# probe, not `subprocess`, not a constant borrowed from either. The soundness
# gate in `tests/test_skill_audit.py` parses these functions' syntax trees and
# fails on any such reference, because "it structurally cannot" is a claim and
# claims are what this skill is for.
# --------------------------------------------------------------------------

def markdown_table_rows(text, header):
    """Every row of every table introduced by exactly this header line.

    One shape, read one way, wherever doctrine states a placement. Prose cannot
    be held to code — SKILL.md is what an agent reads, not a rendered artifact —
    so the instruction has to be written in something a test can parse.
    """
    lines = [line.strip() for line in text.splitlines()]
    tables = []
    for index, line in enumerate(lines):
        if line != header:
            continue
        rows = []
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            rows.append([cell.strip() for cell in row.strip("|").split("|")])
        tables.append(rows)
    return tables


def doctrine_side(text, site):
    """The documented half of a surface, parsed out of one table.

    `site` is a recipe entry, never a roster. It names the table's header line
    and the column to read, and it may claim the table is a *complement* set —
    a table of the members deliberately outside the main flow. Such a claim is
    honoured only if the recipe also quotes the heading verbatim and that
    heading is found in the text, so the editorial judgement is falsifiable by
    renaming the heading and watching the claim stop being honoured.

    Returns `(members, status)`. A site with no parseable table yields no
    members and `no-closed-roster`, which is a first-class result rather than an
    error: the finding is that this subject states its set in prose, and prose
    is what condition 5 forbids the documented side from being read out of.

    A complement is not a closed roster either. It is a deliberate subset, so it
    can support the `phantom` direction — a documented member with nothing
    behind it — but never the `unregistered` direction, where every member the
    complement omits on purpose would be reported as missing documentation.
    """
    header = site.get("table")
    if not header:
        return [], "no-closed-roster"

    tables = markdown_table_rows(text, header)
    rows = [row for table in tables for row in table]
    if not rows:
        return [], "no-closed-roster"

    scope = site.get("scope")
    if scope:
        heading = site.get("headingVerbatim")
        if not heading:
            return [], "scope-claimed-without-heading"
        if heading not in text.splitlines():
            return [], "heading-not-found"

    column = site.get("column", 0)
    members = []
    for row in rows:
        if column >= len(row):
            continue
        members.append(row[column].strip().strip("`").strip())
    return [member for member in members if member], scope or "closed"


def restatement_of(text, members, quorum):
    """Where a set is written out by hand, and which of its members are there.

    A place that mentions one member is not restating the set; a place carrying
    at least `quorum` of them is. The quorum comes from the recipe so the
    domain is declared before the search runs rather than tuned afterwards to
    make an inconvenient result go away.

    Returns `(matched, line)` — the members found and the first line any of them
    appears on, so the report can name the restatement at `file:line` instead of
    gesturing at a file.
    """
    lines = text.splitlines()
    matched = []
    first = 0
    for member in members:
        for number, line in enumerate(lines, start=1):
            if member in line:
                matched.append(member)
                if first == 0 or number < first:
                    first = number
                break
    if len(matched) < quorum:
        return [], 0
    return sorted(matched), first


def bullet_run_length(lines, start):
    """How many top-level bullets the list beginning at `lines[start]` holds.

    A bullet's continuation lines are indented and its items may be separated by
    blank lines, so the run ends at the first non-blank line that is neither a
    top-level bullet nor indented. Counted rather than assumed: the enumeration
    a reader believes follows a numeral is frequently longer than the reader
    thinks, because a long indented item hides the next bullet below the fold.
    """
    count = 0
    index = start
    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            index += 1
            continue
        if line.startswith("- ") or line.startswith("* "):
            count += 1
            index += 1
            continue
        if line[:1] in (" ", "\t"):
            index += 1
            continue
        break
    return count


def table_run_length(lines, start):
    """How many data rows the table beginning at `lines[start]` holds."""
    index = start + 2  # header line, then the separator
    count = 0
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        count += 1
        index += 1
    return count if count else 0


def enumeration_after(lines, index):
    """The enumeration immediately below `lines[index]`, if there is one.

    "Immediately" means at most one blank line away. A numeral separated from a
    list by a paragraph is not claiming to size that list, and treating it as
    though it were is how a check earns its first exemption.
    """
    probe = index + 1
    blanks = 0
    while probe < len(lines) and lines[probe].strip() == "":
        blanks += 1
        if blanks > 1:
            return None
        probe += 1
    if probe >= len(lines):
        return None
    line = lines[probe]
    if line.startswith("- ") or line.startswith("* "):
        return probe, bullet_run_length(lines, probe)
    if line.lstrip().startswith("|"):
        return probe, table_run_length(lines, probe)
    return None


def is_size_claim(stripped, end):
    """Whether the numeral ending at `end` is sizing something, or just counting.

    A numeral sizes an enumeration in one of two positions, and in no others:
    ahead of the plural noun it quantifies ("Three modules ...:"), or postposed
    at the end of the lead-in ("the modules are these three:").

    Everything else is a numeral doing a different job, and the two shapes that
    matter here were both found in a real document rather than imagined. An
    ordinal step marker sizes nothing -- `### 2. Build one X per Y` is the
    second step, not two of anything. A distributive sizes nothing either --
    "one X per Y" is a rate, and the singular noun is what says so.

    This is a narrowing of the rule, not an exemption from it. An exemption
    names the case that was inconvenient; this names the grammar a size claim
    has, so a new document that makes the claim is caught without being
    listed here first.
    """
    tail = stripped[end:]
    if tail.strip().rstrip("*_`") in ("", ":"):
        return True
    word = re.match(r"[\s*_]*([A-Za-z`'\"]+)", tail)
    if not word:
        return False
    noun = word.group(1).strip("`'\"")
    return len(noun) > 2 and noun.lower().endswith("s")


def numeral_mismatches(path):
    """Unhedged numerals that state a size the enumeration beneath them denies.

    Only two positions are read: a line that ends with a colon, which is prose
    introducing the list below it, and a markdown heading. Both are places a
    numeral is making a claim about what follows rather than mentioning a
    quantity in passing. Everything else is left alone deliberately — a rule
    that fires on every number in a document is a rule nobody keeps.

    Each mismatch names the numeral's line and the enumeration's line, because a
    finding that names one half is a candidate.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    findings = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_heading = stripped.startswith("#")
        if not is_heading and not stripped.endswith(":"):
            continue
        if stripped.startswith("|") or stripped.startswith("- "):
            continue
        for match in _CARDINAL_RE.finditer(stripped):
            token = match.group(1)
            before = stripped[:match.start()].lower()
            if any(hedge in before[-24:] for hedge in HEDGES):
                continue
            if not is_size_claim(stripped, match.end()):
                continue
            value = CARDINALS.get(token.lower())
            if value is None:
                value = int(token)
            found = enumeration_after(lines, index)
            if found is None:
                continue
            enumeration_line, counted = found
            if counted and counted != value:
                findings.append({
                    "counted": counted,
                    "enumerationLine": enumeration_line + 1,
                    "numeral": token,
                    "numeralLine": index + 1,
                    "path": str(path),
                    "stated": value,
                })
    return findings


# --------------------------------------------------------------------------
# Code side. This is where the producer lives, kept below a clear line so the
# syntax-tree gate above has something unambiguous to guard.
# --------------------------------------------------------------------------

def _reported_interpreter_version(path):
    """The `(major, minor, micro)` a candidate interpreter reports for its
    own `--version`, or `None` if it cannot be run at all or does not
    answer in the shape CPython and its distributions use."""
    try:
        completed = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(part) for part in match.groups()) if match else None


def resolve_min_version_interpreter(name, min_version):
    """An absolute path to a `name`-family interpreter meeting `min_version`
    (e.g. `"3.10"`), found on this process's own `PATH` -- or `(None,
    checked)` if none does, where `checked` maps every path this looked at
    to the version it reported (`None` where even `--version` could not be
    read).

    `name` is checked first, under its own declared spelling, so a `PATH`
    where it already satisfies `min_version` changes nothing. Failing that,
    this looks for its version-suffixed siblings (`python3.10`,
    `python3.11`, ...) on the same `PATH`: a recipe naming a bare `python3`
    cannot know in advance which minor release a given machine parks under
    that name, only that its own subject needs at least `min_version` to be
    importable at all. This is deliberately unrelated to `run_exits`'s own
    `interpreterAllowlist`, which admits an act's `argv[0]` for path
    resolution and never resolves a version -- reusing it here would gate
    the wrong thing.
    """
    required = tuple(int(part) for part in min_version.split("."))
    base = "python3" if name in ("python", "python3") else name
    candidates = [name] + [f"{base}.{minor}" for minor in range(9, 21)]
    checked = {}
    for candidate in dict.fromkeys(candidates):
        resolved = shutil.which(candidate)
        if not resolved or resolved in checked:
            continue
        checked[resolved] = _reported_interpreter_version(resolved)
    satisfying = sorted(
        (version, path) for path, version in checked.items()
        if version and version >= required)
    return (satisfying[0][1], checked) if satisfying else (None, checked)


def _interpreter_gap_message(name, min_version, checked):
    """A refusal that names the cause: what was required, and exactly what
    was found instead -- never a bare `unprobeable` standing in for it."""
    if not checked:
        return (
            f"this recipe's argv[0] {name!r} needs Python >= {min_version} "
            "to import the subject at all, and no interpreter answering "
            "that name (or a versioned sibling) could be found on PATH")
    found = ", ".join(
        f"{path} -> {'.'.join(map(str, version)) if version else 'unreadable'}"
        for path, version in sorted(checked.items()))
    return (
        f"this recipe's argv[0] {name!r} needs Python >= {min_version} to "
        f"import the subject at all; every interpreter found on PATH falls "
        f"short of it ({found})")


def probe_code_side(recipe, subject, timeout=30):
    """The running subject's own roster, taken out of its own refusal.

    The subject is driven as a real process with a nonce it cannot accept, and
    the accepted set is read from the message it produces in its own words. No
    source of the subject is parsed, so there is no second parser to drift from
    the first, and the subject may be written in any language.

    `stream` and `exit` come from the recipe rather than being fixed here,
    because the two probes genuinely differ: a Node host writes its refusal as
    JSON to stdout and exits `1`, while `argparse` writes `invalid choice` to
    stderr and exits `2`. One hardcoded contract would fit neither.

    A recipe may also declare `minInterpreterVersion` when its subject
    cannot even be imported under an older release sharing its argv[0]'s
    name (a bare `python3` may resolve to Python 3.9 on one machine and
    3.12 on another): a bare `argv[0]` is then resolved to whichever
    `PATH` candidate actually satisfies it, or this raises naming both the
    requirement and every version this machine offered instead -- so the
    subject's own refusal is never confused with an inability to reach it.
    """
    argv = list(recipe["argv"])
    if not argv or not all(isinstance(part, str) for part in argv):
        raise Unprobeable("the recipe's argv must be a list of strings")

    min_version = recipe.get("minInterpreterVersion")
    if min_version and "/" not in argv[0]:
        resolved0, checked = resolve_min_version_interpreter(argv[0], min_version)
        if resolved0 is None:
            raise Unprobeable(
                _interpreter_gap_message(argv[0], min_version, checked))
        argv[0] = resolved0

    subject = Path(subject).resolve()
    where = subject
    if recipe.get("cwd"):
        where = (subject / recipe["cwd"]).resolve()
        if subject != where and subject not in where.parents:
            raise Unprobeable(
                f"the recipe's cwd {recipe['cwd']!r} resolves outside --subject")
    if not where.is_dir():
        raise Unprobeable(f"the recipe's cwd does not exist: {where}")

    try:
        # `shell=False` and argv as a list, never a string: a recipe carrying a
        # semicolon must reach the subject as one literal argument, not as two
        # commands. There is no shell in this path to interpret it.
        completed = subprocess.run(
            argv, cwd=str(where), shell=False, env=probe_child_env(),
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(f"the recipe's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"the subject did not answer within {timeout}s; a probe that hangs "
            "is an inability to look, never an empty roster")

    expected = recipe.get("exit", "any")
    if expected != "any" and completed.returncode != expected:
        raise Unprobeable(
            f"the subject exited {completed.returncode}, not the {expected} the "
            "recipe expects; the refusal path was probably not reached")

    stream = recipe.get("stream", "stdout")
    text = completed.stdout if stream == "stdout" else completed.stderr
    pattern = re.compile(recipe["extract"])
    match = pattern.search(text)
    if match is None:
        raise Unprobeable(
            "the recipe's extract matched nothing in the subject's "
            f"{stream}; returning an empty roster here would make every "
            f"documented row a phantom. Saw: {text.strip()[:400]!r}")

    raw = match.group("roster")
    members = [part.strip().strip("'\"`") for part in raw.split(recipe.get("split", ", "))]
    members = [member for member in members if member]
    if not members:
        raise Unprobeable(
            "the extraction matched but yielded no members, which is the same "
            "inability to look wearing a different shape")
    return members


#: R3's whole verdict vocabulary (`spec.md`, "Renaming is not generalising"):
#: a two-value closed roster, never a third value meaning "the content is
#: specific" -- that would be a reading, not a measurement, and this module
#: refuses to guess it. `IdentityMeasuredCardinalityTests` holds this to
#: exactly these two members, the `FOUND_BY_VALUES`/`REMEDY_VALUES` idiom.
IDENTITY_MEASURED = ("identity-measured", "not-determined")

#: The rename probe's own neutral substitute. No real guarded vocabulary or
#: `FORGE_LEXICON` entry could collide with this, so driving a guard with it
#: tests only whether the guard's verdict moves when the identifier moves,
#: never a real candidate's own meaning.
GUARD_NEUTRAL_TOKEN = "zzz_guardreach_neutral_probe_zzz"


def identifier_variants(member):
    """`member`'s identifier-boundary variants: plural, underscore-joined,
    case-joined -- the three shapes a word-boundary matcher measurably
    failed to reach (`spec.md`, R2: a singular guarded term's matcher did
    not reach its own plural, and `_` is a word character in that pattern
    language, so no word-boundary rule could ever reach an identifier
    joining the term to another word). Naive and deterministic on purpose:
    this derives what to *try*, never what the guard is supposed to catch,
    and it is never a claim about correct English pluralisation.
    """
    return [f"{member}s", f"{member}_other", f"{member}Other"]


#: `guardReach.drive.argv`'s own one-token grammar -- literal `{candidate}`,
#: substituted by `drive_guard_candidate` alone. Compiled once, `re.escape`d
#: since the token itself carries regex metacharacters.
_CANDIDATE_TOKEN_RE = re.compile(re.escape("{candidate}"))


def drive_guard_candidate(drive, candidate, subject, timeout):
    """Whether one candidate string is reached (refused) by the subject's
    own guard, driven for real with `{candidate}` substituted into the
    recipe's declared `guardReach.drive.argv`.

    Never a recipe-declared matcher pattern compiled with `re` here: that
    would be a hand-copy of the subject's own source living beside it, free
    to drift -- the exact class this skill exists to find.

    Substitutes via `re.sub`, never `str.replace`: `NothingWasRepairedTests`'s
    AST sweep scans every function for write verbs by name, and `.replace`
    shares its spelling with `Path.replace` -- the same false positive
    `strip_comparison_operators` already routes around with `re.sub`.
    """
    argv = [_CANDIDATE_TOKEN_RE.sub(lambda match: candidate, part)
           for part in drive["argv"]]
    where = subject
    if drive.get("cwd"):
        where = (subject / drive["cwd"]).resolve()
        if subject != where and subject not in where.parents:
            raise Unprobeable(
                f"guardReach.drive's cwd {drive['cwd']!r} resolves outside "
                "--subject")
    try:
        completed = subprocess.run(
            argv, cwd=str(where), shell=False, env=probe_child_env(),
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(
            f"guardReach.drive's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"guardReach.drive did not answer within {timeout}s; a probe "
            "that hangs is an inability to look, never a clean verdict")
    stream = drive.get("stream", "stdout")
    text = completed.stdout if stream == "stdout" else completed.stderr
    return re.search(drive["refusal"], text) is not None


def guard_reach_findings(recipe, subject, timeout):
    """R2 + R3 (`spec.md`): for every member of a driven guarded vocabulary,
    measure whether the guard reaches each identifier-boundary variant, and
    -- reusing the exact same drive, one further transformation -- whether
    the guard's verdict is measuring identity or content.

    `guardReach` is optional, exactly like `doctrineSites` and
    `restatementSearch`: a recipe that never declares it changes nothing
    about `roster`'s existing behaviour. Returns `(notes, payload)`;
    `payload` is `None` when the block is absent, or when the subject
    exposes no driveable guard for it to measure -- reported as
    `kind=no-driveable-guard`, the `no-closed-roster` idiom reused verbatim,
    never a silently empty roster.

    The control gate runs first, per member: a guard that never refuses its
    own bare guarded member at all is `kind=guard-never-fires`, reported
    once, never as one `guard-unreachable-variant` finding per identifier
    variant -- eleven findings would misread a broken probe as eleven
    separate defects.
    """
    guard_reach = recipe.get("guardReach")
    if not guard_reach:
        return [], None

    producer = guard_reach.get("producer")
    drive = guard_reach.get("drive")
    if not producer or not drive:
        return [note(
            "no-driveable-guard",
            "the recipe's guardReach block declares no producer/drive "
            "pair, so no guarded vocabulary's reach can be measured for "
            "this subject",
            recipe.get("surface", ""),
            "guardReach.producer/guardReach.drive")], None

    try:
        members = sorted(set(probe_code_side(producer, subject, timeout)))
    except Unprobeable as error:
        return [note(
            "no-driveable-guard",
            "guardReach.producer could not derive a guarded vocabulary for "
            f"this subject: {error}",
            recipe.get("surface", ""), str(producer.get("argv", [])))], None

    notes = []
    member_reports = []
    for member in members:
        control_reached = drive_guard_candidate(drive, member, subject, timeout)
        if not control_reached:
            notes.append(note(
                "guard-never-fires",
                f"the guard never refused its own guarded member {member!r} "
                "at all; reporting each of its identifier variants "
                "unreachable would read as eleven findings instead of one "
                "broken probe",
                member, drive["argv"]))
            member_reports.append({
                "control": "not-reached", "identity": None, "member": member,
                "unreachable": [], "variants": {}})
            continue

        variants = {}
        unreachable = []
        for variant in identifier_variants(member):
            reached = drive_guard_candidate(drive, variant, subject, timeout)
            variants[variant] = "reached" if reached else "not-reached"
            if not reached:
                unreachable.append(variant)
                notes.append(note(
                    "guard-unreachable-variant",
                    f"the guard reaches {member!r} but not its identifier-"
                    f"boundary variant {variant!r}; a member of the "
                    "guarded set is unreachable through its own matcher",
                    member, drive["argv"]))

        neutral_reached = drive_guard_candidate(
            drive, GUARD_NEUTRAL_TOKEN, subject, timeout)
        verdict = "not-determined" if neutral_reached else "identity-measured"
        member_reports.append({
            "control": "reached",
            "identity": {"limit": READING_DIFF_LIMIT, "verdict": verdict},
            "member": member, "unreachable": unreachable,
            "variants": variants})

    return notes, {"members": member_reports}


def tree_digest(root, exclude=()):
    """A sorted `path -> sha256` map over every file under `root`.

    The sole helper in this module allowed to walk a filesystem tree.
    `structure`'s on-disk and from-zero sides are this function's output, and
    so is every box's before/after proof of containment. `SingleWalkTests` in
    `tests/test_skill_audit.py` reads this file's own syntax tree and asserts
    that `rglob`, `walk`, `iterdir`, `scandir`, and `glob` occur nowhere else
    in `audit_cli.py`, so a second walk added later -- by this module or by
    the follow-up change's `manifest` -- turns that lock red rather than
    quietly drifting from this one.

    Paths are POSIX-relative to `root`, files only: a directory holds no
    content of its own to hash, and comparing directory sets would let an
    empty, newly created folder pass as agreement. `exclude` is a tuple of
    `fnmatch` patterns matched against the relative path; there is no
    built-in default, because a default would be a hidden narrowing of the
    domain a recipe declares.
    """
    digest = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch(relative, pattern) for pattern in exclude):
            continue
        digest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def frozen_digest(root, exclude=()):
    """One stable `sha256` summary over `tree_digest`'s own sorted map.

    Calls `tree_digest` rather than walking a second time -- `SingleWalkTests`
    holds every walk name to inside `tree_digest` alone, so a second walk
    here would turn that lock red rather than quietly drift beside it. The
    digest embeds one `path sha256` line per file, sorted by path, so two
    runs over the same tree with the same `exclude` always agree, and a
    file added, removed, or changed always disagrees.

    A summary hash, not the per-file map itself: a report cannot embed
    hundreds of lines of per-file hashes and stay reviewable, so the report
    carries this one digest plus the `exclude` list needed to re-derive it --
    the recipe for the hash, not the hash's own working.
    """
    files = tree_digest(root, exclude)
    lines = "\n".join(f"{path} {files[path]}" for path in sorted(files))
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


#: Only these three tokens interpolate inside a `structure` recipe's
#: `fromZero.steps`, each resolved absolutely by the tool rather than taken
#: from the recipe string. Any other `{...}` is refused rather than passed
#: through as a literal brace, so a recipe cannot quietly widen what a step
#: may reach.
STRUCTURE_TOKENS = {"repoRoot", "subject", "box"}

_TOKEN_RE = re.compile(r"\{([a-zA-Z]+)\}")


def interpolate_token(text, repo, subject, box):
    """Substitute `{repoRoot}`, `{subject}`, and `{box}` inside one argv part.

    Every other `{token}` shape is a recipe naming something this tool never
    declared, and is refused before a process is ever started.
    """
    def replace(match):
        token = match.group(1)
        if token not in STRUCTURE_TOKENS:
            raise Unprobeable(
                f"the recipe's step names an unknown token {{{token}}}; only "
                f"{sorted(STRUCTURE_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "subject": str(subject),
                "box": str(box)}[token]
    return _TOKEN_RE.sub(replace, text)


#: `{candidate}` is a fourth token, valid only inside `candidateGates.argv`.
#: `STRUCTURE_TOKENS` is untouched, so a plain `walkthrough` step's own argv
#: still resolves through `interpolate_token` alone and cannot reach for a
#: candidate it never declared.
GATE_TOKENS = STRUCTURE_TOKENS | {"candidate"}


def interpolate_gate_token(text, repo, subject, box, candidate):
    """Substitute `{repoRoot}`, `{subject}`, `{box}`, and `{candidate}`
    inside one `candidateGates.argv` part. Mirrors `interpolate_token`,
    scoped to the one recipe block where a fourth token is legal.
    """
    def replace(match):
        token = match.group(1)
        if token not in GATE_TOKENS:
            raise Unprobeable(
                f"the recipe's candidateGates.argv names an unknown token "
                f"{{{token}}}; only {sorted(GATE_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "subject": str(subject),
                "box": str(box), "candidate": candidate}[token]
    return _TOKEN_RE.sub(replace, text)


#: Only `{repoRoot}` and `{box}` interpolate inside a `fromZero.steps`
#: entry -- never `{subject}`. The from-zero side is meant to build a
#: comparison *target*, never to reference the producer it will be compared
#: against; refusing the token at the interpolation layer is the structural
#: half of that soundness condition. `assert_no_subject_reference` below is
#: the other half, for a recipe that embeds the subject's path directly
#: rather than through the token -- the exact shape of the tar recipe this
#: change replaces (`git archive HEAD:skills/skill-audit`, no
#: `{subject}` token in sight).
FROM_ZERO_TOKENS = STRUCTURE_TOKENS - {"subject"}

#: The step-kind vocabulary a `fromZero.steps` dict element may declare. A
#: bare list stays kind `exec`, run exactly as before -- no existing recipe
#: or fixture changes shape. `driver` is the one new kind: it additionally
#: resolves `cwd` under the box, constructs an environment from declared
#: names, and proves `argv[0]`'s real path is external. An unknown `kind`
#: is `Unprobeable`, the same treatment `interpolate_token` already gives
#: an unknown `{token}`.
BOX_STEP_KINDS = ("exec", "driver")

#: Environment variable *names* a `driver` step may ask to inherit from the
#: parent process. Names only: the child's environment is constructed from
#: this allowlist, never copied from `os.environ` wholesale, and only the
#: names travel into the report -- values never do.
#:
#: `USER` joined this list under W4, measured rather than guessed: isolated
#: with `env -i`, `HOME PATH LANG TMPDIR` alone answers an authenticated
#: driver CLI with "Not logged in - Please run /login" -- a refusal naming
#: the wrong cause, because the driver cannot reach the OS keychain without
#: knowing who is asking. Adding `SHELL` or `LOGNAME` does not change the
#: refusal; adding `USER` does. `USER` is a username, not a credential; this
#: allowlist exists to keep a driver from inheriting the whole environment,
#: never to conceal identity. The list stays hand-written on purpose --
#: deriving it from the recipe would let the recipe grant itself anything,
#: and a denylist pattern (`*KEY*`, `*SECRET*`) fails open on the first
#: credential whose name matches neither pattern.
DRIVER_ENV_ALLOWLIST = ("HOME", "LANG", "LC_ALL", "PATH", "TERM", "TMPDIR",
                        "USER")


def probe_child_env():
    """The environment a PROBED subject is driven under: `DRIVER_ENV_ALLOWLIST`
    and nothing else.

    Same allowlist as `constructed_child_env` below, same stated reason -- to
    keep a child from inheriting the whole environment. It was applied to
    driven steps and not to the two probe paths, which ran with no `env=` at
    all. That is where it mattered most: an ambient variable deciding which
    domain a shared engine serves made the auditor drive the SIBLING and report
    its roster under this subject's name. Measured: 21 accepted operations with
    a clean environment, 20 with the sibling's profile inherited, because one
    verb is registered only where a second document exists.

    No `names` parameter, unlike its sibling: a probe drives the subject as an
    ordinary process, and there is no recipe field for it to ask for more. An
    audit whose subject is chosen by ambient state is not deriving from the
    subject.

    Delegates rather than repeating the comprehension, because
    `ChildEnvConstructionSweepTests` holds `constructed_child_env` as the one
    place a child environment is built -- and it caught this function's first
    draft doing exactly that.
    """
    env, _missing = constructed_child_env(
        DRIVER_ENV_ALLOWLIST, "a probed subject")
    return env


def constructed_child_env(names, label, hint=""):
    """The only place a driver-kind child environment is built, for both
    `run_box_step` and `run_sensitivity_drive`.

    `names` intersected with `DRIVER_ENV_ALLOWLIST` decides what the child
    inherits by *name*; an unknown name is refused `Unprobeable` naming
    `label` and `hint`, so each site keeps its own distinct refusal wording
    while sharing the one comparison against the allowlist.

    `PYTHONDONTWRITEBYTECODE` is then injected **unconditionally** --
    never inherited from the parent, and never satisfiable by declaring it
    in `names`, because it stays out of `DRIVER_ENV_ALLOWLIST` on purpose.
    A same-size mutation to the guarded source must never be able to
    execute a stale `.pyc` at either site; conditioning the purge on the
    parent's own environment or on a recipe's declaration would reopen
    exactly that hole.

    Returns `(env, missing)`: `missing` is `names` filtered to those absent
    from the parent process, sorted -- `run_box_step` transcribes it into
    `envMissing`; `run_sensitivity_drive` has never had a use for it and
    discards it.
    """
    unknown = sorted(set(names) - set(DRIVER_ENV_ALLOWLIST))
    if unknown:
        raise Unprobeable(
            f"{label} names env {unknown}, outside "
            f"{sorted(DRIVER_ENV_ALLOWLIST)}{hint}")
    missing = sorted(name for name in names if name not in os.environ)
    env = {name: os.environ[name] for name in names if name in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env, missing


#: The directory namespace the ignorance control gate seeds a from-zero box
#: with, before trusting that box was ever empty. Absurd and namespaced so
#: it can never collide with a real driver's own output.
IGNORANCE_CONTROL_DIR = "__audit_ignorance_control__"


def interpolate_from_zero_token(text, repo, box):
    """Substitute `{repoRoot}` and `{box}` inside one `fromZero.steps` part.

    Never `{subject}`: the from-zero side may not reference the producer it
    exists to be compared against, so that token is refused here
    structurally rather than by convention -- the same discipline
    `interpolate_token` already gives a token it never declared.
    """
    def replace(match):
        token = match.group(1)
        if token == "subject":
            raise Unprobeable(
                "kind=subject-reference: a fromZero step's argv names "
                "{subject}; the from-zero side may never reference the "
                "producer it exists to be compared against")
        if token not in FROM_ZERO_TOKENS:
            raise Unprobeable(
                f"the recipe's step names an unknown token {{{token}}}; only "
                f"{sorted(FROM_ZERO_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "box": str(box)}[token]
    return _TOKEN_RE.sub(replace, text)


def assert_no_subject_reference(text, subject, repo):
    """Refuse an interpolated `fromZero` part that names the subject by its
    absolute or repo-relative path, even when no `{subject}` token was used
    to get there.

    This is what actually catches the tar recipe's own defect: its argv
    never used `{subject}`, it spelled the path out by hand
    (`HEAD:skills/skill-audit`). Refusing the token alone would
    have missed it.
    """
    subject_abs = str(subject)
    try:
        subject_rel = subject.relative_to(repo).as_posix()
    except ValueError:
        subject_rel = None
    if subject_abs in text or (subject_rel and subject_rel in text):
        raise Unprobeable(
            "kind=subject-reference: a fromZero step's argv names the "
            f"subject ({subject_abs!r}); the from-zero side may never "
            "reference the producer it exists to be compared against")


def assert_brief_names_no_shape(text, forbidden):
    """Refuse a `driver` step's argv part that names a structural element
    of the subject's own declared architecture.

    `forbidden` is derived entirely from the subject's own `structure`
    recipe -- the declared side's `Path` column plus each entry's own
    basename -- never a hand-list of "things a brief must not say" living
    inside this skill or its recipe. Naming a structural element (e.g. the
    literal `SKILL.md`, or `scripts/`) would dictate the driver's output
    shape and reintroduce the exact from-zero fraud this domain closes: the
    producer's own shape arriving spoken instead of copied.
    """
    for name in forbidden:
        if name and name in text:
            raise Unprobeable(
                f"kind=brief-names-the-shape: a fromZero driver step's argv "
                f"names {name!r}, which the subject's own declared file "
                "table lists; a brief may name the problem it is meant to "
                "solve, and never any artefact the subject declares it "
                "ships -- naming the shape would dictate the driver's "
                "output and copy the producer's structure instead of "
                "letting the driver build its own")


def run_box_step(step, repo, subject, box, timeout, forbidden_shape=()):
    """One `fromZero` build step, run inside the box with no shell.

    Mirrors `probe_code_side`'s discipline: argv as a list of strings,
    `shell=False`, a hang becomes exit `2` rather than a wait forever, and a
    nonzero exit from the build itself is an inability to build from-zero,
    never an empty from-zero side.

    A bare list is kind `exec`, unchanged from before this change. A dict
    must declare a `kind` from `BOX_STEP_KINDS`; `driver` additionally
    resolves `cwd` under the box (refusing an occupied one), builds a
    constructed environment from `env`'s declared names intersected with
    `DRIVER_ENV_ALLOWLIST`, proves `argv[0]`'s real path sits outside both
    the repository and the subject, and scans every argv part against
    `forbidden_shape` (see `assert_brief_names_no_shape`). Every part of
    every step, either kind, is interpolated through `FROM_ZERO_TOKENS`
    alone and scanned for a literal reference to the subject.

    Returns a small info dict -- `run_structure` transcribes a `driver`
    step's own info into the report-facing `ignorance` block; an `exec`
    step returns only `{"stepKind": "exec"}`, carrying nothing to
    transcribe. Keyed `stepKind`, never `kind`: `EscalationPartitionTests`
    holds `"kind"` to exactly one meaning across this module -- a note's or
    a stall's own classification, produced solely by `note()` and
    `stalled()` -- and a second dict literal carrying that key anywhere
    else is refused structurally, on sight, regardless of what it means.
    This step-kind value is a different word wearing the same spelling by
    accident; the fix is to stop sharing the spelling, not to carve an
    exception into the lock.
    """
    if isinstance(step, list):
        kind, raw_argv, cwd_spec, env_spec = "exec", step, None, None
    elif isinstance(step, dict):
        kind = step.get("kind", "exec")
        if kind not in BOX_STEP_KINDS:
            raise Unprobeable(
                f"a fromZero step names kind {kind!r}, which is not one of "
                f"{BOX_STEP_KINDS}")
        raw_argv = step.get("argv")
        cwd_spec = step.get("cwd")
        env_spec = step.get("env")
    else:
        raise Unprobeable("a fromZero step must be a list or a dict")

    if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
        raise Unprobeable("a fromZero step's argv must be a list of strings")

    argv = [interpolate_from_zero_token(part, repo, box) for part in raw_argv]
    for part in argv:
        assert_no_subject_reference(part, subject, repo)

    step_cwd = box
    if cwd_spec:
        step_cwd = resolve_under(cwd_spec, box, "driver.cwd")
        if not box_empty_or_absent(step_cwd):
            raise Unprobeable(
                f"a fromZero driver step's cwd is not empty: {step_cwd}; "
                "an occupied box is never silently adopted")
        step_cwd.mkdir(parents=True, exist_ok=True)

    child_env = None
    info = {"stepKind": kind}
    if kind == "driver":
        for part in argv:
            assert_brief_names_no_shape(part, forbidden_shape)
        names = env_spec or []
        # A name declared here but absent from the parent process is
        # dropped from `child_env` with nothing said below -- silent by
        # construction. `envMissing` makes that drop visible: transcribed
        # into `## User drive`, a recipe declaring `USER` on a machine that
        # has none then reads as a stated fact, not as an inexplicable
        # refusal from the child.
        child_env, missing = constructed_child_env(
            names, "a fromZero driver step",
            hint="; a driver refusing for an environment reason is a "
                 "candidate for widening this list by measurement -- run "
                 "the declared argv under `env -i` with only the declared "
                 "names and observe which addition changes the refusal")
        real_path = shutil.which(argv[0], path=child_env.get("PATH"))
        if not real_path:
            raise Unprobeable(
                f"a fromZero driver step's argv[0] is not executable: "
                f"{argv[0]!r}")
        real = Path(real_path).resolve()
        inside_repo = real == repo or repo in real.parents
        inside_subject = real == subject or subject in real.parents
        if inside_repo or inside_subject:
            raise Unprobeable(
                f"kind=driver-not-external: {argv[0]!r} resolves to {real}, "
                "inside the repository or the subject; a driver shipped "
                "inside what it audits is not external")
        info.update({"argv": list(argv), "argv0RealPath": str(real),
                    "cwd": str(step_cwd), "envMissing": missing,
                    "envNames": sorted(names)})

    try:
        completed = subprocess.run(
            argv, cwd=str(step_cwd), shell=False, env=child_env,
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(f"a fromZero step's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"a fromZero step did not answer within {timeout}s; a build that "
            "hangs is an inability to look, never an empty from-zero side")
    if completed.returncode != 0:
        raise Unprobeable(
            f"a fromZero step exited {completed.returncode}: "
            f"{completed.stderr.strip()[:400]}")
    return info


def ignorance_control_gate(box, exclude):
    """Prove the from-zero box's own emptiness detector can see
    contamination, before trusting that emptiness at all.

    Modelled on `candidate_gate_steps`'s inverted control: seed a nonce the
    tool generates, demand `tree_digest` name it, erase, demand it read
    empty again. An `exclude` broad enough to hide the seed -- `["*"]`, or
    anything that over-matches -- would make every box look empty and the
    ignorance claim true by construction, indistinguishable from its own
    absence; proving the detector sees the seed first is what makes this a
    control rather than ceremony.
    """
    nonce = uuid.uuid4().hex
    relative = f"{IGNORANCE_CONTROL_DIR}/{nonce}.txt"
    marker = box / IGNORANCE_CONTROL_DIR / f"{nonce}.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(nonce, encoding="utf-8")
    seeded = tree_digest(box, exclude)
    if relative not in seeded:
        raise Unprobeable(
            "kind=ignorance-control-stalled: the box's own emptiness "
            f"detector did not see a seeded marker at {relative!r}; every "
            "from-zero conclusion downstream is unreached until the "
            "detector can prove it sees contamination")
    erase_box(box)
    box.mkdir(parents=True, exist_ok=True)
    if not box_empty_or_absent(box, exclude):
        raise Unprobeable(
            "kind=ignorance-control-stalled: the box did not read empty "
            "immediately after being re-erased")
    return "passed"


def box_empty_or_absent(box, exclude=()):
    """Whether a box holds no files, proven by content.

    Never by `git status`: `git status --porcelain` over an ignored tree is
    empty by construction, so it can only ever agree, and it would report a
    box that still has files sitting inside it as clean.
    """
    return tree_digest(box, exclude) == {}


def erase_box(box):
    """Remove a box entirely.

    `shutil.rmtree` rather than a hand-rolled walk, so `tree_digest` stays the
    one place in this module allowed to walk a filesystem tree.
    """
    if box.exists():
        shutil.rmtree(box)


def resolve_under(raw, base, label):
    """A recipe-declared root, resolved under `base` and refused if it climbs
    out -- the same discipline `resolve_site` and `probe_code_side`'s `cwd`
    both apply to every other recipe-declared path in this module.
    """
    raw = raw or "."
    parts = Path(raw).parts
    if Path(raw).is_absolute() or ".." in parts:
        raise Unprobeable(f"the recipe's {label} must stay under its root: {raw!r}")
    resolved = (base / raw).resolve()
    if base != resolved and base not in resolved.parents:
        raise Unprobeable(f"the recipe's {label} resolves outside its root: {raw!r}")
    return resolved


#: The only place a `doctrine_side` status becomes a note's `kind`. Hoisted
#: out of `run_roster`'s own inline dict so `note()` can be the single
#: producer of every entry in `notes[]`: a status this map does not name
#: cannot reach `notes[]` at all, which is what lets `ESCALATION_BUCKETS` be
#: checked against `note()`'s own call sites instead of against a second,
#: hand-maintained roster.
DOCTRINE_SIDE_NOTES = {
    "complement": (
        "no-closed-roster",
        "this table is a deliberate subset, so it supports the phantom "
        "direction and never the unregistered one"),
    "no-closed-roster": (
        "no-closed-roster",
        "the set is stated in prose or in another language here, and "
        "prose is what the documented side may not be read out of"),
    "heading-not-found": (
        "heading-not-found",
        "the recipe claims a scope for this table but its quoted heading "
        "is not on disk, so the claim is refused rather than trusted"),
    "scope-claimed-without-heading": (
        "scope-claimed-without-heading",
        "a scope claim with no quoted heading is unfalsifiable"),
}


def note(kind, detail, path, searched):
    """The only way an entry enters `notes[]`.

    A literal scan for `"kind":` strings cannot classify what this module
    emits: `run_roster` writes `"kind": kind` from a variable, which hides
    three of the four escalatable kinds from any such scan. Routing every
    entry through this one constructor instead means the totality lock in
    `EscalationPartitionTests` can scan `note()`'s own call sites for the
    kinds it actually passes, and can refuse -- as a structural fact, not a
    convention -- any dict literal elsewhere that carries a `"kind"` key at
    all.
    """
    return {"detail": detail, "kind": kind, "path": path, "searched": searched}


#: Every kind `note()` can emit, or that `DOCTRINE_SIDE_NOTES` names,
#: partitioned into exactly one bucket. Escalatable: prose exists but could
#: not be derived, and a zero-model probe may still decide it. Consequence:
#: produced only because an escalatable note already fired on the same
#: surface, and never escalated a second time on its own. Deterministic
#: exclusion: a shape or a spelling with no prose behind it to re-read, so
#: escalating it would send a reader after a surface that has nothing to
#: read. `EscalationPartitionTests` holds this constant to the emission
#: sites the same way `FORBIDDEN_SUPPORT` and `ADJUDICATIONS` are held to
#: theirs -- never a second hand-maintained roster.
ESCALATION_BUCKETS = {
    "escalatable": (
        "no-closed-roster", "heading-not-found",
        "scope-claimed-without-heading",
        "no derivation available for this surface", "no-driveable-guard"),
    "consequence": ("comparison-not-run",),
    "deterministic-exclusion": ("shape-not-walkable", "case-only-divergence",
                                "restatement-search-cannot-fire",
                                "guard-never-fires",
                                "guard-unreachable-variant"),
}


def escalation_hint(recipe):
    """The zero-model-probe hint attached to every escalatable note.

    Rung one -- `"probe"` -- is selected only when the emitting recipe
    already declares `probe: "refusal"`: the tool already holds, at
    `recipe["extract"]`, the exact pattern a `candidateGates` control gate
    needs. Move 8 (`walkthrough`) is the mechanism a `probe` rung's
    candidates are driven through. Every other recipe gets rung
    `"readers"`: a two-reader comparison is required before any candidate
    may be proposed at all.
    """
    if recipe.get("probe") == "refusal":
        return {"needs": "candidates", "probe": "8",
                "refusal": recipe.get("extract"), "rung": "probe"}
    return {"needs": None, "probe": None, "refusal": None, "rung": "readers"}


#: Shapes a declared cell can carry that the walk helper can never produce.
#: Expanding one of these against the disk would let the declared side build
#: the very set it is meant to be checked against; counting it as a
#: divergence would blame the disk for a spelling. Neither happens here: the
#: cell is set aside in `notes` instead.
_GLOB_CHARS = set("*?[]")


def normalize_declared_paths(raw_members):
    """Declared path cells, normalised for comparison against a walk.

    POSIX separators, a leading `./` stripped, no trailing slash, case
    preserved, sets compared sorted. A cell whose shape the walk can never
    produce -- a trailing slash, an absolute path, a `..` segment, a glob
    character, or a backslash -- is set aside as `shape-not-walkable` rather
    than normalised, and excluded from every side of the comparison.
    """
    normalised = set()
    notes = []
    for raw in raw_members:
        reason = None
        if raw.endswith("/"):
            reason = "the cell ends with a trailing slash"
        elif "\\" in raw:
            reason = "the cell contains a backslash"
        elif any(char in raw for char in _GLOB_CHARS):
            reason = "the cell contains a glob character"
        elif Path(raw).is_absolute():
            reason = "the cell is an absolute path"
        elif ".." in Path(raw).parts:
            reason = "the cell contains a `..` segment"
        if reason:
            notes.append(note(
                "shape-not-walkable",
                f"{reason}, so it is excluded from every side rather than "
                "expanded against the disk",
                raw, None))
            continue
        cleaned = raw[2:] if raw.startswith("./") else raw
        normalised.add(cleaned)
    return normalised, notes


def case_only_divergences(label_a, set_a, label_b, set_b):
    """Members that agree only case-insensitively, named but never folded.

    Folding them would treat a spelling difference as agreement. Leaving them
    unfolded means such a pair still surfaces as a divergence on the
    arithmetic side, and this note explains why rather than leaving the
    reader to guess.
    """
    lower_b = {}
    for member in set_b:
        lower_b.setdefault(member.lower(), []).append(member)
    found = []
    for member in set_a:
        if member in set_b:
            continue
        for other in lower_b.get(member.lower(), []):
            found.append(note(
                "case-only-divergence",
                f"{label_a} names {member!r}; {label_b} names "
                f"{other!r}, matching only case-insensitively",
                member, None))
    return found


def structure_outcome(declared, disk, from_zero):
    """The arithmetic adjudication: which side, if any, is the odd one out.

    `ADJUDICATIONS` is untouched -- this is a different vocabulary, for a
    different question. Mapping one of these outcomes to a `doctrine wrong` /
    `artefact wrong` verdict is a doctrine decision the auditor makes when it
    writes the report, not something this function does.
    """
    union = declared | disk | from_zero
    only_in = {
        "declared": sorted(declared - disk - from_zero),
        "disk": sorted(disk - declared - from_zero),
        "fromZero": sorted(from_zero - declared - disk),
    }
    missing_from = {
        "declared": sorted(union - declared),
        "disk": sorted(union - disk),
        "fromZero": sorted(union - from_zero),
    }
    if declared == disk == from_zero:
        outcome = "agree"
    elif declared == from_zero:
        outcome = "disk-stale"
    elif declared == disk:
        outcome = "builder-broken"
    elif disk == from_zero:
        outcome = "document-wrong"
    else:
        outcome = "three-way-divergence"
    return outcome, only_in, missing_from


def build_parser():
    """Every subcommand this tool declares.

    Read by the self-audit through `argparse`'s own refusal rather than from a
    list beside it, so a subcommand that ships without a documented row is a
    red rather than a discovery.
    """
    parser = argparse.ArgumentParser(
        prog="audit_cli.py",
        description="Derive both halves of a closed set and compare them.")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    roster = commands.add_parser(
        "roster", help="derive a subject's closed set from code and from docs")
    roster.add_argument("--subject", required=True,
                        help="the subject's root directory")
    roster.add_argument("--probe-spec", required=True,
                        help="the JSON recipe describing how to derive it")
    roster.add_argument("--repo-root", default=".",
                        help="the root a site declaring root=repo resolves under")
    roster.add_argument("--timeout", type=int, default=30,
                        help="seconds before a hanging subject is exit 2")

    report = commands.add_parser(
        "check-report", help="validate a damage report against the shape")
    report.add_argument("report", help="the report file to validate")
    report.add_argument(
        "--moves", default=None,
        help="override path to the doctrine file whose moves table the "
             "move-outcome roster is derived from (default: this skill's own "
             "SKILL.md, resolved relative to this script)")
    report.add_argument(
        "--subject", default=None,
        help="re-derive the '## Frozen' digest from this path and compare "
             "it; without it the payload carries rederived: false and only "
             "finding-vs-'## Frozen' consistency is checked")
    report.add_argument(
        "--supersedes-report", default=None,
        help="a companion report file this report's own '- Supersedes:' "
             "claim names; re-derives the companion's self-digest via the "
             "same mechanism this tool signs its own reports with, and "
             "compares it (and the two reports' '## Frozen' '- Subject:' "
             "values) to the declared claim -- without it a well-formed "
             "claim reports 'unverified', honestly unchecked")

    structure = commands.add_parser(
        "structure",
        help="derive declared, on-disk, and from-zero structure and "
             "adjudicate which side is wrong")
    structure.add_argument("--subject", required=True,
                           help="the subject's root directory")
    structure.add_argument("--spec", required=True,
                           help="the JSON recipe describing the declared, "
                                "disk, and fromZero sides")
    structure.add_argument("--repo-root", default=".",
                           help="the root the box and {repoRoot} token "
                                "resolve under")
    structure.add_argument("--timeout", type=int, default=30,
                           help="seconds before a hanging build step is exit 2")

    walkthrough = commands.add_parser(
        "walkthrough",
        help="drive a recipe's ordered sequence against a real, shared box "
             "and name the index where it stalls")
    walkthrough.add_argument("--subject", required=True,
                             help="the subject's root directory")
    walkthrough.add_argument("--spec", required=True,
                             help="the JSON recipe describing the ordered "
                                  "sequence of steps")
    walkthrough.add_argument("--repo-root", default=".",
                             help="the root the box and {repoRoot} token "
                                  "resolve under")
    walkthrough.add_argument("--timeout", type=int, default=30,
                             help="seconds before a hanging step is a stall "
                                  "of kind timeout")

    reading_diff = commands.add_parser(
        "reading-diff",
        help="compare two supplied readings of one prose surface by "
             "mechanical diff; never sets closed_seen")
    reading_diff.add_argument("--surface", required=True,
                              help="the surface name recorded in the payload")
    reading_diff.add_argument(
        "--reading", action="append", default=[],
        help="a reading file; declare this flag exactly twice")

    sensitivity = commands.add_parser(
        "sensitivity",
        help="vary a declared input a result claims to depend on, and "
             "report whether the declared output moves")
    sensitivity.add_argument("--subject", required=True,
                             help="the subject's root directory")
    sensitivity.add_argument("--spec", required=True,
                             help="the JSON recipe describing the declared "
                                  "site, the disk root to vary, and the "
                                  "producer to drive")
    sensitivity.add_argument("--repo-root", default=".",
                             help="the root the box and {repoRoot} token "
                                  "resolve under")
    sensitivity.add_argument("--timeout", type=int, default=30,
                             help="seconds before a hanging drive is exit 2")

    inversion = commands.add_parser(
        "inversion",
        help="invert every guarded fact a recipe declares in the real "
             "tree, and watch its lock fire")
    inversion.add_argument("--subject", required=True,
                           help="the subject's root directory")
    inversion.add_argument("--spec", required=True,
                           help="the JSON recipe declaring the mutations "
                                "block")
    inversion.add_argument("--repo-root", default=".",
                           help="the root each guarded fact's observe.cwd "
                                "resolves under")
    inversion.add_argument("--timeout", type=int, default=30,
                           help="seconds before a hanging observing run "
                                "is exit 2")

    exits = commands.add_parser(
        "exits",
        help="per state a recipe declares, whether a mechanical exit "
             "exists and is published, and drive it for real if so")
    exits.add_argument("--subject", required=True,
                       help="the subject's root directory")
    exits.add_argument("--spec", required=True,
                       help="the JSON recipe declaring the states block")
    exits.add_argument("--repo-root", default=".",
                       help="the root an interpreter or a repo-scoped act "
                            "resolves under")
    exits.add_argument("--timeout", type=int, default=30,
                       help="seconds before a hanging published act is "
                            "exit-coded published-but-timed-out")

    enumeration_reach = commands.add_parser(
        "enumeration-reach",
        help="per declared check, whether its own iteration source is "
             "derived from the subject or bounded")
    enumeration_reach.add_argument("--subject", required=True,
                                   help="the subject's root directory")
    enumeration_reach.add_argument("--spec", required=True,
                                   help="the JSON recipe declaring the "
                                        "checks block")
    enumeration_reach.add_argument("--repo-root", default=".",
                                   help="the root a site declaring "
                                        "root=repo resolves under")

    return parser


def emit(payload):
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def resolve_site(site, subject, repo):
    """A site's path, under the root the recipe declares and nowhere else.

    Read-only, but still refused if it climbs out: a recipe that can name any
    path on the machine is a recipe that can quietly widen the domain a
    comparison declared.
    """
    root = repo if site.get("root") == "repo" else subject
    relative = site.get("path", "")
    parts = Path(relative).parts
    if not relative or Path(relative).is_absolute() or ".." in parts:
        raise Unprobeable(
            f"a site path must stay under its declared root: {relative!r}")
    return Path(root) / relative


def read_site(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise Unprobeable(f"a documented site could not be read: {error}")


#: The number of independently matching `restatementSearch` sites `duplicated`
#: requires before it reports anything -- one restatement is not a duplication.
#: `run_roster` reads this same constant for the runtime cutoff and for the
#: `restatement-search-cannot-fire` note, so the two never carry two different
#: spellings of one threshold.
RESTATEMENT_SITE_QUORUM = 2


def run_roster(args):
    """Derive both halves of one closed surface and report the difference.

    Exit `0` for any verdict, findings included; exit `2` only when the tool
    could not look. Everything that could make the code side empty raises
    instead of returning, because an empty code side turns every documented row
    into a phantom and prints a broken probe as a page of findings.
    """
    spec_path = Path(args.probe_spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no probe recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the probe recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    notes = []

    if recipe.get("probe") != "refusal":
        notes.append(note(
            "no derivation available for this surface",
            "the subject exposes neither a refusal message nor a parser, "
            "so neither language-independent probe applies",
            str(spec_path), f"{spec_path}:1-1"))
        return finish([], [], notes, [], [], "not-run", recipe, subject, repo)

    code = sorted(set(probe_code_side(recipe, subject, timeout=args.timeout)))

    doctrine = set()
    closed_seen = False
    for site in recipe.get("doctrineSites", []):
        path = resolve_site(site, subject, repo)
        text = read_site(path)
        members, status = doctrine_side(text, site)
        span = f"{path}:1-{max(len(text.splitlines()), 1)}"
        doctrine.update(members)
        if status == "closed":
            closed_seen = True
            continue
        kind, detail = DOCTRINE_SIDE_NOTES[status]
        notes.append(note(kind, detail, str(path), span))

    search = recipe.get("restatementSearch", {})
    duplicated = []
    for site in search.get("paths", []):
        path = resolve_site(site, subject, repo)
        matched, line = restatement_of(read_site(path), code,
                                       search.get("quorum", 2))
        if matched:
            duplicated.append({"line": line, "members": matched,
                               "path": str(path)})
    if len(duplicated) < RESTATEMENT_SITE_QUORUM:
        duplicated = []
    declared_paths = len(search.get("paths", []))
    if "restatementSearch" in recipe and declared_paths < RESTATEMENT_SITE_QUORUM:
        notes.append(note(
            "restatement-search-cannot-fire",
            f"this recipe's restatementSearch declares {declared_paths} "
            f"path(s); `duplicated` only reports once at least "
            f"{RESTATEMENT_SITE_QUORUM} independently matching sites are "
            "found, so this search cannot report a finding regardless of "
            "what the declared path(s) hold -- the search ran and found "
            "nothing reportable by construction, not because no "
            "restatement exists",
            str(spec_path), f"{spec_path}:1-1"))

    comparison = "run" if closed_seen else "not-run"
    if comparison == "not-run":
        notes.append(note(
            "comparison-not-run",
            "no site yielded a closed roster, so the unregistered direction "
            "is not computed; reporting every accepted member as "
            "undocumented would invent one finding per member and none of "
            "them would be about this subject",
            str(subject), f"{subject}:1-1"))
    unregistered = sorted(set(code) - doctrine) if closed_seen else []
    phantom = sorted(doctrine - set(code))

    guard_notes, guard_reach = guard_reach_findings(recipe, subject, args.timeout)
    notes.extend(guard_notes)

    return finish(code, sorted(doctrine), notes, unregistered, phantom,
                  comparison, recipe, subject, repo, duplicated, guard_reach)


def finish(code, doctrine, notes, unregistered, phantom, comparison,
           recipe, subject, repo, duplicated=None, guard_reach=None):
    mismatches = []
    for site in recipe.get("numeralPaths", []):
        mismatches.extend(numeral_mismatches(resolve_site(site, subject, repo)))
    exclude = tuple(recipe.get("exclude", ()))
    escalatable = [dict(entry, escalation=escalation_hint(recipe))
                  for entry in notes
                  if entry["kind"] in ESCALATION_BUCKETS["escalatable"]]
    emit({
        "code": code,
        "comparison": comparison,
        "doctrine": doctrine,
        "duplicated": duplicated or [],
        "escalatable": escalatable,
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "guardReach": guard_reach,
        "notes": notes,
        "numeralMismatch": mismatches,
        "phantom": phantom,
        "surface": recipe.get("surface", ""),
        "unregistered": unregistered,
    })
    return 0


#: sha256 of zero bytes. A produced file carrying this digest has content of
#: length zero -- distinct from `absent` (the from-zero build never wrote it
#: at all). R5 (`spec.md`, "An artefact is judged by what it shows"):
#: "existence is not the measurement." Needs no second walk and no `os.stat`:
#: `tree_digest`'s own sha256 map already carries this fact.
EMPTY_FILE_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def artefact_kind_report(kind, from_zero_root, from_zero_digest, declared_set):
    """R5 + the requirement `73573db` relocated into this commit
    (`spec.md`, "Artefacts on disk that the flow's declared roster never
    names"), sharing one enumeration -- `tree_digest(from_zero_root,
    exclude)`, already built for `structure`'s own three-way comparison.

    For every member of `declared_set` matching this `kind`'s `glob`:
    `"absent"` if the from-zero build never produced it, `"produced-but-
    empty"` if it did but the file carries zero bytes, `"content-not-
    declared"` if the kind names no `contentPattern` to check against
    (never assumed full), `"carries-no-match"` if one is declared and the
    produced content does not match it, else `"produced"`.

    Separately: every on-disk member of this `kind` the declared roster
    never names at all -- `unnamed`, reported whether or not it is empty,
    so a reader learns what the check watches rather than meeting it only
    on failure. The enumeration comes from the filesystem
    (`from_zero_digest`) and the roster from the subject's own
    declarations (`declared_set`) -- deriving both halves rather than
    reading either, exactly as this skill already does for subcommands.
    """
    # Named `kind_glob`, never the bare `glob`: `SingleWalkTests`' AST sweep
    # flags any `glob` identifier outside `tree_digest` on sight, the same
    # false-positive class `.replace` already forced `strip_comparison_
    # operators` to route around with `re.sub`.
    kind_glob = kind["glob"]
    pattern = kind.get("contentPattern")
    on_disk = sorted(path for path in from_zero_digest
                     if fnmatch(path, kind_glob))
    declared_kind = sorted(path for path in declared_set
                           if fnmatch(path, kind_glob))
    content = []
    for path in declared_kind:
        digest = from_zero_digest.get(path)
        if digest is None:
            status = "absent"
        elif digest == EMPTY_FILE_SHA256:
            status = "produced-but-empty"
        elif pattern is None:
            status = "content-not-declared"
        else:
            body = (from_zero_root / path).read_text(
                encoding="utf-8", errors="replace")
            status = "produced" if re.search(pattern, body) else "carries-no-match"
        content.append({"path": path, "status": status})
    unnamed = sorted(set(on_disk) - set(declared_kind))
    return {"content": content, "declared": declared_kind,
           "name": kind["name"], "onDisk": on_disk, "unnamed": unnamed}


def run_structure(args):
    """Derive declared, on-disk, and from-zero, and adjudicate arithmetically.

    Exit `0` for any verdict, including a three-way divergence. Exit `2` when
    a side cannot be derived, when the box is not ours to adopt, or when the
    build wrote outside the box -- none of those is a finding, each is an
    inability to look.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no structure recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the structure recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to box the build under")
    exclude = tuple(recipe.get("exclude", ()))

    declared_site = recipe.get("declared", {})
    declared_path = resolve_site(declared_site, subject, repo)
    declared_text = read_site(declared_path)
    raw_members, _ = doctrine_side(declared_text, declared_site)
    declared_set, notes = normalize_declared_paths(raw_members)
    if not declared_set:
        raise Unprobeable(
            "the declared side normalises to zero members; an empty declared "
            "side would report the entire disk as builder-broken")

    # The roster `assert_brief_names_no_shape` refuses a driver's brief
    # from naming: the declared side's own `Path` column, plus each
    # entry's basename, so a subject that adds a shipped file
    # automatically widens what its own brief may not say -- never a
    # second, hand-maintained list of "structural elements" living beside
    # the guard against exactly that pattern.
    forbidden_shape = tuple(sorted(
        {member for member in raw_members if member}
        | {Path(member).name for member in raw_members if member}))

    disk_root = resolve_under(recipe.get("disk", {}).get("root"), subject,
                              "disk.root")
    if not disk_root.is_dir():
        raise Unprobeable(f"the recipe's disk.root does not exist: {disk_root}")
    disk_set = set(tree_digest(disk_root, exclude))
    if not disk_set:
        raise Unprobeable(
            "the on-disk side normalises to zero members; an empty on-disk "
            "side would report the entire declared side as disk-stale")

    from_zero_spec = recipe.get("fromZero", {})
    steps = from_zero_spec.get("steps", [])
    if not steps:
        raise Unprobeable("the recipe declares no fromZero.steps to build from")

    box = repo / "implementations" / f"_structure_{surface}"
    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running structure again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    try:
        control_gate = ignorance_control_gate(box, exclude)
        box_digest_before = frozen_digest(box, exclude)
        subject_before = tree_digest(subject, exclude)
        step_infos = [run_box_step(step, repo, subject, box, args.timeout,
                                   forbidden_shape=forbidden_shape)
                     for step in steps]
        box_digest_after = frozen_digest(box, exclude)

        from_zero_root = resolve_under(
            from_zero_spec.get("root"), box, "fromZero.root")

        subject_after = tree_digest(subject, exclude)
        if subject_before != subject_after:
            changed = sorted(
                p for p in set(subject_before) | set(subject_after)
                if subject_before.get(p) != subject_after.get(p))
            raise Unprobeable(
                "kind=build-escaped-the-box: the fromZero build changed the "
                f"subject at {changed}; a build writing outside its box is an "
                "inability to look, never a finding, because the tool cannot "
                "tell an intended write from an escape")

        if not from_zero_root.is_dir():
            raise Unprobeable(
                "the recipe's fromZero.root does not exist after the build: "
                f"{from_zero_root}")
        from_zero_digest = tree_digest(from_zero_root, exclude)
        from_zero_set = set(from_zero_digest)
        if not from_zero_set:
            raise Unprobeable(
                "the from-zero side normalises to zero members; an empty "
                "from-zero side would report the entire disk as "
                "builder-broken")

        # R5 + the requirement `73573db` relocated here (`spec.md`, "Artefacts
        # on disk that the flow's declared roster never names"): both share
        # this one from-zero enumeration, read while the box still exists.
        artefacts = [artefact_kind_report(kind, from_zero_root,
                                          from_zero_digest, declared_set)
                    for kind in recipe.get("artefactKinds", [])]
    finally:
        erase_box(box)

    after_removed = box_empty_or_absent(box)

    notes = notes + (
        case_only_divergences("declared", declared_set, "disk", disk_set)
        + case_only_divergences("declared", declared_set, "fromZero", from_zero_set)
        + case_only_divergences("disk", disk_set, "fromZero", from_zero_set))

    outcome, only_in, missing_from = structure_outcome(
        declared_set, disk_set, from_zero_set)

    # The enforceable half of `## User drive`, machine-emitted rather than
    # narrated: whichever step actually declared `kind: driver` is the one
    # whose argv/cwd/env-names/real-path a report transcribes. A recipe
    # built entirely from `exec` steps carries no driver step at all, and
    # `driver` stays `None` -- `## User drive`'s required content is what
    # demands one exist when stage 2 is declared `ran`, not this payload.
    driver_info = next(
        (info for info in step_infos if info.get("stepKind") == "driver"),
        None)

    emit({
        "artefacts": artefacts,
        "containment": {"afterRemoved": after_removed, "beforeEmpty": before_empty,
                        "box": str(box)},
        "escalatable": [dict(entry, escalation=escalation_hint(recipe))
                       for entry in notes
                       if entry["kind"] in ESCALATION_BUCKETS["escalatable"]],
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "ignorance": {
            "argv": driver_info.get("argv") if driver_info else None,
            "argv0RealPath": driver_info.get("argv0RealPath") if driver_info else None,
            "boxDigestAfter": box_digest_after,
            "boxDigestBefore": box_digest_before,
            "controlGate": control_gate,
            "cwd": driver_info.get("cwd") if driver_info else None,
            "envMissing": driver_info.get("envMissing") if driver_info else [],
            "envNames": driver_info.get("envNames") if driver_info else [],
        },
        "missingFrom": missing_from,
        "notes": notes,
        "onlyIn": only_in,
        "outcome": outcome,
        "sides": {"declared": sorted(declared_set), "disk": sorted(disk_set),
                 "fromZero": sorted(from_zero_set)},
        "surface": surface,
    })
    return 0


#: Move 6's hard cap on the number of guarded facts driven per run -- a
#: count, never a wall-clock budget, for the same reason Move 10's own cap
#: below is one: a time budget would make a report's contents depend on
#: the machine that produced it. `SENSITIVITY_INPUT_CAP` is bounded below
#: this cap, cited from this reasoning rather than re-argued there.
INVERSION_FACT_CAP = 8

#: Every comparison operator condition 6 strips from both a guarded fact's
#: `literal` and its `replacement` before comparing what remains. Equal
#: remainders mean the substitution only moved the comparison around the
#: same value -- flipping `==` to `!=` excludes a different subset, it
#: never removes the fact -- and the mutation is refused rather than
#: driven. The two-sided spellings strip before their one-sided halves so
#: neither is left partially consumed.
COMPARISON_OPERATORS = (" is not ", " not in ", "==", "!=", "<=", ">=",
                        "<", ">", " is ", " in ")


#: `strip_comparison_operators`'s own mechanism, compiled once. `re.sub`
#: rather than `str.replace` in a loop: `.replace` shares its name with
#: `Path.replace`, one of the write verbs `NothingWasRepairedTests`'s own
#: AST sweep scans every function for -- a string method sharing a
#: filesystem verb's spelling by accident is exactly the kind of false
#: positive that sweep would otherwise force into its exemption set for a
#: function that writes nothing at all.
_COMPARISON_OPERATOR_RE = re.compile(
    "|".join(re.escape(operator) for operator in COMPARISON_OPERATORS))


def strip_comparison_operators(text):
    """`text` with every member of `COMPARISON_OPERATORS` removed --
    condition 6's mechanical test, applied to a guarded fact's `literal`
    and its `replacement` before the two are compared.
    """
    return _COMPARISON_OPERATOR_RE.sub("", text)


def run_inversion_observe(observe, subject, repo, timeout):
    """Drive one guarded fact's declared observing run, exactly as
    declared -- never a hand-picked subset, and never the whole parent
    environment (conditions 3 and 7). Mirrors `run_sensitivity_drive`'s
    own discipline; `cwd` resolves under `--repo-root` rather than
    `--subject`, because a guarded fact's declaring test commonly lives
    outside the subject (this skill's own suite does).
    """
    raw_argv = observe.get("argv")
    if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
        raise Unprobeable(
            "a guarded fact's observe.argv must be a list of strings")
    argv = [interpolate_token(part, repo, subject, subject) for part in raw_argv]
    for part in argv:
        assert_no_subject_reference(part, subject, repo)
    cwd = resolve_under(observe.get("cwd"), repo, "mutations.observe.cwd")
    names = observe.get("env") or []
    child_env, _ = constructed_child_env(names, "a guarded fact's observe block")
    try:
        return subprocess.run(
            argv, cwd=str(cwd), shell=False, env=child_env,
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(
            f"a guarded fact's observe.argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"a guarded fact's observing run did not answer within "
            f"{timeout}s; a hang is an inability to look, never a verdict")


def run_inversion(args):
    """Move 6: invert every guarded fact a recipe declares, and watch its
    lock fire.

    v1 sources guarded facts only from the recipe's own declared
    `mutations` block, never the subject's own lock roster, and performs
    no AST-based delete/update classification -- both deferred, and
    stated as such in `SKILL.md` rather than smuggled in as unstated
    scope.

    Mutates the real tracked tree in place, never a copy: a guarded
    fact's declaring test commonly lives outside `--subject`, so a copy
    of the subject alone could not host its own observing run. Every
    mutated byte is restored from recorded bytes in a `finally`,
    regardless of outcome, confirmed by `restore_exact_bytes` -- reused
    verbatim, never `git checkout --`.

    Ten soundness conditions guard every substitution; each halts
    `Unprobeable` rather than let a meaningless result through. Exit `0`
    for any verdict, a not-adjudicable finding included; exit `2` only
    for an inability to look: no `mutations` block, an absent or
    ambiguous fact, an operator-flip, a no-op write, a non-green
    baseline, a restore digest mismatch, or an escape.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no inversion recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the inversion recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to scope the sweep under")
    exclude = tuple(recipe.get("exclude", ()))

    mutations = recipe.get("mutations")
    if not mutations:
        raise Unprobeable(
            "the recipe declares no mutations block; a recipe with no "
            "guarded facts to drive is refused, never reported as zero")

    for fact in mutations:
        if not fact.get("observe"):
            raise Unprobeable(
                f"guarded fact {fact.get('fact')!r} declares no observe "
                "block; there is no recipe-level default observing run")

    # Deterministic, machine-independent selection: sorted-first-N, the
    # same idiom `sensitivity` applies to its own varied inputs. `##
    # Unchecked` names every fact beyond the cap individually, never
    # silently dropped.
    ordered = sorted(
        mutations,
        key=lambda fact: (fact["file"], fact["line"], fact["literal"]))
    driven = ordered[:INVERSION_FACT_CAP]
    unchecked = [fact.get("fact") or f"{fact['file']}:{fact['line']}"
                for fact in ordered[INVERSION_FACT_CAP:]]

    # --- Condition 11: the baseline gate. Each distinct declared observe
    # runs once, unmutated, before the first byte is touched. A non-green
    # baseline halts the whole sweep as Unprobeable -- an inability to
    # look is never a verdict about the subject, and it is never reported
    # as a finding. ---
    seen = []
    for fact in driven:
        observe = fact["observe"]
        key = (tuple(observe.get("argv", ())), observe.get("cwd"),
              tuple(sorted(observe.get("env") or ())))
        if key not in seen:
            seen.append(key)
    for argv_key, cwd_key, env_key in seen:
        observe = {"argv": list(argv_key), "cwd": cwd_key, "env": list(env_key)}
        completed = run_inversion_observe(observe, subject, repo, args.timeout)
        if completed.returncode != 0:
            raise Unprobeable(
                "kind=baseline-not-green: the observing run is not green "
                "before any mutation; against an already-red suite every "
                "guarded fact would report fires, having proven nothing")

    frozen_before = tree_digest(subject, exclude)

    matrix = {}
    facts_driven = []
    not_adjudicable = []
    restored = {}
    try:
        for fact in driven:
            label = fact.get("fact") or f"{fact['file']}:{fact['line']}"
            observe = fact["observe"]
            literal = fact["literal"]
            replacement = fact["replacement"]

            path = resolve_under(fact["file"], subject, "mutations.file")
            if not path.is_file():
                raise Unprobeable(
                    f"guarded fact {label!r} names a file that does not "
                    f"exist: {path}")
            before = path.read_bytes()
            lines = before.decode("utf-8").splitlines(keepends=True)
            line_no = fact["line"]
            if not (1 <= line_no <= len(lines)):
                raise Unprobeable(
                    f"guarded fact {label!r} names line {line_no}, outside "
                    f"{path}'s {len(lines)} lines")
            line_text = lines[line_no - 1]
            count = line_text.count(literal)
            if count == 0:
                raise Unprobeable(
                    f"kind=fact-absent: guarded fact {label!r}'s literal "
                    f"{literal!r} is not present at {path}:{line_no}")
            if count > 1:
                raise Unprobeable(
                    f"kind=fact-ambiguous: guarded fact {label!r}'s literal "
                    f"{literal!r} appears {count} times at {path}:{line_no}")
            if literal != replacement and strip_comparison_operators(literal) == \
                    strip_comparison_operators(replacement):
                raise Unprobeable(
                    f"kind=operator-flip: guarded fact {label!r}'s "
                    "replacement only inverts a comparison operator around "
                    "the same value, never the fact's value itself")

            relative = path.relative_to(subject).as_posix()
            restored[relative] = before
            lines[line_no - 1] = line_text.replace(literal, replacement, 1)
            after = "".join(lines).encode("utf-8")
            path.write_bytes(after)
            if hashlib.sha256(after).hexdigest() == \
                    hashlib.sha256(before).hexdigest():
                raise Unprobeable(
                    f"kind=no-op-write: guarded fact {label!r}'s mutation "
                    "left the file's bytes unchanged; the observing run "
                    "never executes against a mutation that did not land")

            completed = run_inversion_observe(observe, subject, repo, args.timeout)
            pending = restored.pop(relative)
            restore_exact_bytes(subject, {relative: pending})

            outcome = "fires" if completed.returncode != 0 else "silent"
            matrix[label] = outcome
            facts_driven.append(label)
            if outcome == "silent":
                not_adjudicable.append({
                    "fact": label, "file": str(path), "line": line_no,
                    "move": 6, "adjudication": "not adjudicable",
                    "remedy": "undecided: none determined"})

        frozen_after = tree_digest(subject, exclude)
        if frozen_before != frozen_after:
            changed = sorted(
                p for p in set(frozen_before) | set(frozen_after)
                if frozen_before.get(p) != frozen_after.get(p))
            raise Unprobeable(
                f"kind=build-escaped-the-box: the inversion drive changed "
                f"{changed}, outside the guarded facts it restored; a "
                "drive writing outside its own box is an inability to "
                "look, never a finding")
    finally:
        if restored:
            restore_exact_bytes(subject, restored)

    emit({
        "baseline": "passed",
        "facts": matrix,
        "factsDriven": facts_driven,
        "factsTotal": len(ordered),
        "factsUnchecked": unchecked,
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "matrix": matrix,
        "notAdjudicable": not_adjudicable,
        "notes": [],
        "observed": facts_driven,
        "range": f"mutations[0:{min(len(ordered), INVERSION_FACT_CAP)}] of {len(ordered)}",
        "surface": surface,
    })
    return 0


#: Move 10's hard cap on the number of declared (output, input) pairs
#: varied per run -- a count, never a wall-clock budget, cited from Move
#: 6's own reasoning rather than re-argued: a time budget would make a
#: report's contents depend on the machine that produced it. Bounded
#: below Move 6's own cap of eight: one sensitivity drive is a full
#: producer invocation, not a subprocess test run, so its unit cost is
#: strictly higher and its worst case (4 varied + 1 control + 1 baseline
#: = 6 drives) stays strictly under Move 6's own cap regardless.
SENSITIVITY_INPUT_CAP = 4

#: The declared range a Move 10 variation sweeps -- absence needs no
#: semantics and is the widest possible range, so "legitimately
#: insensitive over a small range" has no purchase: if a value survives
#: its input's disappearance, no smaller variation would have moved it.
SENSITIVITY_VARIATION_RANGE = "present -> absent"


def declared_value_pairs(text, site):
    """Every `(label, value)` row of a declared results table -- `label`
    always the row's column 0, `value` at the site's own declared column.
    Reuses `markdown_table_rows`, the exact parser `doctrine_side` already
    calls, so this can never see a row `doctrine_side`'s own no-closed-
    roster classification would have missed.
    """
    header = site.get("table")
    if not header:
        return []
    tables = markdown_table_rows(text, header)
    rows = [row for table in tables for row in table]
    column = site.get("column", 0)
    pairs = []
    for row in rows:
        if not row or column >= len(row):
            continue
        label = row[0].strip().strip("`").strip()
        value = row[column].strip().strip("`").strip()
        if label:
            pairs.append((label, value))
    return pairs


def materialize_subject_copy(subject, box, exclude):
    """Copy `subject` into `box/subject`, file by file -- the substrate
    Move 10 perturbs. `## Frozen` pins the real subject's digest for the
    whole report, so the real subject is never touched; everything below
    happens inside this copy, and `erase_box(box)` in the caller's
    `finally` removes it regardless of outcome -- a restore that cannot
    partially succeed, strictly stronger than an inverse patch.

    Copying here is not the `fromZero` fraud: that defect was presenting
    a copy of the product as an independent derivation. Here the copy is
    perturbed and compared against *itself* under a different input --
    copying is the only honest method when the copy is what gets varied.
    """
    destination = box / "subject"
    destination.mkdir(parents=True, exist_ok=True)
    for relative in sorted(tree_digest(subject, exclude)):
        source_path = subject / relative
        target_path = destination / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
    return destination


def vary_by_absence(copy_root, relative_paths):
    """Remove each of `relative_paths` from `copy_root`, returning their
    original bytes keyed by path. The variation is absence (Q17): it
    needs no format semantics, is deterministic, and is the widest
    possible range a declared input can be varied over.
    """
    original = {}
    for relative in relative_paths:
        path = copy_root / relative
        original[relative] = path.read_bytes()
        path.unlink()
    return original


def restore_exact_bytes(copy_root, original):
    """Write every `{relative: bytes}` pair in `original` back into
    `copy_root`, confirmed by sha256 equality per file. Never a blind
    string replace, and never `git checkout --`, which has no target at
    all here: `copy_root` is not tracked by git.
    """
    for relative, data in original.items():
        path = copy_root / relative
        try:
            if path.is_dir():
                raise OSError(f"{path} is now a directory, not a file")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            reproduced = hashlib.sha256(path.read_bytes()).hexdigest() \
                == hashlib.sha256(data).hexdigest()
        except OSError as error:
            raise Unprobeable(
                f"kind=sensitivity-restore-failed: writing {relative} back "
                f"failed: {error}; the sweep halts here rather than "
                "attempting the next variation")
        if not reproduced:
            raise Unprobeable(
                f"kind=sensitivity-restore-failed: writing {relative} back "
                "did not reproduce its pre-variation bytes; the sweep "
                "halts here rather than attempting the next variation")


def run_sensitivity_drive(recipe, real_subject, copy_root, box, repo, timeout):
    """Drive the subject's own declared producer once, inside the copy.

    Mirrors `run_box_step`'s discipline -- argv as a list of strings,
    `shell=False`, a constructed child environment from declared names
    intersected with `DRIVER_ENV_ALLOWLIST` -- reused verbatim rather than
    reimplemented, one allowlist shared with the driver step-kind. `cwd`
    resolves under the copy (never the box, and never able to climb out).
    `{subject}` interpolates to the **copy**, the exact inverse of
    `fromZero`'s own rule, through the same `interpolate_token` every
    other recipe-declared argv already uses; `assert_no_subject_reference`
    still scans every part against the **real** subject, so an argv
    naming the original by hand is refused exactly like `fromZero`'s.
    """
    raw_argv = recipe.get("argv")
    if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
        raise Unprobeable("the recipe's argv must be a list of strings")
    argv = [interpolate_token(part, repo, copy_root, box) for part in raw_argv]
    for part in argv:
        assert_no_subject_reference(part, real_subject, repo)

    cwd = resolve_under(recipe.get("cwd"), copy_root, "sensitivity.cwd")

    names = recipe.get("env") or []
    child_env, _ = constructed_child_env(names, "the sensitivity recipe")

    try:
        return subprocess.run(
            argv, cwd=str(cwd), shell=False, env=child_env,
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(f"the recipe's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"the producer did not answer within {timeout}s; a drive that "
            "hangs is an inability to look, never a clean verdict")


def sensitivity_control_gate(pre_values, post_completed, post_readable,
                             pre_pairs, post_pairs):
    """The inverted control that stops Move 10 accusing a producer never
    proven to consume its box (Q16): every declared input removed at
    once, driven, and the declared site's values demanded to differ from
    what the freshly-copied box already held before anything ran.

    `Unprobeable` (never a finding) when the producer both exits `0` and
    leaves the declared values byte-identical to their pre-drive state:
    the tool cannot tell "never read the box at all" from "every declared
    value is typed in", and choosing would be a verdict with nothing
    behind it. A nonzero exit or an unreadable site after the drive both
    read as the producer demonstrably consuming what the box held, and
    pass without needing the value comparison at all.
    """
    if post_completed.returncode != 0 or not post_readable:
        return "passed"
    if dict(pre_pairs) == dict(post_pairs):
        raise Unprobeable(
            "kind=sensitivity-control-stalled: with every declared input "
            "removed at once, the producer exited 0 and the declared "
            "values did not change from their pre-drive state. Two "
            "readings, and this tool will not choose between them: the "
            "producer never read this box at all, or every declared "
            "value here is typed in rather than computed. Every pair is "
            "unreached until a producer is proven to consume its box")
    return "passed"


def run_sensitivity(args):
    """Move 10: does a declared computed value actually track the
    declared input it claims to depend on?

    Materialize the subject into a copy, prove a producer reads that copy
    at all (the inverted control), drive it once for a baseline, then
    remove one declared input at a time -- up to `SENSITIVITY_INPUT_CAP`
    -- re-driving and re-reading the declared site after each. A declared
    value that never moves across every input it was checked against is
    `not adjudicable`: a fact with no computation traceable to it: the
    provenance cannot be proven or disproven because nothing runs on the
    input side of it to test. Never `artefact wrong` -- distinguishing
    "documented dependency, no path" from "no computation at all" would
    need a hand-written roster of documented dependencies, the exact
    second roster this skill refuses everywhere else.

    Exit `0` for any verdict, a `not adjudicable` finding included, and
    the degenerate "this subject declares no computed values" result.
    Exit `2` only when the tool could not look: an occupied box, a
    stalled control, a baseline the producer refused, a restore
    mismatch, or an escape.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no sensitivity recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the sensitivity recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to box the sweep under")
    exclude = tuple(recipe.get("exclude", ()))
    declared_site = recipe.get("declared", {})

    box = repo / "implementations" / f"_sensitivity_{surface}"
    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running sensitivity again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    try:
        control_seed_gate = ignorance_control_gate(box, exclude)
        copy_root = materialize_subject_copy(subject, box, exclude)
        subject_before = tree_digest(subject, exclude)

        declared_path = resolve_site(declared_site, copy_root, repo)
        declared_text = read_site(declared_path)
        header_span = f"{declared_path}:1-{max(len(declared_text.splitlines()), 1)}"
        _, doctrine_status = doctrine_side(declared_text, declared_site)
        if doctrine_status != "closed":
            notes = [note(
                "no-closed-roster",
                "this subject declares no computed values in a parseable "
                "table; the range searched is named here",
                str(declared_path), header_span)]
            emit({
                "control": None, "frozen": {"digest": frozen_digest(subject, exclude),
                                            "exclude": list(exclude), "subject": str(subject)},
                "inputsTotal": 0, "inputsUnchecked": [], "inputsVaried": [],
                "matrix": {}, "notAdjudicable": [], "notes": notes,
                "range": SENSITIVITY_VARIATION_RANGE, "surface": surface})
            return 2

        disk_root_spec = recipe.get("disk", {}).get("root")
        disk_root = resolve_under(disk_root_spec, copy_root, "disk.root")
        if not disk_root.is_dir():
            raise Unprobeable(f"the recipe's disk.root does not exist: {disk_root}")
        disk_relative_prefix = disk_root.relative_to(copy_root)
        input_relatives = sorted(
            (disk_relative_prefix / member).as_posix()
            for member in tree_digest(disk_root, exclude))
        if not input_relatives:
            raise Unprobeable(
                "the recipe's disk.root normalises to zero members; there "
                "is nothing to vary")

        # Deterministic, machine-independent selection: sorted-first-N.
        # `## Unchecked` names every input beyond the cap, and total names
        # the true size, so a reader never mistakes the cap for exhaustive.
        inputs_varied = input_relatives[:SENSITIVITY_INPUT_CAP]
        inputs_unchecked = input_relatives[SENSITIVITY_INPUT_CAP:]

        # --- Control: every declared input removed at once. ---
        pre_control_text = read_site(declared_path)
        pre_control_pairs = declared_value_pairs(pre_control_text, declared_site)
        removed_all = vary_by_absence(copy_root, input_relatives)
        control_completed = run_sensitivity_drive(
            recipe, subject, copy_root, box, repo, args.timeout)
        try:
            post_control_text = read_site(declared_path)
            post_control_readable = True
        except Unprobeable:
            post_control_text, post_control_readable = "", False
        post_control_pairs = (
            declared_value_pairs(post_control_text, declared_site)
            if post_control_readable else [])
        restore_exact_bytes(copy_root, removed_all)
        control_gate = sensitivity_control_gate(
            pre_control_pairs, control_completed, post_control_readable,
            pre_control_pairs, post_control_pairs)

        # --- Baseline: every declared input present. ---
        baseline_completed = run_sensitivity_drive(
            recipe, subject, copy_root, box, repo, args.timeout)
        if baseline_completed.returncode != 0:
            raise Unprobeable(
                "kind=sensitivity-baseline-refused: with every declared "
                "input present, the producer exited "
                f"{baseline_completed.returncode}. A matrix measured "
                "against a baseline the producer never computed would "
                "read every refusal as a signal; every pair is unreached "
                "until the producer completes with its inputs present")
        baseline_text = read_site(declared_path)
        baseline_pairs = dict(declared_value_pairs(baseline_text, declared_site))

        # The per-run copy-tree check below proves a producer wrote
        # nowhere else in the copy. Snapshotted *after* the baseline
        # drive, not before: the declared results file is expected to
        # change on every drive, including the control and the baseline
        # -- that churn is the whole point of Move 10, never evidence of
        # an escape. The declared path itself is excluded from both
        # snapshots for the same reason; every other path in the copy
        # must still be byte-identical once the sweep finishes.
        declared_relative = declared_path.relative_to(copy_root).as_posix()
        copy_digest_start = {
            path: value for path, value in tree_digest(copy_root, exclude).items()
            if path != declared_relative}

        # --- One variation at a time, restored before the next. ---
        matrix = {label: {} for label in baseline_pairs}
        for relative in inputs_varied:
            removed = vary_by_absence(copy_root, [relative])
            completed = run_sensitivity_drive(
                recipe, subject, copy_root, box, repo, args.timeout)
            try:
                text_after = read_site(declared_path)
                readable = True
            except Unprobeable:
                text_after, readable = "", False
            pairs_after = (
                dict(declared_value_pairs(text_after, declared_site))
                if readable else {})
            restore_exact_bytes(copy_root, removed)

            for label, baseline_value in baseline_pairs.items():
                if completed.returncode != 0 or not readable:
                    outcome = "producer-refused"
                elif pairs_after.get(label) != baseline_value:
                    outcome = "moved"
                else:
                    outcome = "unchanged"
                matrix[label][relative] = outcome

        copy_digest_end = {
            path: value for path, value in tree_digest(copy_root, exclude).items()
            if path != declared_relative}
        if copy_digest_start != copy_digest_end:
            raise Unprobeable(
                "kind=sensitivity-restore-failed: the copy's own tree "
                "digest disagrees before and after the sweep, even though "
                "every per-file restore reported success; a producer "
                "wrote somewhere else in the copy")

        subject_after = tree_digest(subject, exclude)
        if subject_before != subject_after:
            changed = sorted(
                p for p in set(subject_before) | set(subject_after)
                if subject_before.get(p) != subject_after.get(p))
            raise Unprobeable(
                f"kind=build-escaped-the-box: the sensitivity drive changed "
                f"the subject at {changed}; a drive writing outside its "
                "box is an inability to look, never a finding")

        not_adjudicable = sorted(
            label for label, row in matrix.items()
            if row and all(outcome == "unchanged" for outcome in row.values()))
    finally:
        erase_box(box)

    after_removed = box_empty_or_absent(box)

    emit({
        "containment": {"afterRemoved": after_removed, "beforeEmpty": before_empty,
                        "box": str(box)},
        "control": control_gate,
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "inputsTotal": len(input_relatives),
        "inputsUnchecked": inputs_unchecked,
        "inputsVaried": inputs_varied,
        "matrix": matrix,
        "notAdjudicable": not_adjudicable,
        "notes": [],
        "range": SENSITIVITY_VARIATION_RANGE,
        "surface": surface,
    })
    return 0


#: Characters that would carry shell semantics under `shell=True`. This tool
#: never sets `shell=True` -- a published act's argv is always passed as a
#: list of strings -- so any of these appearing in the act's own text is
#: refused rather than passed through as a literal argument the operator
#: never intended: `;`, `|`, `&`, `$`, `>`, `<`, a backtick, or a newline all
#: carry meaning to a shell that they do not carry to `subprocess.run`'s own
#: argv-as-a-list contract, and letting one through would misreport a shell
#: command as broken instead of refusing it before any process starts.
EXIT_SHELL_METACHARACTERS = set(";|&$><`\n")

#: Move 11's own closed, five-value roster (`spec.md`, "A reported state
#: names its exit"). `judgement` and `unstated` are not members: both are
#: reached *before* an act is ever admitted -- a state the recipe or subject
#: declares a human judgement, and a state with no published act and no such
#: declaration -- so they are never a sixth or seventh value of this roster,
#: they are the two ways a state never reaches it at all.
EXIT_OUTCOMES = ("published-and-ran", "published-but-not-executable",
                 "published-but-unparseable", "published-but-timed-out",
                 "unstated")


def split_published_act(act_text):
    """`act_text` split into argv parts, or `None` if the act cannot be
    admitted at all.

    `None` on any `EXIT_SHELL_METACHARACTERS` character: this tool never
    sets `shell=True`, so a semicolon or a pipe reaching `subprocess.run`'s
    argv list would carry no meaning at all, and reporting the act as though
    it had run would be worse than refusing it. `None` on an empty act too --
    the same inability to look, wearing a different shape.
    """
    if any(character in EXIT_SHELL_METACHARACTERS for character in act_text):
        return None
    parts = act_text.split()
    return parts or None


def resolved_act_argv0(argv0, subject, repo, copy_root, interpreters):
    """The absolute path a published act's `argv[0]` actually runs as, or
    `None` if the act is refused before any process starts.

    A name in the recipe's own declared `interpreters` allowlist -- the
    `DRIVER_ENV_ALLOWLIST` precedent, applied to an operator-authored act
    rather than a recipe-declared driver step -- is a tool used to run the
    subject, never the subject's own content, so it is never redirected
    into the copy: a bare name (`python3`) is left exactly as declared, so
    it resolves through the child process's own `PATH`, and a name carrying
    a path separator resolves under `--repo-root`. A name resolving under
    `--subject` instead redirects into `copy_root`: the act runs against a
    COPY, so an exit that repairs repairs only that copy and nothing that
    survives the run. A name resolving under `--repo-root` but outside the
    interpreter allowlist runs against the real repo -- it is repo tooling,
    not subject content, so there is no copy of it to redirect into.
    Anything else -- absolute, climbing `..`, or resolving under neither
    root -- is refused.
    """
    if argv0 in interpreters:
        return Path(argv0) if "/" not in argv0 else (repo / argv0).resolve()
    if "/" not in argv0:
        # A bare command name with no path separator is a lookup against
        # the child's own `PATH`, never a file this tool can locate under
        # either declared root; it is admitted only through the
        # interpreter allowlist above, never by coincidentally matching a
        # root's own name.
        return None
    if Path(argv0).is_absolute() or ".." in Path(argv0).parts:
        return None
    subject_candidate = (subject / argv0).resolve()
    if subject == subject_candidate or subject in subject_candidate.parents:
        return copy_root / subject_candidate.relative_to(subject)
    repo_candidate = (repo / argv0).resolve()
    if repo == repo_candidate or repo in repo_candidate.parents:
        return repo_candidate
    return None


def run_exits_act(argv, cwd, timeout, names):
    """Drive one published act for real, inside `cwd` -- a copy of the
    subject. The act's own exit code is never read: `published-and-ran` is
    reported whether the act refuses or succeeds, because the requirement
    is reachability, not success. A missing binary and a hang are the only
    two ways this can fail to reach `published-and-ran` once admitted.
    """
    child_env, _ = constructed_child_env(names, "a published exit act")
    try:
        subprocess.run(argv, cwd=str(cwd), shell=False, env=child_env,
                       capture_output=True, text=True, timeout=timeout)
        return "published-and-ran"
    except FileNotFoundError:
        return "published-but-not-executable"
    except subprocess.TimeoutExpired:
        return "published-but-timed-out"


def run_exits(args):
    """Move 11: does a reported state let its operator out?

    The eleven earlier moves all ask whether the subject is correct; this
    one asks whether it lets a human out of a state it names. Per state a
    recipe declares: a state the recipe or subject marks a human judgement
    is `judgement`, reported and never a finding -- publishing a command for
    a judgement would be worse than the silence. A state with no such
    declaration is searched, through the recipe's own declared `site` and
    `extract`, for a published act; none found is `unstated`, a finding,
    reported with the driveable range that was searched.

    A found act passes an admission gate before any process starts: split
    into a list of strings or refused, no shell metacharacter, and its
    `argv[0]` resolved under `--subject`, under `--repo-root`, or named in
    the recipe's own declared interpreter allowlist -- anything else is
    `published-but-unparseable`. An admitted act then runs for real inside
    `materialize_subject_copy`'s own copy, through `constructed_child_env`,
    under this subcommand's own `--timeout`. `published-and-ran` deliberately
    never reads the act's own exit code: the requirement is that the act can
    be reached, not that it succeeds.

    The real subject is digested before and after the whole sweep; a
    published act may repair its own copy freely, but a change reaching the
    real subject is `Unprobeable kind=exit-escaped-the-box`, and the sweep
    halts. `erase_box` still runs in a `finally`, whatever the outcome.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no exits recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the exits recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to scope the sweep under")
    exclude = tuple(recipe.get("exclude", ()))
    states = recipe.get("states")
    if not states:
        raise Unprobeable(
            "the recipe declares no states block; a recipe with no "
            "reported states to check is refused, never reported as zero")
    interpreters = tuple(recipe.get("interpreterAllowlist", ()))
    default_env = recipe.get("env") or []

    box = repo / "implementations" / f"_exits_{surface}"
    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running exits again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    subject_before = tree_digest(subject, exclude)
    exits = {}
    searched = {}
    try:
        copy_root = materialize_subject_copy(subject, box, exclude)
        for state in states:
            name = state.get("name")
            if not name:
                raise Unprobeable("a states entry names no state")

            if state.get("judgement"):
                exits[name] = "judgement"
                continue

            site = state.get("site")
            pattern = state.get("extract")
            if not site or not pattern:
                exits[name] = "unstated"
                continue

            path = resolve_site(site, subject, repo)
            text = read_site(path)
            span = f"{path}:1-{max(len(text.splitlines()), 1)}"
            match = re.search(pattern, text)
            if match is None:
                exits[name] = "unstated"
                searched[name] = span
                continue

            act_text = match.group("act").strip()
            parts = split_published_act(act_text)
            resolved0 = (
                resolved_act_argv0(parts[0], subject, repo, copy_root, interpreters)
                if parts else None)
            if resolved0 is None:
                exits[name] = "published-but-unparseable"
                continue

            argv = [str(resolved0), *parts[1:]]
            exits[name] = run_exits_act(
                argv, copy_root, args.timeout, list(state.get("env") or default_env))

        subject_after = tree_digest(subject, exclude)
        if subject_before != subject_after:
            changed = sorted(
                p for p in set(subject_before) | set(subject_after)
                if subject_before.get(p) != subject_after.get(p))
            raise Unprobeable(
                f"kind=exit-escaped-the-box: a published act changed the "
                f"real subject at {changed}; every act runs against a copy "
                "so it may repair nothing that survives -- an escape is an "
                "inability to look, never a finding")
    finally:
        erase_box(box)

    emit({
        "exits": exits,
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "searched": searched,
        "surface": surface,
    })
    return 0


#: The `expect` keys a walkthrough step may declare. `exit` defaults to
#: `"any"`, which asserts nothing on its own -- `declares_expectation` treats
#: an `expect` naming only `exit: any` the same as no `expect` at all, because
#: functionally the two are identical: a gate that always matches whatever it
#: sees is not a gate.
STEP_EXPECT_KEYS = ("exit", "stdout", "stderr", "absent")


def declares_expectation(expect):
    """Whether a walkthrough step's `expect` asserts anything at all.

    A step whose `expect` is missing, empty, or names only `exit: "any"`
    with nothing else declares no expectation, and `run_walkthrough` refuses
    it as `Unprobeable` before ever running the step's command.
    """
    if not expect:
        return False
    if expect.get("exit", "any") != "any":
        return True
    return any(key in expect for key in STEP_EXPECT_KEYS[1:])


def step_matches_expect(expect, returncode, stdout, stderr):
    """Whether one step's real observation matches its own declared `expect`.

    Every declared part of `expect` must hold for the step to be `passed`,
    whatever its exit code -- a step matching its own documented refusal is a
    pass, not a stall. Called only once `declares_expectation` has confirmed
    `expect` asserts something; an `expect` asserting nothing never reaches
    here.
    """
    exit_expect = expect.get("exit", "any")
    if exit_expect == "nonzero":
        if returncode == 0:
            return False
    elif exit_expect != "any" and returncode != exit_expect:
        return False
    if "stdout" in expect and not re.search(expect["stdout"], stdout):
        return False
    if "stderr" in expect and not re.search(expect["stderr"], stderr):
        return False
    if "absent" in expect and re.search(expect["absent"], stdout + stderr):
        return False
    return True


def stalled(kind, index, detail):
    """A walkthrough verdict's own `stall` dict.

    `kind` here is a verdict about *how* a step failed to match its own
    `expect` -- `"missing-executable"`, `"timeout"`, `"contradiction"` --
    never an undecidability. Kept apart from `note()` so a totality lock
    over `notes[]`'s kinds never has to tell a verdict from an unread
    surface by guessing; it simply never looks inside `stalled()` at all.
    """
    return {"detail": detail, "index": index, "kind": kind}


#: The one absurd nonce the `candidateGates` control gate is driven with --
#: a value no real flag or subcommand could ever collide with, so what the
#: subject does with it is a fact about the refusal channel itself, never
#: about a real candidate.
CANDIDATE_GATE_CONTROL_NONCE = "__AUDIT_CONTROL_NONCE__"


def candidate_gate_steps(spec, repo, subject, box):
    """Expand one `candidateGates` block into concrete walkthrough steps:
    one inverted control gate, first, then one gate per candidate.

    One declared `refusal` derives both expectations, so nothing about the
    refusal pattern is restated. The control's own expectation is
    deliberately inverted -- it demands the refusal be *present* -- so a
    channel that never refuses stalls at the control's own index and
    leaves every candidate `unreached` through the walkthrough machinery
    that already exists, no special case and no new branch. No candidate is
    ever reported accepted against a channel not proven capable of
    refusing.
    """
    if not spec:
        return []
    refusal = spec["refusal"]
    raw_argv = spec["argv"]
    candidates = spec["candidates"]

    def gate_argv(candidate):
        return [interpolate_gate_token(part, repo, subject, box, candidate)
               for part in raw_argv]

    steps = [{
        "argv": gate_argv(CANDIDATE_GATE_CONTROL_NONCE),
        "expect": {"exit": "any", "stderr": refusal},
        "role": "gate",
        "name": "candidateGates control: the refusal channel is live",
    }]
    for candidate in candidates:
        steps.append({
            "argv": gate_argv(candidate),
            "expect": {"exit": "any", "absent": refusal},
            "role": "gate",
            "name": f"candidateGates candidate {candidate!r} must not be refused",
        })
    return steps


def normalized_step_roots(step, box):
    """A walkthrough step's declared `roots`, each resolved under the box
    with `resolve_under`'s discipline (no absolute path, no `..`) and
    returned as box-relative POSIX strings, `""` meaning the whole box.

    R6 (`spec.md`: "A driven step is graded on what it wrote"): `roots` is
    the step's own declared ownership boundary inside the shared box, never
    a second hand-maintained list of what the flow is "supposed" to touch.
    """
    normalized = []
    for raw in step.get("roots") or []:
        resolved = resolve_under(raw, box, "step.roots")
        relative = resolved.relative_to(box).as_posix()
        normalized.append("" if relative == "." else relative)
    return normalized


def _inside_declared_roots(path, roots):
    return any(root in ("", ".") or path == root or path.startswith(root + "/")
              for root in roots)


def step_box_verdict(step, roots, before, after):
    """Grade one driven step against what it actually wrote into the shared
    box -- R6's whole subject. `before`/`after` are `tree_digest` maps of
    the box taken immediately around the step's own subprocess run.

    A step the recipe declares `readOnly` is exempt outright (`spec.md`: "A
    step the recipe declares read-only is exempt and MUST be declarable as
    such"); an unchanged box for a step that is not `readOnly` is the
    "returned without producing" finding; a changed box measured against
    declared `roots` is either clean or "wrote into a tree it does not
    own" -- a step with no declared `roots` is not scored against
    ownership at all, since there is nothing declared for it to violate.
    """
    read_only = bool(step.get("readOnly"))
    changed = sorted(
        path for path in set(before) | set(after)
        if before.get(path) != after.get(path))
    if read_only:
        return {"changed": changed, "outsideRoots": [], "readOnly": True,
                "roots": roots, "verdict": "read-only"}
    if not changed:
        return {"changed": changed, "outsideRoots": [], "readOnly": False,
                "roots": roots, "verdict": "produced-nothing"}
    outside = ([path for path in changed
                if not _inside_declared_roots(path, roots)] if roots else [])
    verdict = "wrote-outside-roots" if outside else "produced"
    return {"changed": changed, "outsideRoots": outside, "readOnly": False,
            "roots": roots, "verdict": verdict}


def run_walkthrough(args):
    """Drive a recipe's ordered sequence against one shared box, and name the
    index where it stalls.

    Exit `0` for any verdict, including a stall: a stall is a finding on its
    own, never an inability to look. Exit `2` only when the flow itself could
    not be entered -- a step declaring no expectation, the very first step's
    own command missing, or a `role: "setup"` step failing, all mean there is
    nothing to report on yet.

    Each step declares `role: "setup" | "gate"`, defaulting to `"gate"`
    (precedent: `"reset": true`). A setup step stands up a fixture and
    asserts nothing about the subject -- it must declare no `expect`, is
    never counted among gates that passed, and its failure is reported
    directly as `"setup-failed"` (never `"stalled"`, never routed through
    `Unprobeable`, whose fixed shape cannot name an index): a void run has no
    unchecked gates, it has no run. A recipe with no `"gate"` step at all
    asserts nothing about the subject either, and is refused before it runs.

    One box for the whole sequence, state accumulating as a user's would; a
    step may declare `"reset": true` to demand a fresh, empty box from that
    point on. The box lives at `{repoRoot}/implementations/_walkthrough_
    {surface}`, created only if empty or absent, and removed in a `finally`
    whose absence is proven by `tree_digest`, exactly like `structure`'s box.

    Each step is also graded on what it wrote into the box (R6): its
    `tree_digest` is taken before and after the step's own run, and a step
    the recipe does not declare `readOnly` that leaves the box byte-
    identical is reported as having produced nothing, whatever it exited.
    A step declaring `roots` is graded against them; a change wholly or
    partly outside its declared `roots` is reported as writing into a tree
    it does not own. Separately, and independently of any one step, the
    *subject* tree is digested once before the flow starts and once after
    it ends: `walkthrough` never writes into the subject at all, so any
    change there is `Unprobeable kind=step-escaped-the-box` -- an inability
    to look, never a finding, and the whole sweep halts rather than naming
    which step did it.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no walkthrough recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the walkthrough recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to box the sequence under")
    box = repo / "implementations" / f"_walkthrough_{surface}"
    steps_spec = list(recipe.get("steps", [])) + candidate_gate_steps(
        recipe.get("candidateGates"), repo, subject, box)
    if not steps_spec:
        raise Unprobeable("the recipe declares no steps to walk through")
    if not any(step.get("role", "gate") == "gate" for step in steps_spec):
        raise Unprobeable(
            "the recipe declares no gates to walk through; a walkthrough of "
            "only setup steps asserts nothing about the subject")
    exclude = tuple(recipe.get("exclude", ()))

    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running walkthrough again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    steps_report = []
    stall = None
    setup_failure = None
    subject_before = tree_digest(subject, exclude)
    try:
        for index, step in enumerate(steps_spec):
            name = step.get("name", f"step {index}")
            role = step.get("role", "gate")

            if stall is not None:
                steps_report.append({
                    "expected": step.get("expect"), "index": index,
                    "role": role, "name": name, "observed": None,
                    "box": None, "outcome": "unreached"})
                continue

            expect = step.get("expect")
            if role == "setup":
                if declares_expectation(expect):
                    raise Unprobeable(
                        f"step {index} ({name!r}) is role 'setup' but "
                        "declares an expectation; a setup step asserting "
                        "something about the subject is a gate wearing the "
                        "wrong label")
            elif not declares_expectation(expect):
                raise Unprobeable(
                    f"step {index} ({name!r}) declares no expectation; a "
                    "gate that asserts nothing is not a gate")

            if step.get("reset"):
                erase_box(box)
                box.mkdir(parents=True, exist_ok=True)

            raw_argv = step.get("argv") or []
            if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
                raise Unprobeable(
                    f"step {index} ({name!r})'s argv must be a non-empty "
                    "list of strings")
            argv = [interpolate_token(part, repo, subject, box) for part in raw_argv]

            step_cwd = box
            if step.get("cwd"):
                step_cwd = resolve_under(step["cwd"], box, "step.cwd")

            roots = normalized_step_roots(step, box)
            box_before = tree_digest(box, exclude)
            try:
                completed = subprocess.run(
                    argv, cwd=str(step_cwd), shell=False,
                    capture_output=True, text=True, timeout=args.timeout)
            except FileNotFoundError as error:
                if role == "setup":
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r})'s argv[0] "
                                  f"is not executable: {error}",
                        "index": index, "name": name}
                    break
                if index == 0:
                    raise Unprobeable(
                        f"step 0's argv[0] is not executable: {error}; the "
                        "flow was never entered")
                stall = stalled(
                    "missing-executable", index,
                    f"step {index} ({name!r})'s argv[0] is not executable: "
                    f"{error}")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": None, "box": None,
                    "outcome": "stalled"})
                continue
            except subprocess.TimeoutExpired:
                if role == "setup":
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r}) did not "
                                  f"answer within {args.timeout}s",
                        "index": index, "name": name}
                    break
                stall = stalled(
                    "timeout", index,
                    f"step {index} ({name!r}) did not answer within "
                    f"{args.timeout}s")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": None, "box": None,
                    "outcome": "stalled"})
                continue

            box_after = tree_digest(box, exclude)
            box_report = step_box_verdict(step, roots, box_before, box_after)
            observed = {"exit": completed.returncode,
                       "stderr": completed.stderr, "stdout": completed.stdout}

            if role == "setup":
                if completed.returncode != 0:
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r}) exited "
                                  f"{completed.returncode}",
                        "index": index, "name": name}
                    break
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed, "box": box_report,
                    "outcome": "setup-ok"})
                continue

            if step_matches_expect(expect, completed.returncode,
                                   completed.stdout, completed.stderr):
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed, "box": box_report,
                    "outcome": "passed"})
            else:
                stall = stalled(
                    "contradiction", index,
                    f"step {index} ({name!r})'s observation contradicted "
                    "its own expect")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed, "box": box_report,
                    "outcome": "stalled"})

        subject_after = tree_digest(subject, exclude)
        if subject_before != subject_after:
            changed_subject = sorted(
                p for p in set(subject_before) | set(subject_after)
                if subject_before.get(p) != subject_after.get(p))
            raise Unprobeable(
                "kind=step-escaped-the-box: the driven flow changed the "
                f"subject at {changed_subject}; walkthrough only ever "
                "writes into its own box, and a change to the subject is "
                "an inability to look, never a finding")
    finally:
        erase_box(box)

    if setup_failure is not None:
        # A void run has no unchecked gates, it has no run: `stall` and
        # `unreached` stay at their never-ran values rather than the
        # partial `steps_report` built so far. Emitted directly, not
        # through `Unprobeable`, whose fixed `{"error", "status"}` shape
        # cannot name which step failed.
        emit({
            "detail": setup_failure["detail"],
            "index": setup_failure["index"],
            "name": setup_failure["name"],
            "stall": None,
            "status": "setup-failed",
            "unreached": [],
        })
        return 2

    after_removed = box_empty_or_absent(box)
    unreached = [entry["index"] for entry in steps_report
                if entry["outcome"] == "unreached"]
    gates_declared = sum(1 for step in steps_spec
                         if step.get("role", "gate") == "gate")
    gates_passed = sum(1 for entry in steps_report
                       if entry["role"] == "gate" and entry["outcome"] == "passed")

    emit({
        "containment": {"afterRemoved": after_removed, "beforeEmpty": before_empty,
                        "box": str(box)},
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "gates": {"declared": gates_declared, "passed": gates_passed},
        "stall": stall,
        "steps": steps_report,
        "surface": surface,
        "unreached": unreached,
    })
    return 0


#: `reading-diff`'s own stated epistemic limit, carried in every payload it
#: emits regardless of verdict. Two readers agreeing proves the prose has
#: **one reading**, never that it is closed -- a weaker and different claim,
#: and this string is what stops a report from quietly upgrading one into
#: the other by copying the output without its limit.
READING_DIFF_LIMIT = (
    "agreement between two readers proves the prose has one reading, "
    "never that it is closed; comparison stays not-run for this surface, "
    "permanently")


def reading_pair_digest(paths):
    """One stable `sha256` summary over the exact bytes of the two supplied
    reading files -- the same per-path idiom `frozen_digest` uses, scoped to
    these two files rather than to a directory tree.

    `reading-diff` has no subject directory to walk: the two reading files
    are the bytes the comparison is about. So this reads each file directly
    rather than calling `tree_digest`, which stays the only walker in this
    module per `SingleWalkTests`.
    """
    ordered = sorted(paths, key=str)
    lines = "\n".join(
        f"{path} {hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in ordered)
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


def run_reading_diff(args):
    """Compare exactly two supplied readings of one prose surface by
    mechanical diff, and report agreement or divergence.

    A subcommand, never a flag or a recipe field: either of those would
    route a supplied reading back through `run_roster`, the one function
    that ever assigns `closed_seen = True`. This function never calls
    `doctrine_side`, `probe_code_side`, or `finish` -- asserted over its own
    syntax tree by `ReadingDiffTests` -- so a reading of prose can propose
    candidates, and can never itself close a comparison.

    `comparison` is emitted as the literal `"not-run"`, always: two readers
    agreeing proves the prose has one reading, never that it is closed.
    And when a supplied reading names a strict superset of some real code
    side, the payload still carries no `"unregistered"` key at all -- not an
    empty one, which would read as "checked and found none" rather than
    "never checked".

    Exit `0` for either verdict -- agreement or divergence. Exit `2` only
    when the tool could not look: not exactly two `--reading` flags, a
    reading file that cannot be read, or a reading with no non-empty
    `members` list.
    """
    readings = args.reading or []
    if len(readings) != 2:
        raise Unprobeable(
            f"reading-diff takes exactly two --reading flags; got "
            f"{len(readings)}")

    paths = [Path(raw) for raw in readings]
    member_sets = []
    for path in paths:
        if not path.is_file():
            raise Unprobeable(f"no reading file at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Unprobeable(f"the reading file is unreadable: {error}")
        members = data.get("members")
        if not isinstance(members, list) or not members:
            raise Unprobeable(
                f"the reading file at {path} declares no non-empty "
                "members list")
        member_sets.append({str(member) for member in members})

    set_a, set_b = member_sets
    shared = sorted(set_a & set_b)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    agreement = "single-reading" if not only_a and not only_b else "divergent"

    emit({
        "agreement": agreement,
        "candidates": shared,
        "comparison": "not-run",
        "frozen": {"digest": reading_pair_digest(paths), "exclude": [],
                   "subject": "|".join(str(path) for path in paths)},
        "limit": READING_DIFF_LIMIT,
        "onlyIn": {"a": only_a, "b": only_b},
        "shared": shared,
        "surface": args.surface,
    })
    return 0


#: Move 12's own closed, four-value roster (`spec.md`, "The audit measures an
#: enumerator's reach, not only its result"). `derived` is the innocent
#: default: a check with no bounded pattern this classifier can recognise is
#: presumed derived, never presumed guilty. The other three name exactly the
#: three bounded shapes the source session actually measured: a literal
#: collection, an unfiltered namespace walk (`dir(...)`), and that same walk
#: narrowed by a filter before the assertion runs.
ENUMERATION_SOURCES = ("derived", "literal-collection", "single-namespace",
                       "filtered-subset")

#: The one outcome a non-Python subject's check reports, never guessed at.
#: `probe_code_side` parses no source, on purpose, so the subject may be any
#: language; this subcommand does parse source, so a subject it cannot parse
#: is a language boundary, not an empty roster.
ENUMERATION_UNREACHABLE = "unreachable-for-this-language"


def find_check_function(tree, qualname):
    """The `ast.FunctionDef` a dotted `qualname` names inside `tree`.

    `qualname` is `function` or `Class.method`, the same two shapes
    `check_citations.py`'s own symbol citations use elsewhere in this
    repository -- a name, never a line, since a parallel edit moves every
    line number and never moves a name.
    """
    parts = qualname.split(".")
    class_name, function_name = (None, parts[0]) if len(parts) == 1 \
        else (parts[0], parts[1])
    for node in ast_walk(tree):
        if class_name:
            if not (isinstance(node, ast.ClassDef) and node.name == class_name):
                continue
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == function_name:
                    return child
        elif isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    return None


def _resolve_local_literal(function_node, iterable):
    """`iterable`, or the literal collection it names if it is a bare local
    variable assigned one earlier in the same function.

    A hand-written allowlist is overwhelmingly assigned to a name before it
    is walked -- `test_the_cli_is_stdlib_only`'s own `permitted` set is
    written exactly this way -- so classifying only a literal sitting
    directly in the loop's own `iter` slot would miss the shape real code
    actually has. One level of resolution, not a general data-flow
    analysis: a name assigned anything other than a literal collection, or
    never assigned one at all, is returned unchanged and falls through to
    `derived`.
    """
    if not isinstance(iterable, ast.Name):
        return iterable
    for node in ast_walk(function_node):
        if isinstance(node, ast.Assign) \
                and isinstance(node.value, (ast.List, ast.Tuple, ast.Set, ast.Dict)) \
                and any(isinstance(target, ast.Name) and target.id == iterable.id
                       for target in node.targets):
            return node.value
    return iterable


def _classify_iterable(iterable, has_filter):
    if isinstance(iterable, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return "literal-collection"
    if isinstance(iterable, ast.Call) and isinstance(iterable.func, ast.Name) \
            and iterable.func.id == "dir":
        return "filtered-subset" if has_filter else "single-namespace"
    return "derived"


def enumeration_source_kind(function_node):
    """One check function's own iteration source, classified from its
    syntax tree into `ENUMERATION_SOURCES`.

    Reads the first `for` statement or comprehension `ast.walk` reaches --
    source order for a function with one dominant loop, the shape every
    check this subcommand was built against actually has. A function with
    no loop and no comprehension at all enumerates nothing this classifier
    can see, and is `derived` by the same innocent-until-caught default:
    presumed to compute its own domain rather than presumed to hand-list it.
    """
    for node in ast_walk(function_node):
        if isinstance(node, ast.comprehension):
            iterable = _resolve_local_literal(function_node, node.iter)
            return _classify_iterable(iterable, bool(node.ifs))
        if isinstance(node, ast.For):
            iterable = _resolve_local_literal(function_node, node.iter)
            has_filter = any(isinstance(child, ast.If) for child in node.body)
            return _classify_iterable(iterable, has_filter)
    return "derived"


def run_enumeration_reach(args):
    """Move 12: is a check's own claim of completeness backed by a
    derivation, or by something bounded wearing a derivation's clothes?

    `probe_code_side` parses no source of the subject, on purpose, so the
    subject may be written in any language; this subcommand does the
    opposite on purpose, and so cannot live inside `roster` without forking
    a second code-side derivation there. It reads the recipe's own declared
    `checks` -- each an operator-identified function the operator has
    already read as claiming completeness over a set, by symbol name, never
    by line -- and classifies only the enumeration side: `derived`, or one
    of three bounded shapes. A check whose site does not end `.py`, or whose
    source does not parse as Python, is `unreachable-for-this-language`,
    never guessed at.

    Nothing here mutates the subject; there is no box, no copy, and no
    escape gate, because nothing here writes at all. Exit `0` for any
    verdict; exit `2` only for an inability to look: no `checks` block, a
    check naming no site, or a named check not found in its own site.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no enumeration-reach recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the enumeration-reach recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to scope the sweep under")
    checks = recipe.get("checks")
    if not checks:
        raise Unprobeable(
            "the recipe declares no checks block; a recipe with no checks "
            "to classify is refused, never reported as zero")

    matrix = {}
    parsed = {}
    for entry in checks:
        name = entry.get("name")
        if not name:
            raise Unprobeable("a checks entry names no check")
        site = entry.get("site")
        if not site:
            raise Unprobeable(f"check {name!r} declares no site")

        path = resolve_site(site, subject, repo)
        if path.suffix != ".py":
            matrix[name] = {"claim": None, "verdict": ENUMERATION_UNREACHABLE}
            continue

        cache_key = str(path)
        if cache_key not in parsed:
            try:
                parsed[cache_key] = ast.parse(read_site(path))
            except SyntaxError:
                parsed[cache_key] = None
        tree = parsed[cache_key]
        if tree is None:
            matrix[name] = {"claim": None, "verdict": ENUMERATION_UNREACHABLE}
            continue

        function = find_check_function(tree, name)
        if function is None:
            raise Unprobeable(f"check {name!r} was not found at {path}")
        matrix[name] = {"claim": ast.get_docstring(function),
                        "verdict": enumeration_source_kind(function)}

    bounded = sorted(
        name for name, result in matrix.items()
        if result["verdict"] not in ("derived", ENUMERATION_UNREACHABLE))

    emit({"bounded": bounded, "checks": matrix, "surface": surface})
    return 0


#: Every item a report must carry, with the heading or field that carries it.
#: Held to the shape table in SKILL.md in both directions, so this cannot become
#: a roster restated in two places -- which is the defect the whole tool exists
#: to find, and which a report validator would be the most embarrassing place
#: to ship.
REPORT_SHAPE = {
    "adjudication": "- Adjudication:",
    "changed-line-forecast": "## Changed-line forecast",
    "clean-section": "## Clean, stated as results",
    "computed-value-provenance": "## Computed-value provenance",
    "disputed-severity": "## Disputed severity",
    "drives": "## Drives",
    "evidence-marker": "- Evidence:",
    "falsifier": "## Falsifier",
    "found-by": "- Found by:",
    "frozen": "## Frozen",
    "move-number": "- Move:",
    "move-outcomes": "## Move outcomes",
    "not-adjudicable": "## Not adjudicable",
    "ranked-findings": "## Ranked findings",
    "reachability": "- Reachability:",
    "reading-diff": "## Reading diff",
    "remedy": "- Remedy:",
    "repair-units": "## Repair units",
    "report-integrity": "## Report integrity",
    "stage-outcomes": "## Stage outcomes",
    "supersedes": "- Supersedes:",
    "unchecked-section": "## Unchecked",
    "undecidable": "## Undecidable",
    "user-drive": "## User drive",
}

#: Every stage's own not-run value for the `REPORT_SHAPE` field it demands,
#: keyed by the same `REPORT_SHAPE` key the stages table names in its
#: `Demands` cell. Stage 4's row names `found-by`; while that stage is
#: `skipped`, `- Found by: not-compared` is the honest default every other
#: finding already carries, and only a `ran` stage-4 row tightens what is
#: accepted, per the marker's own shape rather than a second hand-written
#: rule.
FIELD_NOT_RUN = {"found-by": "not-compared"}

#: The header of the moves table this skill's own `SKILL.md` carries. Read
#: with the same `markdown_table_rows` the documented side of every other
#: comparison uses, so a report's required move-outcome roster comes from
#: parsing that table rather than from a list held here -- a hand-written
#: roster in the validator would ship the exact defect this skill exists to
#: find.
MOVES_TABLE_HEADER = "| Move | Ships as | Lock |"

#: `## Move outcomes` rows: `- Move: <id>: ran` or `- Move: <id>: skipped:
#: <reason>`. `<id>` is either a move's number or the literal `textual`, for
#: the one row the moves table carries with no leading digit.
MOVE_OUTCOME_ROW = re.compile(
    r"^-\s*Move:\s*(\d+|textual)\s*:\s*(ran|skipped:\s*.*)$")

#: `## Repair units` header. A table naming, per unit, the findings it groups
#: and its own changed-line forecast -- distinct from grouping by move or by
#: adjudication.
REPAIR_UNITS_HEADER = "| Unit | Findings | Changed lines |"


def move_roster(text):
    """The move-outcome roster a report must carry, derived from one moves
    table rather than listed by hand.

    Every numbered row becomes its own number, as a string; the one row this
    table carries with no leading digit becomes the literal `textual`. Raises
    rather than returning an empty roster when the table cannot be found or
    is not singular, because a roster silently empty would let every report
    pass by accident.
    """
    tables = markdown_table_rows(text, MOVES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {MOVES_TABLE_HEADER!r} table to derive "
            f"the required move-outcome roster from; found {len(tables)}")
    roster = []
    for row in tables[0]:
        match = re.match(r"^(\d+)\b", row[0]) if row else None
        roster.append(match.group(1) if match else "textual")
    return roster


def resolve_moves_doctrine(override):
    """The path `check-report` reads the moves table from.

    Defaults to this skill's own `SKILL.md`, resolved relative to this
    script rather than to the caller's working directory, so the roster a
    report is held to is always this skill's own doctrine unless the caller
    names another file explicitly.
    """
    path = Path(override) if override else Path(__file__).resolve().parent.parent / "SKILL.md"
    if not path.is_file():
        raise Unprobeable(f"no moves-table doctrine file at {path}")
    return path


def move_outcome_rows(lines):
    """Every `- Move: <id>: ran|skipped: <reason>` row under `## Move
    outcomes`, as `{id: outcome}`. Reads only inside that section, so a
    finding's own `- Move: <n>` marker elsewhere in the report is never
    mistaken for an outcome row.
    """
    rows = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Move outcomes":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = MOVE_OUTCOME_ROW.match(stripped)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


#: The header of the stages table this skill's own `SKILL.md` carries. Read
#: the same way `MOVES_TABLE_HEADER` is, so `## Stage outcomes`'s required
#: roster -- and which items are conditional on it -- comes from parsing
#: that table rather than from a list held here. Unlike the moves table
#: there is no `textual` escape valve: every row must carry a leading digit
#: and a `REPORT_SHAPE` key, or the table is `Unprobeable`.
STAGES_TABLE_HEADER = "| Stage | Models | Demands |"

#: `## Stage outcomes` rows: `- Stage: <id>: ran` or
#: `- Stage: <id>: skipped: <reason>`. Mirrors `MOVE_OUTCOME_ROW` exactly.
STAGE_OUTCOME_ROW = re.compile(
    r"^-\s*Stage:\s*(\d+)\s*:\s*(ran|skipped:\s*.*)$")

#: The one skip reason the `user-drive` stage may ever carry. An audit never
#: reports on a subject without driving it -- the zero-model path is never a
#: caller's shortcut to assert, so this literal is the only text
#: `run_check_report` accepts, and only when the measurement it names
#: (`## Undecidable` non-empty, every entry `no-closed-roster`) actually
#: holds. Any other stage-2 skip reason is `driver-required`.
DRIVE_STAGE_RESERVED_SKIP = "no reachable surface (stage 1)"

#: The one skip reason a post-drive stage (numbered after the `user-drive`
#: stage) may carry -- "available, the operator chose not to take it" --
#: legal only once the drive itself reached agreement. Any other stage's
#: `skipped:` text is untouched by this rule; it is unconditional and free.
POST_DRIVE_OFFERED_SKIP = "offered, declined"

#: A `## User drive` section's own `- Outcome:` line -- the one field W5
#: needs before W6 specifies the rest of that section's required content.
#: Read only inside the section, exactly like `frozen_section_fields`.
USER_DRIVE_OUTCOME_LINE = re.compile(r"^-\s*Outcome:\s*(.+?)\s*$")


def user_drive_outcome(lines):
    """The `## User drive` section's own `- Outcome:` value, or `None` if
    the section carries no such line.
    """
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = USER_DRIVE_OUTCOME_LINE.match(stripped)
        if match:
            return match.group(1)
    return None


#: `## User drive`'s own `- Digest:` line, held to `## Frozen`'s declared
#: digest exactly like every finding's own `- Digest:` already is: proof
#: the driven-audit narrative is about the same subject state as the rest
#: of the report.
USER_DRIVE_DIGEST_LINE = re.compile(r"^-\s*Digest:\s*(\S+)\s*$")

#: The heading under which `## User drive` states what the drive did *not*
#: prove -- training-data exposure, contact between drives, "genuinely
#: ignorant" versus "was not shown the file". A bare heading with nothing
#: under it is the same claim as an absent one: a drive that believes it
#: proved everything has misread what it did.
USER_DRIVE_DECLARED_HEADING = "### Declared, not proven"

#: R4 (`spec.md`, "The from-zero drive demands what the subject reads"): the
#: heading under which `## User drive` names, per declaration the subject
#: read from its target during the drive, where it belongs and the
#: consequence of its absence -- an operator's declaration, never a proof,
#: exactly like `USER_DRIVE_DECLARED_HEADING` already is. `(none)` is the
#: explicit way to say there was nothing to demand; a bare heading with
#: nothing under it is refused the same as an absent one, by the same
#: `user_drive_subsection_only_nonempty` this shares with that heading.
USER_DRIVE_DEMANDED_HEADING = "### Demanded, not scaffolded"


def user_drive_digest(lines):
    """`## User drive`'s own `- Digest:` value, or `None` if the section
    carries no such line. Mirrors `frozen_section_fields`'s `- Digest:`
    field, reading only inside the section.
    """
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = USER_DRIVE_DIGEST_LINE.match(stripped)
        if match:
            return match.group(1)
    return None


def user_drive_subsection_only_nonempty(lines, heading):
    """Whether `## User drive`'s subsection named `heading` carries at
    least one non-empty line beneath it, before the next heading of either
    level. Shared by `### Declared, not proven` and `### Demanded, not
    scaffolded`: one walk, one rule, two headings -- never a hand-copied
    second function for the second heading.
    """
    in_user_drive = False
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_user_drive = True
            continue
        if in_user_drive and stripped.startswith("## "):
            break
        if not in_user_drive:
            continue
        if stripped == heading:
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if in_section and stripped:
            return True
    return False


def user_drive_declared_only_nonempty(lines):
    """`### Declared, not proven`'s own check, kept as its own name since
    doctrine and existing call sites already cite it by name.
    """
    return user_drive_subsection_only_nonempty(lines, USER_DRIVE_DECLARED_HEADING)


def stage_roster(text):
    """The `(stage id, REPORT_SHAPE key)` roster a report's stage table
    demands, derived from one stages table rather than listed by hand --
    mirrors `move_roster`, except every row must carry a leading digit and
    a known `REPORT_SHAPE` key: there is no `textual` escape valve here,
    and an unknown key would let a stages table quietly invent an
    enforcement the tool never checks.
    """
    tables = markdown_table_rows(text, STAGES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {STAGES_TABLE_HEADER!r} table to derive "
            f"the required stage-outcome roster from; found {len(tables)}")
    roster = []
    for row in tables[0]:
        match = re.match(r"^(\d+)\b", row[0]) if row else None
        if not match:
            raise Unprobeable(
                f"a stages-table row carries no leading digit: {row!r}")
        if len(row) < 3:
            raise Unprobeable(
                f"a stages-table row is not three cells: {row!r}")
        key = row[2].strip("`")
        if key not in REPORT_SHAPE:
            raise Unprobeable(
                f"stage {match.group(1)} names {key!r} in its Demands "
                "cell, which is not a REPORT_SHAPE key")
        roster.append((match.group(1), key))
    return roster


def stage_model_total(text):
    """The stages table's `Models` column, summed -- the figure the
    doctrine's own "N model runs, total" sentence must name.

    Parsed the same way every other documented side in this module is,
    with `markdown_table_rows`, never a second hand-maintained figure held
    beside the table it describes. The lock over the sentence itself lives
    in `tests/test_skill_audit.py`, not here: `check-report` validates
    reports, and this sentence is the skill's own doctrine, the same home
    `stage_roster`'s own derivation test already occupies.
    """
    tables = markdown_table_rows(text, STAGES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {STAGES_TABLE_HEADER!r} table to sum "
            f"Models from; found {len(tables)}")
    total = 0
    for row in tables[0]:
        if len(row) < 2:
            raise Unprobeable(f"a stages-table row is not three cells: {row!r}")
        try:
            total += int(row[1].strip())
        except ValueError:
            raise Unprobeable(
                f"a stages-table row's Models cell is not an integer: "
                f"{row!r}")
    return total


def resolve_stages_doctrine():
    """The path the stages table is always read from.

    Unlike `resolve_moves_doctrine`, there is no override flag: every
    fixture that exercises `--moves` to prove the move-outcome roster is
    derived rather than hardcoded carries no stages table of its own, and
    coupling stage derivation to that same override would make those
    fixtures `Unprobeable` for a reason unrelated to what they test. The
    stages table always comes from this skill's own `SKILL.md`.
    """
    return resolve_moves_doctrine(None)


def stage_outcome_rows(lines):
    """Every `- Stage: <id>: ran|skipped: <reason>` row under
    `## Stage outcomes`, as `{id: outcome}` -- mirrors `move_outcome_rows`
    exactly, reading only inside that section.
    """
    rows = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Stage outcomes":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = STAGE_OUTCOME_ROW.match(stripped)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


#: `## Undecidable` entry field lines. Each entry starts with `- Kind:`;
#: `- Rung:` and, only when the rung is `probe`, `- Probe: <move>` follow
#: it, up to the next `- Kind:` or the end of the section.
UNDECIDABLE_KIND_LINE = re.compile(r"^-\s*Kind:\s*(.+?)\s*$")
UNDECIDABLE_RUNG_LINE = re.compile(r"^-\s*Rung:\s*(probe|readers)\s*$")
UNDECIDABLE_PROBE_LINE = re.compile(r"^-\s*Probe:\s*(\d+)\s*$")


def undecidable_entries(lines):
    """Every `## Undecidable` entry, each `{surfaceKind, rung, probe}` -- `probe`
    is `None` unless the entry's own rung is `probe`. Read only inside
    that section, exactly like `frozen_section_fields` and
    `move_outcome_rows`, so prose elsewhere in the report is never
    mistaken for a recorded entry.
    """
    entries = []
    in_section = False
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped == "## Undecidable":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        kind_match = UNDECIDABLE_KIND_LINE.match(stripped)
        if kind_match:
            # Not `"kind"`: that key is reserved to `note()`'s reason and
            # `stalled()`'s verdict, and `EscalationPartitionTests` refuses
            # any other dict literal that carries it.
            current = {"surfaceKind": kind_match.group(1),
                      "rung": None, "probe": None}
            entries.append(current)
            continue
        if current is None:
            continue
        rung_match = UNDECIDABLE_RUNG_LINE.match(stripped)
        if rung_match:
            current["rung"] = rung_match.group(1)
            continue
        probe_match = UNDECIDABLE_PROBE_LINE.match(stripped)
        if probe_match:
            current["probe"] = probe_match.group(1)
    return entries


ADJUDICATIONS = ("doctrine wrong", "artefact wrong", "not adjudicable")

#: `- Found by:`'s closed set -- the independence axis, distinct from
#: `- Evidence:`'s obtained axis. Enforced with no default, exactly like
#: `- Evidence:`: a missing marker is never read as `one`, any more than a
#: missing evidence marker is read as confirmed.
FOUND_BY_VALUES = ("both", "one", "not-compared")

#: `- Remedy:`'s closed set, required on -- and only on -- a finding that
#: carries both `- Move: 6` and `- Adjudication: not adjudicable`: Move 6
#: finds a guarded fact whose mutation left the suite green, and that
#: single bucket hides two different jobs. `delete` names a fact that no
#: longer exists; `update` names a fact that exists but moved, or that the
#: test measures wrongly. Neither AST existence-checking nor any other
#: mechanical test can always resolve the split, so `undecided` is a third,
#: legitimate value, never an omission -- and there is no default: a
#: missing marker is never read as any of the three.
REMEDY_VALUES = ("delete", "update", "undecided")

#: The closed set of causes an `undecided` Move-6 remedy reason must name
#: one of -- condition 9. Condition 2 proves the bytes moved; nothing
#: proves behaviour moved, so `- Remedy: undecided: <reason>` must state
#: which of these it could not rule out, rather than defaulting to
#: `obsolete guard` when the cause might equally be an equivalent mutant
#: (bytes moved, behaviour identical) or a degenerate fixture (the
#: fixture's own correct answer already equals the mutant's output).
#: `"none determined"` is itself a legitimate fourth member, never an
#: omission: an honest "I could not tell" is not the same claim as a
#: guess dressed as a finding.
UNDISTINGUISHED_CAUSES = ("obsolete guard", "equivalent mutant",
                          "degenerate fixture", "none determined")

#: `- Reachability:`'s closed set -- condition 10. Every substitution-probe
#: finding proves the guarded fact's lock **fires** or stayed **silent**;
#: it never proves every consumer of the fact was exercised. Reachability,
#: never coverage, and the report must say so on its own payload rather
#: than let a reader infer the stronger claim.
REACHABILITY_VALUES = ("fires", "silent")

NO_CONFIRMED_DECLARATION = "No finding in this report is CONFIRMED by execution"

#: Supports a report may never lean on. Each one is a mistake made in this
#: repository, not a hypothetical: a claim resting on any of them says something
#: about the environment, the index, or the mood of a suite, and nothing about
#: the subject.
FORBIDDEN_SUPPORT = {
    "green-suite": (
        re.compile(r"suite (passed|is green)|tests all pass", re.IGNORECASE),
        "greenness is never evidence; name the execution and the observation"),
    "porcelain-containment": (
        re.compile(r"git status", re.IGNORECASE),
        "`git status --porcelain` over an ignored tree is empty by "
        "construction, so it can only ever agree; a content manifest taken "
        "before and after is the evidence that would actually decide this"),
    "request-as-receipt": (
        re.compile(r"live GET|GET returned|request succeeded", re.IGNORECASE),
        "a successful request proves the environment answered, never a fact "
        "about the subject's code"),
    "single-harness-count": (
        re.compile(r"repository[^.\n]*\b\d+\s+tests", re.IGNORECASE),
        "the harnesses are disjoint and no single command runs both, so one "
        "of them cannot report a repository-wide count"),
}

BOTH_HARNESSES = (re.compile(r"unittest", re.IGNORECASE),
                  re.compile(r"npm test|node", re.IGNORECASE))

CITATION = re.compile(r"`[^`\s]+:\d+`")


def report_findings(lines):
    """Every `### F<n>.` block, with the lines that belong to it and the
    top-level `## ` section it sits directly under -- the section a
    finding's own `- Adjudication:` must agree with when that adjudication
    is `not adjudicable`.
    """
    blocks = []
    section = None
    for index, line in enumerate(lines):
        if re.match(r"^### F\d+\.", line.strip()):
            blocks.append({"label": line.strip()[4:].split(".")[0],
                           "line": index + 1, "start": index, "text": [],
                           "section": section})
        elif line.startswith("## "):
            section = line.strip()
            if blocks and "end" not in blocks[-1]:
                blocks[-1]["end"] = index
        elif blocks and "end" not in blocks[-1]:
            blocks[-1]["text"].append(line)
    return blocks


def repair_unit_rows(text):
    """The `## Repair units` table's rows, or `None` if no such table exists.

    Distinct from `## Changed-line forecast`, which sizes the fix by remedy,
    never by the hand-off-able group a downstream change would take whole.
    """
    tables = markdown_table_rows(text, REPAIR_UNITS_HEADER)
    if len(tables) != 1:
        return None
    return tables[0]


#: `## Frozen`'s own three fields: `- Digest:`, `- Subject:`, `- Exclude:`.
#: Self-describing, so re-deriving the digest needs no out-of-band argument
#: beyond `--subject` -- the exclude list travels with the report itself.
FROZEN_FIELD_ROW = re.compile(r"^-\s*(Digest|Subject|Exclude):\s*(.*)$")


def frozen_section_fields(lines):
    """The `- Digest:`, `- Subject:`, and `- Exclude:` lines under
    `## Frozen`, read only inside that section -- exactly like
    `move_outcome_rows` -- so a finding's own citation of a digest elsewhere
    in the report is never mistaken for the run's own frozen fields.
    """
    fields = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Frozen":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = FROZEN_FIELD_ROW.match(stripped)
        if match:
            fields[match.group(1).lower()] = match.group(2).strip()
    return fields


#: A `- Position:` line under `## Disputed severity`. The section is a bare
#: heading -- an empty one demands nothing, because a surface nobody looked
#: at and a surface both drives agreed on must not read the same way (R6).
POSITION_LINE = re.compile(r"^-\s*Position:\s*.+$")


def disputed_severity_positions(lines):
    """`- Position:` lines under `## Disputed severity`, and whether the
    section carries any content at all beyond the bare heading.

    Read only inside the section, exactly like `frozen_section_fields` and
    `move_outcome_rows`, so a finding's own prose elsewhere in the report is
    never mistaken for a recorded position.
    """
    positions = []
    in_section = False
    has_content = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Disputed severity":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        if stripped:
            has_content = True
        if POSITION_LINE.match(stripped):
            positions.append(stripped)
    return has_content, positions


#: `- Delete:`, `- Update:`, `- Undecided:` -- the three rosters
#: `## Not adjudicable` derives from its own Move-6 findings. Required at
#: the top of the section, before the first `### F` block: `report_findings`
#: closes a finding's own text at the next `## ` line, so a line placed
#: after the first finding would be swallowed into that finding's text
#: rather than read as the section's own roster.
REMEDY_ROSTER_LINE = re.compile(r"^-\s*(Delete|Update|Undecided):\s*(.+?)\s*$")


def not_adjudicable_roster_lines(lines):
    """The `- Delete:`, `- Update:`, `- Undecided:` lines under `## Not
    adjudicable`, read only between that heading and the section's first
    `### F` block -- modelled on `frozen_section_fields` and
    `disputed_severity_positions`'s own "read only inside this section"
    discipline, narrowed further to stop at the first finding rather than
    the next `## ` heading, matching exactly where these lines are
    required to sit.

    Returns `{"delete": raw, "update": raw, "undecided": raw}` for every
    roster line actually present; a bucket the report carries no line for
    is simply absent from the dict, never a default empty string -- an
    absent line and an explicit `(none)` must read differently.
    """
    rosters = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Not adjudicable":
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("## ") or re.match(r"^### F\d+\.", stripped):
            break
        match = REMEDY_ROSTER_LINE.match(stripped)
        if match:
            rosters[match.group(1).lower()] = match.group(2)
    return rosters


def roster_labels(raw):
    """A roster line's raw value, back into a sorted list of finding
    labels -- `(none)` becomes the empty list, mirroring
    `parse_exclude_field`'s own `(none)` idiom for an empty declared set.
    """
    if raw is None or raw == "(none)":
        return []
    return sorted(part.strip() for part in raw.split(",") if part.strip())


def parse_exclude_field(value):
    """`- Exclude:`'s rendered value, back into the tuple `frozen_digest`
    accepts. `(none)` -- the shape `## Frozen` renders when the list is
    empty -- becomes the empty tuple; anything else is a comma-separated
    list of `fnmatch` patterns.
    """
    if not value or value == "(none)":
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


#: The report-shape schema version this tool validates against. Named
#: `skill-audit-report/N` in a report's own `- Schema:` line -- a monotone
#: integer, never semver (no meaningful minor/patch distinction exists for a
#: validator that either knows a shape or does not) and never a date (two
#: schema changes on one day would collide) or a git sha (unreadable to a
#: human hitting a refusal, and it would couple the schema to a commit a
#: revert would falsify). Derived-checked, not restated: `SKILL.md` states
#: the version once, in prose, and a lock asserts this constant equals it --
#: the same discipline `stage_model_total` already established for "Six
#: model runs, total".
REPORT_SCHEMA_VERSION = 1

#: `## Report integrity` is judged entirely by the identity gate below,
#: before the unconditional sweep in `run_check_report` ever runs. Named
#: here explicitly, rather than left as an unreachable branch of that sweep:
#: a future edit that moves the gate later would otherwise silently
#: reintroduce the exact collapse this domain exists to prevent -- a report
#: that predates the shape being judged as an ordinary missing section.
PRE_SWEEP_ITEMS = {"report-integrity"}

REPORT_INTEGRITY_HEADING = "## Report integrity"
REPORT_INTEGRITY_SCHEMA_LINE = re.compile(r"^-\s*Schema:\s*(\S+)\s*$")
REPORT_INTEGRITY_SELF_DIGEST_LINE = re.compile(r"^-\s*Self-digest:\s*(\S+)\s*$")

#: `- Supersedes: sha256:<hex>` inside `## Report integrity`: an optional
#: claim naming the OTHER report's own self-digest -- never this report's.
#: Captures the raw value; well-formedness is judged separately, by
#: `SUPERSEDES_VALUE_SHAPE` below, so a malformed value is an ordinary-sweep
#: violation, never a parse failure at this stage.
REPORT_SUPERSEDES_LINE = re.compile(r"^-\s*Supersedes:\s*(\S+)\s*$")

#: Well-formedness for a `- Supersedes:` value: `sha256:` followed by one or
#: more hex digits. Deliberately not length-anchored to 64 hex chars -- no
#: other digest field in this codebase validates hex length, only content
#: equality.
SUPERSEDES_VALUE_SHAPE = re.compile(r"^sha256:[0-9a-f]+$")


def _top_level_section_span(lines, heading):
    """The `[start, end)` line-index span of one top-level `## ` section,
    heading line included, running to the next `## ` line or EOF. `None`
    when the heading does not appear verbatim as its own stripped line.
    """
    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def report_self_digest(text):
    """A report's own canonical self-digest, over its text with the one
    `- Self-digest:` line inside `## Report integrity` excluded.

    The exclusion is stated as an algorithm so two implementations cannot
    disagree about what they are hashing:

    1. Replace `\\r\\n` and lone `\\r` with `\\n` (universal-newline reading,
       regardless of how the caller obtained `text`); split on `\\n`.
    2. Locate `## Report integrity` -- the line equal to that string after
       `.strip()` -- running to the next line starting with `## ` or EOF.
    3. Inside that span, find every line matching `^-\\s*Self-digest:\\s*
       (\\S+)\\s*$`. Two or more raises `Unprobeable`: the tool cannot tell
       which line is the claim, and picking one would be adjudication with
       nothing behind it.
    4. **Remove** that one line entirely -- never blank it. A blanked line
       is still a line whose presence depends on the field, and two
       implementations could reasonably disagree about whether it stays;
       removing it is decidable by inspection.
    5. `rstrip()` every remaining line of spaces, tabs, and `\\r`; drop
       trailing empty lines at EOF; join with `\\n`.
    6. Encode UTF-8, hash with sha256, and return it in `frozen_digest`'s own
       `"sha256:" + hexdigest` shape -- a report carries one digest
       vocabulary, not two.

    Canonical content, not raw bytes: a trailing-newline difference or a
    CRLF/LF conversion must not read as tampering, the same class of
    misdiagnosis this project already found in a `403` caused by a missing
    `owner_slug` field and in a `claude` driver refusing for a missing
    `USER`. Only what no editor asked a human about is normalized; nothing a
    human could have meant is.
    """
    # `str.splitlines()` already treats `\r\n` and lone `\r` as line breaks
    # exactly like `\n` -- the universal-newline read step -- and discards
    # the specific line-ending byte, so no separate normalization call is
    # needed (and none is made: `SuiteIntegrityTests`'s write-verb lock
    # scans every attribute-call name in this file by spelling alone, and
    # cannot distinguish `str.replace` from a filesystem write; the honest
    # fix is to need no method carrying that name here, not an exemption
    # naming a function that writes nothing at all).
    lines = text.splitlines()
    span = _top_level_section_span(lines, REPORT_INTEGRITY_HEADING)
    kept = list(lines)
    if span is not None:
        start, end = span
        digest_indices = [
            index for index in range(start, end)
            if REPORT_INTEGRITY_SELF_DIGEST_LINE.match(lines[index].strip())]
        if len(digest_indices) >= 2:
            raise Unprobeable(
                f"the report carries {len(digest_indices)} '- Self-digest:' "
                "lines under '## Report integrity'; the tool cannot tell "
                "which one is the claim, and choosing would be a verdict "
                "with nothing behind it")
        if digest_indices:
            del kept[digest_indices[0]]
    while kept and kept[-1] == "":
        kept.pop()
    canonical = "\n".join(line.rstrip(" \t\r") for line in kept)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def report_integrity_fields(lines):
    """The `- Schema:`, `- Self-digest:`, and `- Supersedes:` values under
    `## Report integrity`, read only inside that section -- exactly like
    `frozen_section_fields`. `None` for any key the section does not carry
    (including `- Supersedes:`, which is optional and never required).
    Raises `Unprobeable` when any of the three appears twice: the same
    "which line is the claim" inability `report_self_digest` raises for a
    duplicated `- Self-digest:`, extended to `- Schema:` and `- Supersedes:`
    for symmetry.
    """
    span = _top_level_section_span(lines, REPORT_INTEGRITY_HEADING)
    if span is None:
        return None
    start, end = span
    schema_values, self_values, supersedes_values = [], [], []
    for index in range(start, end):
        stripped = lines[index].strip()
        match = REPORT_INTEGRITY_SCHEMA_LINE.match(stripped)
        if match:
            schema_values.append(match.group(1))
            continue
        match = REPORT_INTEGRITY_SELF_DIGEST_LINE.match(stripped)
        if match:
            self_values.append(match.group(1))
            continue
        match = REPORT_SUPERSEDES_LINE.match(stripped)
        if match:
            supersedes_values.append(match.group(1))
    if len(schema_values) >= 2 or len(self_values) >= 2 or len(supersedes_values) >= 2:
        raise Unprobeable(
            "the report's '## Report integrity' section carries more than "
            "one '- Schema:', '- Self-digest:', or '- Supersedes:' line; "
            "the tool cannot tell which one is the claim, and choosing "
            "would be a verdict with nothing behind it")
    return {"schema": schema_values[0] if schema_values else None,
            "selfDigest": self_values[0] if self_values else None,
            "supersedes": supersedes_values[0] if supersedes_values else None}


def schema_version_classification(schema):
    """A companion report's own `- Schema:` value, classified as `absent`,
    `current`, `predates`, or `postdates` -- structurally identical to the
    version-comparison branch already inside `report_identity_gate`, but a
    small, standalone, pure function used ONLY by the `--supersedes-report`
    companion-check path.

    `report_identity_gate` itself stays untouched: it is already
    tamper-sensitive, already covered by `HistoricalReportRecordTests` and
    the Q9-step-4 blanked-line lock, and this addition is purely additive --
    touching it for a DRY gain would put untested blast radius on
    already-hardened code for no requirement this domain has. A ~6-line
    duplication of the numeric-comparison logic against the gate's own
    inline branch is the accepted, smaller, reversible cost.
    """
    if schema is None:
        return "absent"
    current = f"skill-audit-report/{REPORT_SCHEMA_VERSION}"
    if schema == current:
        return "current"
    match = re.match(r"skill-audit-report/(\d+)$", schema)
    if match and int(match.group(1)) < REPORT_SCHEMA_VERSION:
        return "predates"
    return "postdates"


def report_identity_gate(text, lines):
    """The RECONCILED three-way classification (spec's
    `report-tamper-evidence` domain, reconciled against the design's
    mechanism): `valid` (exit 0), `tampered` (exit 1, a finding), or
    `predates the schema` (exit 2, `Unprobeable` -- an inability to judge,
    never an error and never a clean verdict).

    Returns `None` when the report is current-schema and its self-digest
    recomputes -- the caller proceeds to the existing sweep. Otherwise
    returns `(exit_code, payload)`, which the caller emits and returns
    directly: nothing else is computed for a report that will not be
    judged, and a `tampered` report is never handed the rest of the sweep
    either, so a single mismatch is never buried among unrelated findings.

    The presence-combination is checked BEFORE the schema-version value --
    the reconciliation's load-bearing ordering. Both fields absent together
    is the only shape that means "written before this shape existed";
    exactly one present is a partial, inconsistent state that means someone
    edited the report, classified `tampered` rather than `predates the
    schema`. Reading the schema value first would let an attacker strip
    only `- Schema:` and escape into the unjudged, `predates` bucket --
    exactly the loophole this ordering closes.
    """
    fields = report_integrity_fields(lines)
    schema = fields["schema"] if fields else None
    self_digest = fields["selfDigest"] if fields else None

    if schema is None and self_digest is None:
        return 2, {
            "error": (
                "this report carries no '## Report integrity' section (or "
                "an empty one), so it was written before the report shape "
                "carried one. That is not tampering, and this tool will not "
                "judge it: it cannot distinguish a record written under an "
                "older shape from one whose identity was removed, and "
                "guessing would make those two indistinguishable forever. "
                "Read it by hand, or supersede it with a new report under "
                "the current shape."),
            "status": "predates-the-schema"}

    if schema is None or self_digest is None:
        missing = "- Schema:" if schema is None else "- Self-digest:"
        present = "- Self-digest:" if schema is None else "- Schema:"
        return 1, {"rederived": False, "violations": [{
            "detail": (
                f"the report's '## Report integrity' section carries "
                f"{present!r} but not {missing!r}. A report with exactly "
                "one of the two identity fields is not a report written "
                "before this shape existed -- that would carry neither -- "
                "it is a report someone edited after the fact. This is "
                "tampered, not predates-the-schema."),
            "item": "report-integrity", "where": "line 1"}]}

    current = f"skill-audit-report/{REPORT_SCHEMA_VERSION}"
    if schema != current:
        match = re.match(r"skill-audit-report/(\d+)$", schema)
        if match and int(match.group(1)) < REPORT_SCHEMA_VERSION:
            return 2, {
                "error": (
                    f"this report declares schema {schema!r}; this tool "
                    f"ships {current!r}. It validates one shape, and "
                    "judging an older record under a newer shape is how a "
                    "record gets edited to fit. Supersede it, or read it by "
                    "hand."),
                "status": "predates-the-schema"}
        # `match` and NOT older means a numbered version above current, the
        # symmetric case; no `match` at all means the value names no
        # `skill-audit-report/N` shape this tool has ever shipped. Both read
        # the same to a validator that only ever knows one shape: it has not
        # judged a report written under a shape it does not recognise.
        return 2, {
            "error": (
                f"this report declares schema {schema!r}, which this tool "
                f"(shipping {current!r}) does not recognise. A validator "
                "that does not know a shape has not judged a report "
                "written under it."),
            "status": "postdates-the-schema"}

    recomputed = report_self_digest(text)
    if recomputed != self_digest:
        return 1, {"rederived": False, "violations": [{
            "detail": (
                f"the report's recorded self-digest {self_digest} disagrees "
                f"with its content, which now digests to {recomputed}. A "
                "report is a record of one audit at one moment: a wrong "
                "report is superseded by a new report, never edited into "
                "agreement. Recomputing this field would make the guard "
                "ceremony -- do not."),
            "item": "report-integrity", "where": "line 1"}]}

    return None


def run_check_report(args):
    """Validate a damage report against the shape, as a process.

    Exit `0` valid, `1` invalid, `2` unreadable. The third is separate for the
    same reason `roster` keeps it separate: a report nobody could open has not
    been judged, and recording it as invalid would be a verdict with nothing
    behind it.
    """
    path = Path(args.report)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        emit({"error": f"the report could not be read: {error}",
              "status": "unreadable"})
        return 2

    lines = text.splitlines()
    violations = []

    def fail(item, detail, where):
        violations.append({"detail": detail, "item": item, "where": where})

    # Self-supersession is checked against the RAW recorded fields, before
    # the identity gate below ever runs -- deliberately, not merely for
    # convenience. `- Supersedes:` is itself part of what `report_self_
    # digest` hashes (only `- Self-digest:` is ever excluded), so a report
    # can never be constructed whose CORRECT self-digest equals a value
    # that is itself an input to that same digest -- a cryptographic hash
    # has no fixed point a fixture could ever build. Checking the raw
    # strings first, ahead of the gate's own recompute step, is what makes
    # this violation reachable at all; `report_identity_gate` itself is
    # untouched -- this is a new, independent check, not a change to its
    # three-way classification.
    integrity_fields = report_integrity_fields(lines)
    early_supersedes_claim = integrity_fields.get("supersedes") if integrity_fields else None
    if (early_supersedes_claim is not None
            and integrity_fields.get("selfDigest") == early_supersedes_claim):
        emit({"rederived": False, "supersession": "unverified", "violations": [{
            "detail": (
                "the report's '- Supersedes:' value equals its own "
                "'- Self-digest:' value; a report cannot supersede itself"),
            "item": "supersedes", "where": f"{path}:1"}]})
        return 1

    # The identity gate runs before everything else in this function --
    # nothing else is computed for a report that will not be judged. A
    # `predates-the-schema` (or `postdates-the-schema`) verdict emits a
    # payload with no `violations` key at all, never the standard shape; a
    # `tampered` verdict emits exactly one violation and returns
    # immediately, so a digest mismatch is never buried among unrelated
    # findings by continuing on to the rest of the sweep below.
    gate = report_identity_gate(text, lines)
    if gate is not None:
        exit_code, payload = gate
        emit(payload)
        return exit_code

    # `- Supersedes:` is optional and purely additive: reaching this point
    # means the report is already known non-tampered (the gate above
    # returned `None`), so `integrity_fields.get("selfDigest")` is the
    # report's genuine, recomputation-agreeing self-digest, and a forged
    # `- Supersedes:` would already have been caught upstream as `tampered`
    # -- it is automatically covered by `report_self_digest`'s hashing,
    # since only `- Self-digest:` itself is ever excluded. `"supersession"`
    # is a closed three-value roster -- `not-claimed`, `unverified`, or
    # `verified` -- never a boolean: a boolean would collapse "nobody
    # claimed a supersession" into "a claim exists that nobody checked",
    # the exact defect this field exists to remove.
    supersedes_claim = integrity_fields.get("supersedes")
    supersession = "not-claimed"
    supersedes_claim_ok = False
    if supersedes_claim is not None:
        supersession = "unverified"
        if not SUPERSEDES_VALUE_SHAPE.match(supersedes_claim):
            fail("supersedes",
                 f"'- Supersedes: {supersedes_claim}' is not shaped "
                 "'sha256:<hex>'", f"{path}:1")
        else:
            supersedes_claim_ok = True

    # `--supersedes-report <path>` checks a well-formed, non-self-referential
    # claim against a NAMED companion report: re-derive the companion's own
    # self-digest via the exact same `report_self_digest` this tool signs
    # its own reports with -- no second digest convention -- and compare it
    # to the declared value. A malformed or self-referential claim is
    # already its own violation above; this block never layers a second,
    # confusing verdict on top of one (G2's ordering: inability and
    # mismatch never share an outcome with an already-broken claim).
    #
    # Ordering inside this branch, load-bearing: inability to look always
    # precedes an ordinary violation, consistent with this skill's own
    # standing rule that "could not look" never shares an outcome with
    # "looked and found wrong" -- (1) the flag names a report that carries
    # no claim at all is its own violation, checked first, with no
    # companion read attempted; then, once a companion read is attempted,
    # (2) unreadable, (3) schema predates/postdates, (4) either side's
    # `- Subject:` absent are each `Unprobeable`, before (5) a digest
    # mismatch or (6) a subject mismatch are ever considered as ordinary
    # violations, with (7) verified only once every earlier check agrees.
    supersedes_report_path = getattr(args, "supersedes_report", None)
    if supersedes_report_path:
        if supersedes_claim is None:
            fail("supersedes",
                 f"'--supersedes-report {supersedes_report_path}' was "
                 "supplied, but the report carries no '- Supersedes:' "
                 "claim to check", f"{path}:1")
        elif supersedes_claim_ok:
            try:
                companion_text = Path(supersedes_report_path).read_text(
                    encoding="utf-8")
            except OSError as error:
                raise Unprobeable(
                    f"the named companion at {supersedes_report_path!r} "
                    f"could not be read: {error}")

            companion_lines = companion_text.splitlines()
            companion_fields = report_integrity_fields(companion_lines)
            companion_schema = (
                companion_fields.get("schema") if companion_fields else None)
            classification = schema_version_classification(companion_schema)
            if classification in ("absent", "predates"):
                raise Unprobeable(
                    f"the named companion at {supersedes_report_path!r} "
                    "predates the schema (no current '## Report integrity' "
                    "section); its self-digest cannot be judged")
            if classification == "postdates":
                current = f"skill-audit-report/{REPORT_SCHEMA_VERSION}"
                raise Unprobeable(
                    f"the named companion at {supersedes_report_path!r} "
                    f"declares schema {companion_schema!r}, which postdates "
                    f"the schema this tool ships ({current!r}); its "
                    "self-digest cannot be judged")

            this_frozen = frozen_section_fields(lines)
            companion_frozen = frozen_section_fields(companion_lines)
            this_subject = this_frozen.get("subject")
            companion_subject = companion_frozen.get("subject")
            if not this_subject or not companion_subject:
                absent_side = ("this report" if not this_subject
                              else "the named companion")
                raise Unprobeable(
                    f"{absent_side}'s '## Frozen' carries no '- Subject:' "
                    "line; comparability cannot be judged without it")

            companion_self_digest = report_self_digest(companion_text)
            if companion_self_digest != supersedes_claim:
                fail("supersedes",
                     f"the named companion at {supersedes_report_path!r} "
                     f"re-derives to {companion_self_digest}, which "
                     f"disagrees with the declared '- Supersedes: "
                     f"{supersedes_claim}'", f"{path}:1")
            elif this_subject != companion_subject:
                fail("supersedes",
                     f"the named companion's '- Subject: "
                     f"{companion_subject}' disagrees with this report's "
                     f"own '- Subject: {this_subject}'; a re-validation "
                     "must be of the same subject, never merely of the "
                     "same self-digest match", f"{path}:1")
            else:
                supersession = "verified"

    # `## Report integrity` must be the report's first `## ` section: the
    # schema marker governs every later judgment, so a validator that must
    # scan the whole file to learn which shape it is reading has already
    # read it under an assumption. Checked only once the gate above has
    # already confirmed the section is present and its identity is valid --
    # a misplaced-but-valid section is an ordinary violation, appended to
    # the same list the rest of this sweep builds, never a second gate.
    first_heading = next((line for line in lines if line.startswith("## ")), None)
    if first_heading != REPORT_INTEGRITY_HEADING:
        fail("report-integrity",
             f"{REPORT_INTEGRITY_HEADING!r} must be the report's first "
             f"'## ' section; found {first_heading!r} first", f"{path}:1")

    # Both doctrine tables are resolved up front: the moves table for
    # `## Move outcomes` below, and the stages table for which
    # `REPORT_SHAPE` items are conditional at all. Unprobeable propagates
    # from either: a missing or unparseable table is an inability to look,
    # not a pass.
    moves_path = resolve_moves_doctrine(getattr(args, "moves", None))
    required_moves = move_roster(moves_path.read_text(encoding="utf-8"))
    required_stages = stage_roster(
        resolve_stages_doctrine().read_text(encoding="utf-8"))

    # An item is conditional exactly when the stages table names it in a
    # `Demands` cell -- derived from `required_stages` rather than a second
    # hand-written set, so a stage added to the table without its own
    # `REPORT_SHAPE` key changes nothing here and a stage naming an
    # existing key is exempted from the unconditional sweep automatically.
    # `PRE_SWEEP_ITEMS` is excluded the same way: `report-integrity` is
    # judged entirely by the gate above, never by this loop.
    conditional_items = {key for _, key in required_stages}

    for item, marker in REPORT_SHAPE.items():
        if item in conditional_items or item in PRE_SWEEP_ITEMS:
            continue
        if marker.startswith("## ") and marker not in lines:
            fail(item, f"the report carries no {marker!r} section",
                 f"{path}:1")

    # `--subject` is optional: without it, `rederived` stays `false`, borrowing
    # `comparison: not-run`'s idiom rather than silently weakening the check,
    # and only a finding's own digest is held to `## Frozen`'s declared one.
    frozen = frozen_section_fields(lines)
    rederived = False
    if getattr(args, "subject", None) and frozen.get("digest"):
        actual = frozen_digest(
            Path(args.subject).resolve(),
            parse_exclude_field(frozen.get("exclude", "(none)")))
        rederived = True
        if actual != frozen["digest"]:
            fail("frozen",
                 f"the subject at {args.subject!r} re-derives to {actual}, "
                 f"which disagrees with '## Frozen''s declared digest "
                 f"{frozen['digest']}", f"{path}:1")

    findings = report_findings(lines)
    if not findings:
        fail("ranked-findings", "the report names no finding at all",
             f"{path}:1")

    confirmed = False
    # Populated by the per-finding `remedy` check below, keyed by vocabulary
    # token; consumed after the loop by the derived-roster cross-check
    # (Commit 2). Declared here, unconditionally, so a report with zero
    # Move-6 not-adjudicable findings correctly derives three empty buckets
    # rather than a missing name.
    remedy_by_bucket = {"delete": [], "update": [], "undecided": []}
    for finding in findings:
        where = f"{path}:{finding['line']} {finding['label']}"
        body = "\n".join(finding["text"])

        move = re.search(r"^- Move:\s*(\d+)\s*$", body, re.MULTILINE)
        if not move:
            fail("move-number",
                 "every finding names the move that found it", where)

        # Condition 10, scoped to `- Move: 6` alone -- never also gated on
        # `- Adjudication: not adjudicable` the way `remedy` is below. A
        # lock that fires is a clean result, not a finding under `## Not
        # adjudicable`, and this binds both outcomes: whatever Move 6
        # reports, it must say reachability was proven, never coverage.
        reachability = re.search(
            r"^- Reachability:\s*(.+?)\s*$", body, re.MULTILINE)
        reachability_in_scope = move is not None and move.group(1) == "6"
        if reachability_in_scope:
            if not reachability:
                fail("reachability",
                     f"finding {finding['label']} carries '- Move: 6' but "
                     "no '- Reachability:' line; every substitution-probe "
                     "finding must state whether it proves the lock fires "
                     "or stayed silent, and what that does not prove",
                     where)
            else:
                prefix = reachability.group(1).split(":", 1)[0].strip()
                if prefix not in REACHABILITY_VALUES:
                    fail("reachability",
                         f"finding {finding['label']}'s "
                         f"'- Reachability: {reachability.group(1)}' does "
                         "not open with fires | silent, the closed "
                         "reachability vocabulary", where)
        elif reachability:
            fail("reachability",
                 f"finding {finding['label']} carries "
                 f"'- Reachability: {reachability.group(1)}' outside its "
                 "exact scope ('- Move: 6'); the field is refused on any "
                 "other finding", where)

        marker = re.search(r"^- Evidence:\s*(.+?)\s*$", body, re.MULTILINE)
        value = marker.group(1) if marker else ""
        if value == "CONFIRMED by execution":
            confirmed = True
        elif value != "read-only":
            fail("evidence-marker",
                 "every finding carries `CONFIRMED by execution` or "
                 "`read-only`, and there is no default: a missing marker is "
                 "never read as confirmed", where)

        found_by = re.search(r"^- Found by:\s*(.+?)\s*$", body, re.MULTILINE)
        if not found_by or found_by.group(1) not in FOUND_BY_VALUES:
            fail("found-by",
                 "every finding carries `- Found by: both | one | "
                 "not-compared`, and there is no default: a missing marker "
                 "is never read as `one`", where)

        verdict = re.search(r"^- Adjudication:\s*(.+?)\s*$", body, re.MULTILINE)
        if not verdict or verdict.group(1) not in ADJUDICATIONS:
            fail("adjudication",
                 "every finding carries exactly one adjudication from "
                 + ", ".join(ADJUDICATIONS), where)
        elif (verdict.group(1) == "not adjudicable") \
                != (finding["section"] == "## Not adjudicable"):
            # Mirrors the `## Undecidable` <-> `## Move outcomes`
            # cross-section rule: a `not adjudicable` finding cannot have
            # two homes. Either direction of the mismatch is refused --
            # this section without that adjudication, or that adjudication
            # outside this section.
            fail("not-adjudicable",
                 f"finding {finding['label']}'s adjudication is "
                 f"{verdict.group(1)!r} but it sits under "
                 f"{finding['section']!r}; a `not adjudicable` finding "
                 "belongs under '## Not adjudicable' and nowhere else",
                 where)

        # Move 6's own occasion, scoped tightly: `- Remedy:` is required iff
        # a finding carries both `- Move: 6` and `- Adjudication: not
        # adjudicable`, and refused everywhere else -- bidirectional,
        # mirroring the `not-adjudicable` cross-section rule right above.
        # `remedy_by_bucket` accumulates the in-scope labels this loop finds,
        # by vocabulary token, for the derived-roster cross-check after the
        # loop; grouping ignores an `undecided` finding's own reason text.
        remedy = re.search(r"^- Remedy:\s*(.+?)\s*$", body, re.MULTILINE)
        remedy_in_scope = (
            move is not None and move.group(1) == "6"
            and verdict is not None and verdict.group(1) == "not adjudicable")
        if remedy_in_scope:
            if not remedy:
                fail("remedy",
                     f"finding {finding['label']} carries '- Move: 6' and "
                     "'- Adjudication: not adjudicable' but no "
                     "'- Remedy:' line; the field is required in exactly "
                     "this scope", where)
            else:
                value = remedy.group(1)
                if value in ("delete", "update"):
                    remedy_by_bucket[value].append(finding["label"])
                elif value == "undecided" or value.startswith("undecided:"):
                    reason = value.split(":", 1)[1].strip() \
                        if ":" in value else ""
                    if not reason:
                        fail("remedy",
                             f"finding {finding['label']}'s "
                             "'- Remedy: undecided' carries no reason; a "
                             "bare `undecided` is refused, matching this "
                             "repo's own idiom for every other escape "
                             "hatch (`Unprobeable`, `no-closed-roster`, "
                             "'## Unchecked')", where)
                    elif not any(cause in reason
                                for cause in UNDISTINGUISHED_CAUSES):
                        # Condition 9: proving the bytes moved (condition 2)
                        # is not proving behaviour moved. A reason naming
                        # none of the three causes -- or stating none could
                        # be determined -- defaults to nothing; stricter
                        # than accepting any non-empty string.
                        fail("remedy",
                             f"finding {finding['label']}'s "
                             f"'- Remedy: undecided: {reason}' names none "
                             "of the three causes (obsolete guard | "
                             "equivalent mutant | degenerate fixture) and "
                             "does not state that none could be "
                             "determined", where)
                    else:
                        remedy_by_bucket["undecided"].append(finding["label"])
                else:
                    fail("remedy",
                         f"finding {finding['label']}'s "
                         f"'- Remedy: {value}' is outside the vocabulary "
                         "delete | update | undecided: <reason>", where)
        elif remedy:
            fail("remedy",
                 f"finding {finding['label']} carries "
                 f"'- Remedy: {remedy.group(1)}' outside its exact scope "
                 "('- Move: 6' and '- Adjudication: not adjudicable'); "
                 "the field is refused on any other finding", where)

        citations = {c for c in CITATION.findall(body)}
        if len(citations) < 2:
            fail("ranked-findings",
                 "a finding names both halves at `file:line`; naming one half "
                 f"makes it a candidate, not a finding (saw {sorted(citations)})",
                 where)

        digest = re.search(r"^- Digest:\s*(\S+)\s*$", body, re.MULTILINE)
        if digest and frozen.get("digest") and digest.group(1) != frozen["digest"]:
            fail("frozen",
                 f"finding {finding['label']}'s digest {digest.group(1)} "
                 f"disagrees with '## Frozen''s declared digest "
                 f"{frozen['digest']}", where)

        # The differential drive's asymmetry, enforced structurally: the
        # skill-less drive never ran the skill's own machinery, so a
        # finding attributed to it can never make a claim with the subject
        # itself as its target -- that pairing is a category error
        # regardless of whether the differential-drive stage is declared
        # ran or skipped in this report.
        drive = re.search(r"^- Drive:\s*(.+?)\s*$", body, re.MULTILINE)
        target = re.search(r"^- Target:\s*(.+?)\s*$", body, re.MULTILINE)
        if (drive and target and drive.group(1) == "skill-less"
                and target.group(1) == "subject"):
            fail("drives",
                 f"finding {finding['label']} attributes itself to the "
                 "skill-less drive while naming the subject as its "
                 "target; that drive never ran the skill's own machinery "
                 "and cannot make a claim with the subject as its target",
                 where)

    # The three derived rosters, cross-checked against `remedy_by_bucket`
    # (populated above, per finding): required, matching exactly, iff at
    # least one Move-6 not-adjudicable finding exists; forbidden otherwise.
    # Reuses the `"remedy"` violation item -- mirrors how `"not-adjudicable"`
    # already covers both directions of its own cross-section rule, rather
    # than inventing a second item id for the same capability.
    rosters = not_adjudicable_roster_lines(lines)
    has_move6_findings = any(remedy_by_bucket.values())
    if has_move6_findings:
        for bucket in ("delete", "update", "undecided"):
            raw = rosters.get(bucket)
            expected = sorted(remedy_by_bucket[bucket])
            if raw is None:
                fail("remedy",
                     f"'## Not adjudicable' carries a Move-6 finding but no "
                     f"'- {bucket.capitalize()}:' roster line; expected "
                     f"{expected!r}", f"{path}:1")
                continue
            actual = roster_labels(raw)
            if actual != expected:
                fail("remedy",
                     f"'- {bucket.capitalize()}:' names {actual!r}, but the "
                     f"matching Move-6 findings are {expected!r}",
                     f"{path}:1")
    elif rosters:
        fail("remedy",
             "'## Not adjudicable' carries a Delete/Update/Undecided "
             "roster line but no Move-6 not-adjudicable finding to "
             "justify it", f"{path}:1")

    if findings and not confirmed:
        head = [line for line in lines[:6] if line.strip()]
        if not any(NO_CONFIRMED_DECLARATION in line for line in head):
            fail("evidence-marker",
                 "no finding is CONFIRMED by execution, so the report must say "
                 f"so in its first line: {NO_CONFIRMED_DECLARATION!r}",
                 f"{path}:1")

    # `## Disputed severity` is a bare heading: an empty section demands
    # nothing, because a surface nobody looked at and a surface both drives
    # agreed on must not read the same way. Non-empty means each dispute is
    # recorded as exactly two `- Position:` lines, each citing `file:line`,
    # verbatim -- no ranking, no ladder of any kind.
    has_disputes, dispute_positions = disputed_severity_positions(lines)
    if has_disputes:
        if not dispute_positions or len(dispute_positions) % 2 != 0:
            fail("disputed-severity",
                 "'## Disputed severity' records each dispute as exactly "
                 "two '- Position:' lines; found an unpaired count "
                 f"({len(dispute_positions)})", f"{path}:1")
        for position in dispute_positions:
            if not CITATION.search(position):
                fail("disputed-severity",
                     f"a '- Position:' line carries no `file:line` "
                     f"citation, verbatim: {position!r}", f"{path}:1")

    # Every move required by the moves table this run is pointed at -- this
    # skill's own SKILL.md by default -- needs its own row in `## Move
    # outcomes`, `ran` or `skipped` with a reason.
    outcomes = move_outcome_rows(lines)
    for move in required_moves:
        outcome = outcomes.get(move)
        if outcome is None:
            fail("move-outcomes",
                 f"move {move} has no row in '## Move outcomes'; every move "
                 "the moves table names must be `ran` or `skipped: <reason>`, "
                 "never absent", f"{path}:1")
        elif outcome.startswith("skipped:") and not outcome.split(":", 1)[1].strip():
            fail("move-outcomes",
                 f"move {move}'s row is `skipped` with an empty reason; a "
                 "move attempted zero times must say why", f"{path}:1")

    # Every stage the stages table names needs its own row in `## Stage
    # outcomes`, `ran` or `skipped` with a reason -- mirrors the move-
    # outcomes check exactly. Only a `ran` row then demands the artifact
    # its own `Demands` cell names: a `## ` marker means a required
    # section, a `- ` marker means the field's declared not-run value is
    # no longer accepted anywhere in the report.
    stage_outcomes = stage_outcome_rows(lines)
    for stage_id, key in required_stages:
        outcome = stage_outcomes.get(stage_id)
        if outcome is None:
            fail("stage-outcomes",
                 f"stage {stage_id} has no row in '## Stage outcomes'; "
                 "every stage the stages table names must be `ran` or "
                 "`skipped: <reason>`, never absent", f"{path}:1")
            continue
        if outcome.startswith("skipped:") and not outcome.split(":", 1)[1].strip():
            fail("stage-outcomes",
                 f"stage {stage_id}'s row is `skipped` with an empty "
                 "reason; a stage attempted zero times must say why",
                 f"{path}:1")
            continue
        if outcome != "ran":
            continue
        marker = REPORT_SHAPE[key]
        if marker.startswith("## "):
            if marker not in lines:
                fail(key,
                     f"stage {stage_id} is declared ran, so the report "
                     f"must carry {marker!r}", f"{path}:1")
            elif key == "user-drive":
                # The enforceable half: `## User drive`'s own `- Digest:`
                # must agree with `## Frozen`'s, exactly as every finding's
                # own `- Digest:` already must -- proof the driven-audit
                # narrative is about the same subject state as the rest of
                # the report.
                drive_digest = user_drive_digest(lines)
                if not drive_digest or (frozen.get("digest")
                                        and drive_digest != frozen["digest"]):
                    fail(key,
                         "'## User drive' carries no '- Digest:' agreeing "
                         f"with '## Frozen''s declared digest "
                         f"{frozen.get('digest')!r}", f"{path}:1")
                # The declared-only half: stated, never implied as proof.
                # A drive claiming to have proven everything has misread
                # what it did, so an empty column is refused the same as
                # an absent one.
                if not user_drive_declared_only_nonempty(lines):
                    fail(key,
                         "'## User drive' carries no non-empty "
                         f"{USER_DRIVE_DECLARED_HEADING!r} content; the "
                         "declared-only column must be stated, never "
                         "implied as proof", f"{path}:1")
                # R4's structural half: stated, `(none)` included, never
                # left blank -- item-conditional on this same stage-2
                # branch, so it opens no REPORT_SHAPE door of its own.
                if not user_drive_subsection_only_nonempty(
                        lines, USER_DRIVE_DEMANDED_HEADING):
                    fail(key,
                         "'## User drive' carries no non-empty "
                         f"{USER_DRIVE_DEMANDED_HEADING!r} content; R4's "
                         "structural half must be stated explicitly, "
                         "'(none)' included, never left blank", f"{path}:1")
        else:
            not_run_value = FIELD_NOT_RUN.get(key)
            if not_run_value:
                for finding in findings:
                    body = "\n".join(finding["text"])
                    field = re.search(r"^- Found by:\s*(.+?)\s*$", body,
                                      re.MULTILINE)
                    if field and field.group(1) == not_run_value:
                        fail(key,
                             f"stage {stage_id} is declared ran, so "
                             f"finding {finding['label']}'s "
                             f"'- Found by: {not_run_value}' is no longer "
                             "accepted",
                             f"{path}:{finding['line']} {finding['label']}")

    # The binding ruling: an audit never reports on a subject without
    # driving it. Derived structurally -- the `user-drive` stage id is
    # whichever row in `required_stages` names that key, never a hardcoded
    # `"2"` -- so a future renumbering moves this check along with the
    # table it reads, exactly like every other stage check above.
    drive_stage_id = next(
        (stage_id for stage_id, key in required_stages if key == "user-drive"),
        None)
    if drive_stage_id is not None:
        drive_outcome = stage_outcomes.get(drive_stage_id)
        if drive_outcome is not None and drive_outcome.startswith("skipped:"):
            drive_reason = drive_outcome.split(":", 1)[1].strip()
            if drive_reason != DRIVE_STAGE_RESERVED_SKIP:
                fail("driver-required",
                     f"stage {drive_stage_id}'s row reads "
                     f"'skipped: {drive_reason}'; an audit never reports "
                     "on a subject without driving it, and the only "
                     f"accepted skip reason is {DRIVE_STAGE_RESERVED_SKIP!r}",
                     f"{path}:1")
            else:
                undecidable_id = next(
                    (stage_id for stage_id, key in required_stages
                     if key == "undecidable"), None)
                stage1_ran = (undecidable_id is not None
                             and stage_outcomes.get(undecidable_id) == "ran")
                entries = undecidable_entries(lines)
                all_no_closed_roster = bool(entries) and all(
                    entry["surfaceKind"] == "no-closed-roster"
                    for entry in entries)
                if not (stage1_ran and all_no_closed_roster):
                    fail("driver-required",
                         f"stage {drive_stage_id}'s row reads "
                         f"'skipped: {DRIVE_STAGE_RESERVED_SKIP}', which is "
                         "only valid when stage 1 ran and '## Undecidable' "
                         "is non-empty with every entry's '- Kind:' reading "
                         "'no-closed-roster'; an empty '## Undecidable' is "
                         "not the same claim as one full of them",
                         f"{path}:1")

        # `skipped: offered, declined` is the one skip text legal only
        # after the drive itself reached agreement -- equivalence reached
        # is what makes the question worth asking. Scoped to stages
        # numbered *after* the drive stage, derived the same way, never a
        # hardcoded "3, 4, 5": stage 2's own row already cannot carry this
        # text at all, since it must equal `DRIVE_STAGE_RESERVED_SKIP`
        # exactly or fail as `driver-required` above.
        drive_agreed = (stage_outcomes.get(drive_stage_id) == "ran"
                       and user_drive_outcome(lines) == "agree")
        for stage_id, key in required_stages:
            if int(stage_id) <= int(drive_stage_id):
                continue
            outcome = stage_outcomes.get(stage_id)
            if not outcome or not outcome.startswith("skipped:"):
                continue
            if outcome.split(":", 1)[1].strip() != POST_DRIVE_OFFERED_SKIP:
                continue
            if not drive_agreed:
                fail(key,
                     f"stage {stage_id}'s row reads "
                     f"'skipped: {POST_DRIVE_OFFERED_SKIP}', which is legal "
                     f"only once stage {drive_stage_id} reads `ran` and "
                     "'## User drive''s own '- Outcome:' reads `agree`; "
                     "no question was asked here", f"{path}:1")

    # The one cross-section rule: an `## Undecidable` entry claiming
    # `- Rung: probe` must name a move whose own `## Move outcomes` row is
    # `ran`. Declaring a probe was the answer and then skipping the move it
    # names is refused, structurally.
    for entry in undecidable_entries(lines):
        # The partition is total over what this tool emits, held by
        # `EscalationPartitionTests`. A report is written by hand, so the same
        # closed set has to be enforced on the way in as well; otherwise a
        # surface can be declared undecidable under a reason that exists
        # nowhere, and `## Undecidable` stops meaning what the tool means.
        if entry["surfaceKind"] not in ESCALATION_BUCKETS["escalatable"]:
            fail("undecidable",
                 f"an '## Undecidable' entry names kind "
                 f"{entry['surfaceKind']!r}, which is not one this tool can "
                 "emit as escalatable; only a surface the tool could not "
                 "decide belongs here", f"{path}:1")
        if entry["rung"] != "probe":
            continue
        probe_move = entry["probe"]
        if not probe_move or outcomes.get(probe_move) != "ran":
            fail("undecidable",
                 "an '## Undecidable' entry claims rung `probe` naming "
                 f"move {probe_move!r}, but that move's '## Move outcomes' "
                 "row is not `ran`; a probe cannot be the answer for a "
                 "move that never ran", f"{path}:1")

    # `## Repair units`: every `### F<n>.` block belongs to exactly one unit,
    # and each unit's own changed-line forecast is an integer.
    finding_labels = {finding["label"] for finding in findings}
    units = repair_unit_rows(text)
    if units is not None:
        coverage = {}
        for row in units:
            unit = row[0] if row else ""
            findings_cell = row[1] if len(row) > 1 else ""
            forecast_cell = row[2] if len(row) > 2 else ""
            labels = [label.strip() for label in findings_cell.split(",")
                     if label.strip()]
            if not labels:
                fail("repair-units",
                     f"repair unit {unit!r} names no finding", f"{path}:1")
            for label in labels:
                if label not in finding_labels:
                    fail("repair-units",
                         f"repair unit {unit!r} names {label!r}, which "
                         "matches no finding in this report", f"{path}:1")
                    continue
                coverage[label] = coverage.get(label, 0) + 1
            if not re.fullmatch(r"-?\d+", forecast_cell.strip()):
                fail("repair-units",
                     f"repair unit {unit!r} carries a non-integer "
                     f"changed-line forecast: {forecast_cell!r}", f"{path}:1")
        for label in sorted(finding_labels):
            count = coverage.get(label, 0)
            if count != 1:
                fail("repair-units",
                     f"finding {label} is named by {count} repair units, not "
                     "exactly one", f"{path}:1")
    elif "## Repair units" in lines:
        fail("repair-units",
             f"the report carries '## Repair units' but no "
             f"{REPAIR_UNITS_HEADER!r} table beneath it", f"{path}:1")

    for index, line in enumerate(lines, start=1):
        for item, (pattern, detail) in FORBIDDEN_SUPPORT.items():
            if not pattern.search(line):
                continue
            if item == "single-harness-count" and all(
                    harness.search(line) for harness in BOTH_HARNESSES):
                continue
            fail(item, detail, f"{path}:{index}")

    emit({"rederived": rederived, "supersession": supersession, "violations": sorted(
        violations, key=lambda v: (v["item"], v["where"]))})
    return 1 if violations else 0


DISPATCH = {
    "roster": run_roster,
    "check-report": run_check_report,
    "structure": run_structure,
    "walkthrough": run_walkthrough,
    "reading-diff": run_reading_diff,
    "sensitivity": run_sensitivity,
    "inversion": run_inversion,
    "exits": run_exits,
    "enumeration-reach": run_enumeration_reach,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    try:
        return DISPATCH[args.command](args)
    except Unprobeable as error:
        emit({"error": str(error), "status": "unprobeable"})
        return 2


if __name__ == "__main__":
    sys.exit(main())
