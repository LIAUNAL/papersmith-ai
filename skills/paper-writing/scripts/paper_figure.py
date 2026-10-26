"""paper_figure: diagram source/manifest layout, the two-way manifest
cross-check, the data-figure boundary's source-side stop (stop A), and the
per-figure-id repair-budget ledger.

Owns no subprocess of its own — that is `paper_latex.py`'s exclusive
privilege (design.md, "three skill-local modules, none of them in
`_core/`"); this module calls `paper_latex.compile()` and interprets its
`CompileResult`.

An ordinary repairable compile failure (exit != 0, a diagnostic explains
it, the package is not simply absent, and the budget is not yet exhausted)
is reported as a successful CLI call (`"status": "ok"`) carrying
`"verdict": "failure"` and the diagnostics — spending a budget attempt is
the ordinary cost of the authoring loop, not a guard blocking anything.
Only these become `Refused` (exit 2): the toolchain/log/package absences,
`DIAGRAM_PLOTS_DATA`, `MANIFEST_SOURCE_MISMATCH`, `LATEX_OUTCOME_UNEXPLAINED`,
and `REPAIR_BUDGET_SPENT` once the fifth repairable attempt is requested.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_latex  # noqa: E402
import paper_tikz  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: Four repairable `latexmk` compiles per figure id (proposal.md, "A repair
#: budget of four compiles per figure id"). Keyed to the id ALONE — every
#: attempt for this id counts against the same ledger regardless of the
#: source digest at the time, which is the whole point of
#: `REPAIR_BUDGET_SPENT`'s "editing the source between attempts MUST NOT
#: reset the count" (`authored-diagram` spec). The operator's bound, never
#: an agent's to widen.
REPAIR_BUDGET = 4

#: Stop A, source side of the data-figure boundary (design.md, "the
#: data-figure boundary is two stops, and neither subsumes the other").
_PLOTTING_PACKAGES = ("pgfplots", "pgfplotstable")
_USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}")
_AXIS_ENV_RE = re.compile(r"\\begin\{axis\}")
_EXTERNAL_READ_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\\addplot\s+table"),
    re.compile(r"\\pgfplotstableread"),
    re.compile(r"\\csvreader"),
)
_INPUT_ESCAPE_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_COORDINATES_BLOCK_RE = re.compile(r"coordinates\s*\{([^}]*)\}", re.DOTALL)
_NUMERIC_PAIR_RE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")
#: More than this many numeric pairs in one `coordinates{...}` block reads
#: as an embedded data series rather than a small illustrative sketch (a
#: handful of points placing boxes on a canvas is normal TikZ; a series
#: this long is a plotted result).
_COORDINATE_SERIES_THRESHOLD = 4

#: A node this manifest/source cross-check recognizes: a comment marker
#: `% node: <label>` the diagram author places beside each declared
#: component. This skill parses no real TikZ grammar — the marker is this
#: skill's own, deliberately simple grammar for "what this source declares
#: as a component," analogous to how `paper_block.py` never parses LaTeX
#: either and instead reads its own marker comments.
_NODE_MARKER_RE = re.compile(r"%\s*node:\s*(\S+)")


def figure_paths(paper_dir: Path, figure_id: str) -> dict:
    """Every path one figure id resolves to (`authored-diagram` spec,
    `Requirement: Source Layout`).

    A figure id is a NAME, never a path or an option: an empty id, one
    containing `/`, `\\` or a NUL, one beginning with `-`, or the ids
    `.`/`..` refuses `DIAGRAM_SOURCE_ABSENT` —
    the code this module already uses for "this call cannot address a
    diagram source" (same as `read_manifest`) — so nothing interpolates
    out of `Figures/` or `.paper-writing/figures/`."""
    if (
        not figure_id
        or "/" in figure_id
        or "\\" in figure_id
        or "\x00" in figure_id
        or figure_id in {".", ".."}
    ):
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{figure_id!r} is not a single path segment; a figure id is a name, never a path",
        )
    if figure_id.startswith("-"):
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{figure_id!r} begins with '-'; latexmk would read <id>.tex as an option",
        )
    figures_dir = paper_dir / "Figures"
    scratch_dir = paper_dir / ".paper-writing" / "figures" / figure_id
    return {
        "tex": figures_dir / f"{figure_id}.tex",
        "manifest": figures_dir / f"{figure_id}.diagram.json",
        "pdf": figures_dir / f"{figure_id}.pdf",
        "scratch": scratch_dir,
        "ledger": scratch_dir / "ledger.json",
    }


def read_manifest(paths: dict) -> dict:
    """Refuses `DIAGRAM_SOURCE_ABSENT` when `<id>.diagram.json` names no
    matching `<id>.tex` (`authored-diagram` spec, `Scenario: Manifest
    without source refuses`)."""
    if not paths["tex"].is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{paths['tex']} does not exist for this manifest")
    return json.loads(paths["manifest"].read_text(encoding="utf-8"))


def _tex_nodes(tex_text: str) -> set:
    return set(_NODE_MARKER_RE.findall(tex_text))


def cross_check_manifest(manifest: dict, tex_text: str) -> None:
    """Both directions (`diagram-obligation` spec, `Requirement: Manifest
    Crossed With Source, Both Directions`): a declared label absent from
    the source, or a node in the source absent from the manifest, refuses
    `MANIFEST_SOURCE_MISMATCH` naming the label(s) and the direction."""
    declared = set(manifest.get("components", []))
    present = _tex_nodes(tex_text)
    missing_in_source = sorted(declared - present)
    if missing_in_source:
        raise Refused(
            "MANIFEST_SOURCE_MISMATCH",
            f"declared in the manifest, absent from the source: {missing_in_source}",
        )
    missing_in_manifest = sorted(present - declared)
    if missing_in_manifest:
        raise Refused(
            "MANIFEST_SOURCE_MISMATCH",
            f"present in the source, undeclared in the manifest: {missing_in_manifest}",
        )


def _resolves_inside_figures(target: str) -> bool:
    if target.startswith("/"):
        return False
    return ".." not in Path(target).parts


def scan_data_boundary(tex_text: str) -> None:
    """Stop A: refuses `DIAGRAM_PLOTS_DATA` on a plotting package, a
    `\\begin{axis}`, an external table read, an `\\input`/`\\include`
    escaping `paper/Figures/`, or an embedded coordinate series over the
    threshold (`authored-diagram` spec, `Requirement: Data-Figure
    Boundary`)."""
    for usepackage_match in _USEPACKAGE_RE.finditer(tex_text):
        packages = {name.strip() for name in usepackage_match.group(1).split(",")}
        for plotting_package in _PLOTTING_PACKAGES:
            if plotting_package in packages:
                raise Refused("DIAGRAM_PLOTS_DATA", f"loads plotting package {plotting_package!r}")
    if _AXIS_ENV_RE.search(tex_text):
        raise Refused("DIAGRAM_PLOTS_DATA", "declares a pgfplots \\begin{axis} environment")
    for pattern in _EXTERNAL_READ_PATTERNS:
        if pattern.search(tex_text):
            raise Refused("DIAGRAM_PLOTS_DATA", f"reads an external table via {pattern.pattern!r}")
    for input_match in _INPUT_ESCAPE_RE.finditer(tex_text):
        target = input_match.group(1)
        if not _resolves_inside_figures(target):
            raise Refused(
                "DIAGRAM_PLOTS_DATA", f"\\input/\\include escapes paper/Figures/: {target!r}",
            )
    for series_match in _COORDINATES_BLOCK_RE.finditer(tex_text):
        pairs = _NUMERIC_PAIR_RE.findall(series_match.group(1))
        if len(pairs) > _COORDINATE_SERIES_THRESHOLD:
            raise Refused(
                "DIAGRAM_PLOTS_DATA", f"embeds a {len(pairs)}-point coordinate series",
            )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_replace(path: Path, data: bytes) -> None:
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=path.name + ".")
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


def _read_ledger(ledger_path: Path) -> dict:
    if not ledger_path.is_file():
        return {"attempts": []}
    return json.loads(ledger_path.read_text(encoding="utf-8"))


def _write_ledger(ledger_path: Path, ledger: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_replace(ledger_path, json.dumps(ledger, indent=2).encode("utf-8"))


def acknowledge_reset(paths: dict, figure_id: str) -> dict:
    """The only exit from a spent ledger: an explicit operator
    acknowledgement (`authored-diagram` spec, `Scenario: Acknowledgement
    clears the ledger`). Deleting the ledger file IS the acknowledgement,
    made explicit rather than pretended-secure (design.md, "nothing under
    `paper/` is tamper-proof")."""
    if paths["ledger"].is_file():
        paths["ledger"].unlink()
    return {"figureId": figure_id, "ledgerReset": True}


def _package_diagnostic(diagnostics: tuple) -> object | None:
    for diagnostic in diagnostics:
        if diagnostic.kind == "package":
            return diagnostic
    return None


def render(paper_dir: Path, figure_id: str, *, path: str | None = None) -> dict:
    """The whole `render` pipeline for one figure id: layout resolution,
    the manifest cross-check, stop A, the compile, and the budget ledger.

    Refuses (never spends budget): `DIAGRAM_SOURCE_ABSENT`,
    `MANIFEST_SOURCE_MISMATCH`, `DIAGRAM_PLOTS_DATA` (all pre-compile),
    `LATEX_TOOLCHAIN_ABSENT`, `LATEX_LOG_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED`,
    `LATEX_PACKAGE_ABSENT` (a missing `.sty` "cannot be fixed by redrawing",
    `authored-diagram` spec, `Requirement: Package Absence Spends Nothing`).
    Refuses, spending the fifth attempt: `REPAIR_BUDGET_SPENT`. Returns a
    plain dict (never `Refused`) for a clean success OR an ordinary
    repairable failure within budget — the latter IS the loop's ordinary
    cost, not a guard blocking anything (module docstring).
    """
    paths = figure_paths(paper_dir, figure_id)
    manifest = read_manifest(paths)
    tex_text = paths["tex"].read_text(encoding="utf-8")
    cross_check_manifest(manifest, tex_text)
    scan_data_boundary(tex_text)

    source_digest = _digest(tex_text)
    ledger = _read_ledger(paths["ledger"])
    attempts = list(ledger.get("attempts", []))

    # The budget is checked BEFORE spawning another compile -- a spent
    # ledger refuses without wasting a fifth `latexmk` call, which is the
    # whole point of a REPAIR budget (`authored-diagram` spec, `Requirement:
    # Repair Budget Ledger`). Keyed to the id alone: `attempts` above is
    # NEVER filtered by `source_digest`, so editing the source between
    # attempts cannot reset the count (`DiagramMutationProofTests`,
    # "budget keyed to (id, sourceDigest) instead of id").
    if len(attempts) >= REPAIR_BUDGET:
        raise Refused(
            "REPAIR_BUDGET_SPENT",
            "budget of "
            f"{REPAIR_BUDGET} compiles spent for {figure_id!r}; "
            f"diagnostics={[a['diagnostics'] for a in attempts]} "
            f"digests={[a['sourceDigest'] for a in attempts]}",
        )

    result = paper_latex.compile(paths["tex"].parent, figure_id, paths["scratch"], path=path)

    if result.verdict == "unexplained":
        raise Refused(
            "LATEX_OUTCOME_UNEXPLAINED",
            f"exit={result.exit_code} pdfWritten={result.pdf_written} "
            f"diagnostics={len(result.diagnostics)} unrecognizedLines={result.unrecognized_lines} "
            f"log={result.log_path}",
        )

    if result.verdict == "success":
        pdf_bytes = (paths["scratch"] / f"{figure_id}.pdf").read_bytes()
        paths["pdf"].parent.mkdir(parents=True, exist_ok=True)
        paths["pdf"].write_bytes(pdf_bytes)
        return {
            "figureId": figure_id, "pdf": str(paths["pdf"]), "verdict": "success",
            "ledgerCreated": bool(attempts), "attemptsUsed": len(attempts),
        }

    # result.verdict == "failure": a repairable outcome, or a package
    # absence that spends nothing.
    package_diag = _package_diagnostic(result.diagnostics)
    if package_diag is not None:
        raise Refused(
            "LATEX_PACKAGE_ABSENT",
            f"{package_diag.message}; the budget is unchanged at {len(attempts)}/{REPAIR_BUDGET}",
        )

    attempts.append({
        "sourceDigest": source_digest,
        "diagnostics": [d.message for d in result.diagnostics],
        "at": datetime.now(timezone.utc).isoformat(),
    })
    _write_ledger(paths["ledger"], {"attempts": attempts})
    return {
        "figureId": figure_id, "verdict": "failure", "attemptsUsed": len(attempts),
        "budgetRemaining": REPAIR_BUDGET - len(attempts),
        "diagnostics": [d.message for d in result.diagnostics],
    }


def render_optimized_text(tex_path: Path, *, strip_comments: bool = False) -> dict:
    """Dry run: the optimized candidate text for one source path, writing
    nothing.

    The CLI's `--file` route and its `--no-write` route both land here. The
    guards and the compile belong to `optimize_figure` below and a dry run
    deliberately performs neither — it answers "what would optimization
    do to this file", and nothing else.
    """
    tex_text = tex_path.read_text(encoding="utf-8")
    result = paper_tikz.optimize(tex_text, strip_comments=strip_comments)
    return {
        "figureId": tex_path.stem,
        "text": result.text,
        "changes": list(result.changes),
        "librariesAdded": list(result.libraries_added),
        "librariesRemoved": list(result.libraries_removed),
        "stylesFactored": list(result.styles_factored),
        "warnings": list(result.warnings),
    }


def optimize_source(
    tex_path: Path, *, manifest: dict | None = None, strip_comments: bool = False,
    compile_candidate: bool = True, output: Path | None = None, path: str | None = None,
) -> dict:
    """The whole `optimize` pipeline for one source path: transform, the two
    always-run guards, compile-validation, and an atomic commit.

    `paper_tikz.optimize` is a pure function; everything that could make a
    rewrite unsafe-to-commit is decided here, and none of it is skipped by
    a flag:

    1. `cross_check_manifest` and `scan_data_boundary` run on the CANDIDATE,
       unconditionally — before the compile and, importantly, **also under
       `compile_candidate=False`**. Both are pure text checks, independent
       of the compiler, so the `--no-compile` shortcut skips the compiler
       and nothing else. A candidate failing either is discarded with the
       original left byte-identical (refusals `MANIFEST_SOURCE_MISMATCH` /
       `DIAGRAM_PLOTS_DATA` — existing codes, never a new one).
    2. The candidate is compiled from a staging directory under the real
       `<id>.tex` name (`latexmk` resolves the source by name, so the name
       is not negotiable), and only a `success` verdict reaches the atomic
       commit. A compile failure is the loop's ordinary cost, not a guard:
       it returns `verdict: "rolled_back"` with the diagnostics, exactly as
       `render` reports a repairable failure — never a `Refused`, and never
       a partial write.

    `output` redirects the commit to another path (`--output`); `None`
    means in place. `path` is `paper_latex.compile`'s own injectable
    `latexmk` search path, test-only, same as `render`'s.
    """
    source = Path(tex_path)
    if not source.is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{source} does not exist")

    original = source.read_text(encoding="utf-8")
    figure_id = source.stem
    result = paper_tikz.optimize(original, strip_comments=strip_comments)
    candidate = result.text
    target = Path(output) if output is not None else source

    # Always-run, compile-independent guards. Deliberately BEFORE the
    # `candidate == original` short-circuit: a source that is already
    # optimal still has to be a legal diagram, and reporting "unchanged"
    # for a source stop A would refuse would be a false green. The manifest
    # cross-check applies only where a manifest exists (`--figure-id`); the
    # bare `--file` case has none to check against, which is a different
    # fact from skipping the check.
    if manifest is not None:
        cross_check_manifest(manifest, candidate)
    scan_data_boundary(candidate)

    report = {
        "figureId": figure_id,
        "changes": list(result.changes),
        "librariesAdded": list(result.libraries_added),
        "librariesRemoved": list(result.libraries_removed),
        "stylesFactored": list(result.styles_factored),
        "warnings": list(result.warnings),
    }

    if candidate == original:
        return {**report, "verdict": "unchanged", "written": None, "compiled": False}

    if compile_candidate:
        # A private staging tree: `latexmk` resolves the source by its own
        # name, so the candidate is compiled as the real `<id>.tex` inside a
        # throwaway directory rather than anywhere under `paper/`.
        with tempfile.TemporaryDirectory(prefix="paper-tikz-") as tmp:
            staging = Path(tmp) / "src"
            staging.mkdir(parents=True, exist_ok=True)
            (staging / f"{figure_id}.tex").write_text(candidate, encoding="utf-8")
            compiled = paper_latex.compile(staging, figure_id, Path(tmp) / "out", path=path)
        if compiled.verdict != "success":
            return {
                **report,
                "verdict": "rolled_back",
                "written": None,
                "compiled": True,
                "diagnostics": [diagnostic.message for diagnostic in compiled.diagnostics],
            }

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_replace(target, candidate.encode("utf-8"))
    return {
        **report, "verdict": "committed", "written": str(target), "compiled": bool(compile_candidate),
    }


def optimize_figure(
    paper_dir: Path, figure_id: str, *, strip_comments: bool = False,
    compile_candidate: bool = True, output: Path | None = None, path: str | None = None,
) -> dict:
    """`optimize_source` for one figure id, with its manifest cross-check.

    The id-keyed entry point exists so the happy path — "optimize the
    diagram this block's contract declares" — cannot accidentally skip the
    manifest check: the manifest is read here, from the layout this skill
    already owns, and handed to `optimize_source` as a non-optional fact.
    """
    paths = figure_paths(paper_dir, figure_id)
    if not paths["tex"].is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{paths['tex']} does not exist")
    manifest = read_manifest(paths)
    return optimize_source(
        paths["tex"], manifest=manifest, output=output,
        strip_comments=strip_comments, compile_candidate=compile_candidate, path=path,
    )


def place_figure(paper_dir: Path, figure_id: str, pdf_source: Path, provenance_source: Path) -> dict:
    """Placing a measured figure — compiles nothing, requires provenance
    naming the run that produced it (`authored-diagram` spec, `Requirement:
    Data-Figure Boundary`: "Placing a measured figure MUST use a separate
    verb that compiles nothing and requires provenance naming the run that
    produced it"). Entirely outside the compile path: no `latexmk` call, no
    ledger, no stop-A scan — the diagram-authoring loop and the
    measured-figure path never share a code path (proposal.md's own
    "Two independent stops" risk mitigation).

    Reuses `DIAGRAM_SOURCE_ABSENT` for a missing `--pdf`/`--provenance`
    source or a provenance record that names no run: the same code already
    means "the named diagram artifact this call needs is absent," and this
    is the placement path's own instance of exactly that condition — never
    a second code for one condition (design.md's own convention, `Refusal
    codes and their classification`).
    """
    if not pdf_source.is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{pdf_source} does not exist")
    if not provenance_source.is_file():
        raise Refused("DIAGRAM_SOURCE_ABSENT", f"{provenance_source} does not exist")
    provenance = json.loads(provenance_source.read_text(encoding="utf-8"))
    if not provenance.get("run"):
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT", f"{provenance_source} names no 'run' the figure came from"
        )

    paths = figure_paths(paper_dir, figure_id)
    paths["pdf"].parent.mkdir(parents=True, exist_ok=True)
    paths["pdf"].write_bytes(pdf_source.read_bytes())
    provenance_dest = paths["pdf"].with_suffix(".provenance.json")
    provenance_dest.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return {"figureId": figure_id, "pdf": str(paths["pdf"]), "provenance": str(provenance_dest)}
