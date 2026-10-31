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
