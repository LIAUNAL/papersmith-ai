"""paper_latex: toolchain discovery, the one `latexmk` subprocess call, log
parsing, and the three-signal verdict.

The sole module this skill lets import `subprocess` — an AST scan in
`tests/test_paper_writing.py` (`NoSubprocessScanTests`) holds every other
`scripts/*.py` file to zero `subprocess`/`os.system`/`os.popen`/`os.exec*`/
`multiprocessing` imports, with this file as the one named exception
(`SUBPROCESS_EXCEPTIONS`). `paper_figure.py` calls `compile()` below; it
never spawns a process of its own (`a-diagram-that-compiles-or-says-why`
design.md, "three skill-local modules, none of them in `_core/`").

The compile's verdict never comes from the parser alone: exit status,
whether `<id>.pdf` was written, and whether the log's diagnostics explain
either outcome must all agree. Disagreement — a failed exit with zero
explained diagnostics, or a clean exit with errors parsed — refuses
`LATEX_OUTCOME_UNEXPLAINED` rather than silently reading as one or the
other (design.md, "the compile's verdict never comes from the parser").
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: `latexmk -norc -g -pdf -interaction=nonstopmode -file-line-error
#: -outdir=<scratch> <id>.tex`, cwd = `paper/Figures/` (design.md, "the
#: compile's verdict never comes from the parser"). `-norc` because a
#: `~/.latexmkrc` would make the invocation machine-dependent; `-g` because
#: latexmk skipping an up-to-date target hands back a PREVIOUS run's log
#: while spending a repair-budget attempt against stale evidence
#: (`LatexStaleLogTests`, tasks.md 1.3).
_LATEXMK_FLAGS = ("-norc", "-g", "-pdf", "-interaction=nonstopmode", "-file-line-error")

#: The child environment `latexmk`/pdfTeX runs under, on top of a copy of
#: this process's own `os.environ` — the second half of the data-figure
#: boundary's reachability stop (design.md, "Stop B — reachability"):
#: `openin_any=p`/`openout_any=p` restrict kpathsea's OWN path search,
#: `shell_escape=f` forbids `\write18` (measured against a real TeX Live
#: 2026 install: `shell_escape=f` genuinely blocks `\write18`, confirmed by
#: a real compile attempt producing no side-effect file).
#:
#: **Measured limit, not assumed**: `openin_any=p` does NOT block a literal
#: absolute-path `\input{/abs/path}` on this real engine — kpathsea's
#: "paranoid" search restriction never triggers because an explicit
#: absolute path never goes through its search algorithm at all. Stop A
#: (`paper_figure.scan_data_boundary`'s `\input`/`\include` escape check)
#: is therefore the PRIMARY, load-bearing defense against that specific
#: vector — a pre-compile source-text refusal, not something left resting
#: on this env var. These three vars stay set regardless (design.md's own
#: required invocation shape, and real defense-in-depth against a filename
#: stop A's regex does not enumerate — a macro-built path, `\write18`).
_SANDBOX_ENV = {"openin_any": "p", "openout_any": "p", "shell_escape": "f"}

#: `-file-line-error`'s own line shape: `<file>:<line>: <message>`, for `!`
#: errors (`authored-diagram` spec, `Requirement: Standalone Compile`).
_ERROR_LINE_RE = re.compile(r"^(?P<file>\S+):(?P<line>\d+):\s*(?P<message>.+)$")

#: `Overfull \hbox (...) in paragraph at lines A--B` (and `\vbox`), mapped
#: to A — the precedent's own rule, adopted verbatim (proposal.md, "What the
#: precedent gives").
_OVERFULL_RE = re.compile(
    r"Overfull \\(?:hbox|vbox) \([^)]*\) in paragraph at lines (?P<start>\d+)--\d+"
)

#: A missing `.sty`/`.cls` reported inside an otherwise-ordinary
#: `-file-line-error` line. Detected as a SUBCLASS of an "error" diagnostic
#: (the same regex matches it first), never a separate top-level pattern —
#: one real log line, one classification.
_PACKAGE_ABSENT_RE = re.compile(r"File `([^']+)' not found")

#: Measured against a REAL `latexmk`/pdfTeX run (tier-1 fixture
#: `tests/fixtures/paper-figure/failure_package/`), not assumed: a missing
#: package's `! LaTeX Error: File `X.sty' not found.` line carries NO
#: `<file>:<line>:` prefix at all -- `-file-line-error` does not reformat
#: it, because kpathsea hits it before TeX has a current input line to
#: report. The generic error regex above never matches this line; without
#: this second pattern it would silently fall through to
#: `unrecognizedLines`, and `LATEX_PACKAGE_ABSENT` would never fire --
#: exactly the false-green this skill's own tier-1 evidence exists to
#: catch.
_BARE_PACKAGE_ABSENT_RE = re.compile(r"^! LaTeX Error: File `([^']+)' not found\.$")


@dataclass(frozen=True)
class Diagnostic:
    """One line the log parser could explain. `kind` is `"error"`
    (`!`-class, `-file-line-error`-formatted), `"package"` (an `"error"`
    whose message also matches `_PACKAGE_ABSENT_RE`), or `"overfull"` (a
    warning, never blocking). `line` is `None` only when a pattern carries
    no source line of its own — none currently do, but the field stays
    optional rather than a sentinel int."""

    kind: str
    line: int | None
    message: str


@dataclass(frozen=True)
class CompileResult:
    """What `compile()` returns on a call that actually ran (never on a
    `Refused` path — `LATEX_TOOLCHAIN_ABSENT`/`LATEX_LOG_ABSENT` are raised
    before this is constructed). `verdict` is `"success"`, `"failure"`
    (repairable — `paper_figure.py`'s ledger owns what happens next), or
    `"unexplained"` (the three signals disagree; `paper_figure.render`
    refuses `LATEX_OUTCOME_UNEXPLAINED` on this and spends no budget)."""

    exit_code: int
    pdf_written: bool
    log_path: Path
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)
    unrecognized_lines: int = 0
    verdict: str = "unexplained"


def discover_latexmk(path: str | None) -> str:
    """Resolves the `latexmk` binary via `shutil.which`, through an
    INJECTABLE `path` (never read from `os.environ["PATH"]` implicitly —
    `shutil.which(name, path=None)` already falls back to the real `PATH`
    on its own, which is what the production call site relies on).

    Refuses `LATEX_TOOLCHAIN_ABSENT` (work-state) naming the binary sought
    and the exact `PATH` searched, never a skip or a silent pass
    (`authored-diagram` spec, `Requirement: Toolchain Absence Refusal`).
    """
    searched = path if path is not None else os.environ.get("PATH", "")
    found = shutil.which("latexmk", path=path)
    if found is None:
        raise Refused(
            "LATEX_TOOLCHAIN_ABSENT",
            f"latexmk not found; searched PATH={searched!r}",
        )
    return found


#: Where a TeX Live install keeps its binaries when the calling shell's
#: `PATH` does not carry them -- the same list `experiment-diagrams`'
#: `diagram_cli.py` searches (macOS MacTeX symlinks, Homebrew, versioned
#: `texlive/<year>/bin/<arch>` trees).
TOOL_FALLBACK_DIRS: tuple = (
    "/Library/TeX/texbin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/local/texlive/*/bin/*",
    "/opt/texlive/*/bin/*",
    "~/texlive/*/bin/*",
)


def discover_kpsewhich(path: str | None = None, fallback_dirs: tuple = TOOL_FALLBACK_DIRS) -> str | None:
    """Finds `kpsewhich` on the injectable `path` (default: the real `PATH`),
    then in `fallback_dirs` (glob patterns, `~` expanded). Returns `None`
    rather than refusing: `venue acquire` names its own refusal for "no
    TeX Live here" (`TEXLIVE_UNAVAILABLE`), distinct from "TeX Live has no
    such class" (`TEMPLATE_ABSENT`).
    """
    found = shutil.which("kpsewhich", path=path)
    if found:
        return found
    for pattern in fallback_dirs:
        expanded = os.path.expanduser(pattern)
        for directory in sorted(glob.glob(expanded)):
            candidate = os.path.join(directory, "kpsewhich")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def kpsewhich_lookup(binary: str, filename: str, timeout: float = 30) -> str | None:
    """One `kpsewhich <filename>` call: the resolved absolute path, or `None`
    when TeX Live does not carry the file. `filename` is never an option:
    a leading `-` or a path separator returns `None` without a spawn.
    """
    if not filename or filename.startswith("-") or "/" in filename or "\\" in filename:
        return None
    try:
        proc = subprocess.run(
            [binary, filename], capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[0] if lines else None


def resolve_texlive_file(
    filename: str, *, path: str | None = None, fallback_dirs: tuple = TOOL_FALLBACK_DIRS,
) -> str | None:
    """`discover_kpsewhich` then `kpsewhich_lookup`, `None` on either miss."""
    binary = discover_kpsewhich(path, fallback_dirs)
    if binary is None:
        return None
    return kpsewhich_lookup(binary, filename)


def parse_log(log_text: str) -> tuple[tuple[Diagnostic, ...], int]:
    """Extracts every diagnostic this parser can explain, plus a count of
    lines it could NOT — `unrecognizedLines`, scoped to lines that open with
    `!` (LaTeX's own error-announcement prefix) and matched neither the
    `-file-line-error` shape nor an Overfull warning. Ordinary log noise
    (banners, package-loading chatter) is not "unrecognized": it never
    claimed to be a diagnostic in the first place, and counting every
    non-matching line would make `unrecognizedLines` fire on every real log
    ever produced (design.md, "Unrecognized lines are counted and
    published, never dropped" — scoped here to the class of line that COULD
    have been a diagnostic).
    """
    diagnostics: list[Diagnostic] = []
    unrecognized = 0
    for raw_line in log_text.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        match = _ERROR_LINE_RE.match(line)
        if match:
            message = match.group("message")
            line_no = int(match.group("line"))
            kind = "package" if _PACKAGE_ABSENT_RE.search(message) else "error"
            diagnostics.append(Diagnostic(kind, line_no, message))
            continue
        bare_package_match = _BARE_PACKAGE_ABSENT_RE.match(line.strip())
        if bare_package_match:
            # No source line: this message precedes TeX ever reaching one
            # (real behaviour, measured above -- never a guess).
            diagnostics.append(Diagnostic("package", None, line.strip()))
            continue
        overfull_match = _OVERFULL_RE.search(line)
        if overfull_match:
            diagnostics.append(Diagnostic("overfull", int(overfull_match.group("start")), line.strip()))
            continue
        if line.startswith("!"):
            unrecognized += 1
    return tuple(diagnostics), unrecognized


def classify_verdict(exit_code: int, pdf_written: bool, diagnostics: tuple[Diagnostic, ...]) -> str:
    """The three-signal verdict, as a pure function over already-parsed
    data — independently testable with hand-constructed `Diagnostic`
    tuples, which is legitimate (they are structured arithmetic inputs, not
    a claim about a real `latexmk` run) where authoring a raw log fixture
    is not (design.md, "A fixture log authored by the same hand that
    parses it passes vacuously").
    """
    blocking = any(d.kind in ("error", "package") for d in diagnostics)
    if exit_code == 0 and pdf_written and not blocking:
        return "success"
    if exit_code != 0 and blocking:
        return "failure"
    return "unexplained"


def compile(
    figure_dir: Path, figure_id: str, scratch_dir: Path, *, path: str | None = None,
    timeout: float = 300,
) -> CompileResult:
    """Exactly one `latexmk` invocation against `<id>.tex`, cwd =
    `figure_dir` (`paper/Figures/`), `-outdir` = `scratch_dir`
    (`paper/.paper-writing/figures/<id>/`).

    The scratch `.log` is deleted before the spawn (never trusted as
    "already there"); no log after the call refuses `LATEX_LOG_ABSENT`
    rather than reading an absent log as either verdict. `FileNotFoundError`
    at spawn time — the binary vanished between `discover_latexmk` and this
    call — maps to the SAME `LATEX_TOOLCHAIN_ABSENT` code, never a second
    one for a race that reads identically to the caller. An id beginning
    with `-` refuses `DIAGRAM_SOURCE_ABSENT` before anything runs.
    """
    if figure_id.startswith("-"):
        # `<id>.tex` is a positional argument; a leading `-` would make
        # latexmk read it as an option. Rejected before discovery or any
        # write -- `figure optimize --file` reaches here with the file stem,
        # never through `paper_figure.figure_paths`' own name check.
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{figure_id!r} begins with '-'; latexmk would read it as an option",
        )
    binary = discover_latexmk(path)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    log_path = scratch_dir / f"{figure_id}.log"
    if log_path.exists():
        log_path.unlink()
    pdf_path = scratch_dir / f"{figure_id}.pdf"

    argv = [binary, *_LATEXMK_FLAGS, f"-outdir={scratch_dir}", f"{figure_id}.tex"]
    env = dict(os.environ)
    env.update(_SANDBOX_ENV)
    try:
        proc = subprocess.run(
            argv, cwd=str(figure_dir), env=env, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        raise Refused(
            "LATEX_TOOLCHAIN_ABSENT",
            f"{binary} vanished between discovery and spawn",
        )

    if not log_path.is_file():
        raise Refused("LATEX_LOG_ABSENT", f"no log produced at {log_path} after the compile call")

    diagnostics, unrecognized = parse_log(log_path.read_text(encoding="utf-8", errors="replace"))
    pdf_written = pdf_path.is_file()
    verdict = classify_verdict(proc.returncode, pdf_written, diagnostics)
    return CompileResult(
        exit_code=proc.returncode, pdf_written=pdf_written, log_path=log_path,
        diagnostics=diagnostics, unrecognized_lines=unrecognized, verdict=verdict,
    )


# ---------------------------------------------------------------------------
# Table source lint (spec S5 of `odd/tasks/figure-and-table-quality.md`).
#
# A table never shrinks to fit the text block: no `\resizebox`/`\scalebox`/
# `adjustbox` below a factor of 0.85 or to a width, and no size switch inside
# a table that prints below 0.70 times the body size. The floor comes from
# `skills/_core/figure/print_scale.py` (imported, never copied), the same
# rule figures are measured against. The lint WARNS, never refuses: the
# write gate already treats typographic diagnostics that way (an `Overfull`
# box above is a non-blocking `Diagnostic`), the body size it compares
# against is read from `main.tex` and may be a fallback, and the compiled
# manuscript QA (`skills/_core/figure/manuscript_qa.py`) is what measures
# the printed result.
# ---------------------------------------------------------------------------

def _print_scale():
    """`skills/_core/figure/print_scale.py`, imported on first lint, never
    at module load: this module is the compile seam every figure path and
    the mutation harnesses import, and they must not need `_core/figure`
    (nor pypdfium2) to compile a diagram."""
    figure_dir = str(Path(__file__).resolve().parents[2] / "_core" / "figure")
    if figure_dir not in sys.path:
        sys.path.insert(0, figure_dir)
    import print_scale  # noqa: PLC0415

    return print_scale

#: Scaling at or above this factor is tolerated; below it the text shrinks
#: past what the section contracts allow.
TABLE_MIN_SCALE = 0.85

#: Printed size of LaTeX's relative size switches, in TeX points, for the
#: standard classes' 10/11/12 pt bodies (`size10.clo`, `size11.clo`,
#: `size12.clo`). Other bodies scale the 10 pt row proportionally.
_SIZE_SWITCH_PT = {
    10.0: {"tiny": 5.0, "scriptsize": 7.0, "footnotesize": 8.0, "small": 9.0,
           "normalsize": 10.0, "large": 12.0, "Large": 14.4, "LARGE": 17.28,
           "huge": 20.74, "Huge": 24.88},
    11.0: {"tiny": 6.0, "scriptsize": 8.0, "footnotesize": 9.0, "small": 10.0,
           "normalsize": 10.95, "large": 12.0, "Large": 14.4, "LARGE": 17.28,
           "huge": 20.74, "Huge": 24.88},
    12.0: {"tiny": 6.0, "scriptsize": 8.0, "footnotesize": 10.0, "small": 10.95,
           "normalsize": 12.0, "large": 14.4, "Large": 17.28, "LARGE": 20.74,
           "huge": 24.88, "Huge": 24.88},
}

_TABLE_ENV_RE = re.compile(
    r"\\begin\{(?P<env>table\*?|sidewaystable\*?|tabular[x*]?|tabulary|longtable)\}"
)
_TABULAR_RE = re.compile(r"\\begin\{(?:tabular[x*]?|tabulary|longtable)\}")
_SIZE_SWITCH_RE = re.compile(
    r"\\(?P<name>tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)(?![A-Za-z])"
    r"|\\fontsize\s*\{\s*(?P<fontsize>[0-9]*\.?[0-9]+)\s*(?:pt)?\s*\}"
)
_SCALEBOX_RE = re.compile(r"\\scalebox\s*\{")
_RESIZEBOX_RE = re.compile(r"\\resizebox\*?\s*\{")
_ADJUSTBOX_ENV_RE = re.compile(r"\\begin\{adjustbox\}\s*\{")
_ADJUSTBOX_CMD_RE = re.compile(r"\\adjustbox\s*\{")
_ADJUST_SCALE_RE = re.compile(r"(?:^|,)\s*scale\s*=\s*\{?\s*(?P<factor>[0-9]*\.?[0-9]+)")
_ADJUST_WIDTH_RE = re.compile(r"(?:^|,)\s*(?:max\s+)?(?:width|totalheight|height)\s*=")


def _size_switch_pt(name: str, body_pt: float) -> float:
    if name == "normalsize":
        return float(body_pt)
    row = _SIZE_SWITCH_PT.get(float(body_pt))
    if row is not None:
        return row[name]
    return _SIZE_SWITCH_PT[10.0][name] * float(body_pt) / 10.0


def _brace_group(text: str, open_index: int) -> tuple[int, int] | None:
    """`(start, end)` of the content of the brace group opening at
    `open_index` (which holds `{`), or `None` when it never closes. An
    escaped `\\{`/`\\}` does not count."""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_index + 1, index
        index += 1
    return None


def _next_group(text: str, index: int) -> tuple[int, int] | None:
    """The next `{...}` group at or after `index`, skipping whitespace and
    one optional `[...]` argument."""
    while index < len(text) and text[index].isspace():
        index += 1
    if index < len(text) and text[index] == "[":
        close = text.find("]", index)
        if close < 0:
            return None
        index = close + 1
        while index < len(text) and text[index].isspace():
            index += 1
    if index < len(text) and text[index] == "{":
        return _brace_group(text, index)
    return None


def _wraps_tabular(text: str, group: tuple[int, int] | None) -> bool:
    return bool(group) and _TABULAR_RE.search(text, group[0], group[1]) is not None


def _table_regions(latex: str) -> list[tuple[int, int]]:
    regions = []
    for match in _TABLE_ENV_RE.finditer(latex):
        end = latex.find("\\end{" + match.group("env") + "}", match.end())
        regions.append((match.start(), len(latex) if end < 0 else end))
    return regions


def _finding(latex: str, index: int, rule: str, command: str, **extra) -> dict:
    start = latex.rfind("\n", 0, index) + 1
    end = latex.find("\n", index)
    snippet = (latex[start:] if end < 0 else latex[start:end]).strip()[:160]
    line = latex.count("\n", 0, index) + 1
    return {"rule": rule, "line": line, "command": command, "snippet": snippet, **extra}


def lint_tables(latex: str, body_pt: float) -> list[dict]:
    """Every table-sizing finding in `latex`, in source order. Rules:

    - `table-scaled-to-width`: `\\resizebox`, or an `adjustbox` width or
      height key, wrapping a tabular (the factor is unknowable from the
      source and the text shrinks with the box);
    - `table-scaled-below-floor`: `\\scalebox` or `adjustbox` `scale=`
      below `TABLE_MIN_SCALE` wrapping a tabular;
    - `table-font-below-floor`: a size switch (`\\tiny` ... `\\small`, or
      `\\fontsize{<pt>}`) inside a table that prints below
      `print_scale.min_printed_pt(body_pt)`;
    - `table-font-above-cap` (spec S2 of
      `odd/tasks/manuscript-polish-0-54.md`): a size switch inside a table
      that prints above `print_scale.max_printed_pt(body_pt)` (0.90 x body:
      `\\normalsize` and larger always, `\\small` at 11/12 pt), or a table
      that declares no size at all and so prints at the body size (one
      finding at its opening, command `\\normalsize (default)`). A float
      resets its font to `\\normalsize`, so only a switch inside the
      outermost table environment counts.

    Each finding: `{"rule", "line" (1-based in `latex`), "command",
    "snippet"}` plus `factor`, `size_pt`/`min_printed_pt` or
    `size_pt`/`max_printed_pt`."""
    findings: list[dict] = []
    floor = _print_scale().min_printed_pt(body_pt)
    cap = _print_scale().max_printed_pt(body_pt)

    for match in _SCALEBOX_RE.finditer(latex):
        factor_group = _brace_group(latex, match.end() - 1)
        if factor_group is None:
            continue
        try:
            factor = float(latex[factor_group[0]:factor_group[1]].strip())
        except ValueError:
            continue
        content = _next_group(latex, factor_group[1] + 1)
        if factor < TABLE_MIN_SCALE and _wraps_tabular(latex, content):
            findings.append(_finding(latex, match.start(), "table-scaled-below-floor",
                                     "\\scalebox", factor=factor))

    for match in _RESIZEBOX_RE.finditer(latex):
        width = _brace_group(latex, match.end() - 1)
        height = _next_group(latex, width[1] + 1) if width else None
        content = _next_group(latex, height[1] + 1) if height else None
        if _wraps_tabular(latex, content):
            findings.append(_finding(latex, match.start(), "table-scaled-to-width", "\\resizebox"))

    for pattern, command in ((_ADJUSTBOX_ENV_RE, "adjustbox"), (_ADJUSTBOX_CMD_RE, "\\adjustbox")):
        for match in pattern.finditer(latex):
            options = _brace_group(latex, match.end() - 1)
            if options is None:
                continue
            if command == "adjustbox":
                end = latex.find("\\end{adjustbox}", options[1])
                content = (options[1], len(latex) if end < 0 else end)
            else:
                content = _next_group(latex, options[1] + 1)
            if not _wraps_tabular(latex, content):
                continue
            keys = latex[options[0]:options[1]]
            scale = _ADJUST_SCALE_RE.search(keys)
            if scale and float(scale.group("factor")) < TABLE_MIN_SCALE:
                findings.append(_finding(latex, match.start(), "table-scaled-below-floor", command,
                                         factor=float(scale.group("factor"))))
            elif _ADJUST_WIDTH_RE.search(keys):
                findings.append(_finding(latex, match.start(), "table-scaled-to-width", command))

    regions = _table_regions(latex)
    outermost = [region for region in regions
                 if not any(other != region and other[0] <= region[0] and region[1] <= other[1]
                            for other in regions)]
    declared = set()
    for match in _SIZE_SWITCH_RE.finditer(latex):
        if not any(start <= match.start() < end for start, end in regions):
            continue
        declared.update(region for region in outermost if region[0] <= match.start() < region[1])
        if match.group("fontsize") is not None:
            size = float(match.group("fontsize"))
            command = "\\fontsize{" + match.group("fontsize") + "}"
        else:
            size = _size_switch_pt(match.group("name"), body_pt)
            command = "\\" + match.group("name")
        if size < floor - 1e-9:
            findings.append(_finding(latex, match.start(), "table-font-below-floor",
                                     command, size_pt=size, min_printed_pt=floor))
        elif size > cap + 1e-9:
            findings.append(_finding(latex, match.start(), "table-font-above-cap",
                                     command, size_pt=size, max_printed_pt=cap))
    for region in outermost:
        if region not in declared:
            findings.append(_finding(latex, region[0], "table-font-above-cap",
                                     "\\normalsize (default)", size_pt=float(body_pt),
                                     max_printed_pt=cap))

    findings.sort(key=lambda finding: finding["line"])
    return findings


def table_lint_report(latex: str, main_tex: Path) -> dict:
    """The write envelope's `tableLint`: the body size read from `main_tex`
    (the 10 pt fallback when it is absent), the floor and the cap of
    the printed range, and `lint_tables`'s findings. `status` is `"clean"` or `"warnings"`; never a refusal."""
    print_scale = _print_scale()
    if Path(main_tex).is_file():
        body, source = print_scale.body_font_pt(Path(main_tex))
    else:
        body, source = print_scale.FALLBACK_BODY_PT, "fallback"
    findings = lint_tables(latex, body)
    return {
        "status": "warnings" if findings else "clean",
        "bodyPt": body,
        "bodySource": source,
        "minPrintedPt": print_scale.min_printed_pt(body),
        "maxPrintedPt": print_scale.max_printed_pt(body),
        "findings": findings,
    }
