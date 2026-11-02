"""paper_tikz: the TikZ optimization transforms — pure text-to-text, no
filesystem, no compile, no CLI (`a-diagram-that-compiles-or-says-why`'s
optimization capability).

This module owns no subprocess and no `Refused` of its own. It is a pure
function library: `optimize()` takes a source string and returns an
`OptimizeResult` carrying the rewritten text plus what changed. The
pipeline that decides whether a rewritten candidate may reach disk —
stop A, the manifest cross-check, the compile, the atomic commit — is
`paper_figure.optimize_figure()`'s, never this module's.

Grammar honesty: like `paper_block.py`, this module does NOT implement a
LaTeX or TikZ grammar. It reads a marker-first source with shallow regexes:
`\\usetikzlibrary{...}` lines, `\\node`/`\\draw`/`\\path` option lists, and
the `% node: <label>` comment markers this skill already treats as its own
declaration grammar (`paper_figure._NODE_MARKER_RE`). A regex rewrite that
claims to be an AST is the failure mode this note exists to prevent.

Two transforms are deliberately conservative, because a naive version of
either silently changes rendering:

* **Library pruning** only ever removes a library this module knows how to
  detect AND whose trigger is absent. A library outside the detection map
  (say `intersections`, `decorations.markings`) is never removed — this
  module cannot prove it unused, so it does not pretend to.
* **`\\tikzset` factoring** only fires on byte-identical option lists that
  carry no positional key, no placeholder, and no baked-in coordinate or
  node reference, and never re-factors a site that already carries a
  generated `ps-` style. Style names are a pure function of the canonical
  options string, which is what makes
  `optimize(optimize(x)).text == optimize(x).text` structural rather than
  hoped for.

Public surface:

    OptimizeResult                                   -> the rewrite and its changes
    scan_libraries(tex) -> set[str]                  -> every \\usetikzlibrary member
    detect_required_libraries(tex) -> set[str]       -> syntax -> library map
    merge_libraries(tex, libs) -> str                -> one deduped, sorted line
    normalize_header(tex) -> (str, tuple[str, ...])  -> standalone-safe header
    strip_directives_and_comments(tex) -> str        -> never drops "% node:" / "%!"
    factor_styles(tex) -> (str, tuple[str, ...])     -> conservative \\tikzset
    scan_memory_guards(tex) -> tuple[str, ...]       -> static, toolchain-independent
    scan_font_switches(tex) -> tuple[str, ...]       -> relative size switches, as warnings
    optimize(tex, *, strip_comments=False) -> OptimizeResult
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: `\usetikzlibrary{a,b}` and `\usetikzlibrary[options]{a,b}`.
_USETIKZLIBRARY_RE = re.compile(r"\\usetikzlibrary(?:\[[^\]]*\])?\{([^}]*)\}")

#: `\documentclass[opts]{class}` — the standalone-safe header this skill's
#: diagrams are authored against.
_DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[(?P<options>[^\]]*)\])?\{(?P<cls>[^}]*)\}")

#: The exact header `normalize_header` inserts when a source declares none.
STANDALONE_HEADER = r"\documentclass[tikz,border=2pt]{standalone}"

#: `\node`/`\draw`/`\path` immediately followed by one bracketed option list.
_OPTIONS_RE = re.compile(r"\\(node|draw|path)(\s*)\[([^\[\]]*)\]")

#: A generated style reference — never re-factored (structural idempotency).
_GENERATED_STYLE_RE = re.compile(r"ps-[0-9a-f]{8}\Z")

#: Positional keys: per-instance by definition, so an option list carrying
#: one can never become a shared style without changing where things land.
_POSITIONAL_KEY_RE = re.compile(r"^(?:at|below|above|left|right|anchor|shift)\b")

#: Syntax -> library. Every entry is a library this module can both DETECT
#: and therefore PRUNE when absent; anything outside this map is only ever
#: added, never removed.
_SYNTAX_LIBRARIES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:below|above|left|right)\s*=[^,\]]*\bof\b"), "positioning"),
    (re.compile(r"\(\s*\$|\$\s*\)"), "calc"),
    (re.compile(r"-\{\s*[A-Za-z][A-Za-z.]*\s*\}"), "arrows.meta"),
    (re.compile(r">=\s*[A-Za-z][A-Za-z.]*"), "arrows.meta"),
    (re.compile(r"\bshape\s*="), "shapes.geometric"),
    (re.compile(r"\bfit\s*="), "fit"),
    (re.compile(r"\bon background layer\b"), "backgrounds"),
    (re.compile(r"\bdecorations?\s*=|\\decorate\b"), "decorations.pathreplacing"),
)

_DETECTABLE_LIBRARIES = frozenset(library for _, library in _SYNTAX_LIBRARIES)

#: Static memory-guard thresholds. Toolchain-independent by construction —
#: see `scan_memory_guards` for the measured M1 result and why no hard TeX
#: memory limit is claimed here.
_FOREACH_COUNT_WARNING = 6
_MACRO_DEFINITION_RE = re.compile(r"\\(?:def|newcommand|renewcommand|providecommand)\s*(\\[A-Za-z@]+)")
_FOREACH_RE = re.compile(r"\\foreach\b")
_PGFMATH_IN_LOOP_RE = re.compile(r"\\foreach\b(?:(?!\\end).)*\\pgfmath", re.DOTALL)
_BOUNDED_INVOKE_RE = re.compile(r"\\pgfplotsinvokeforeach\b")


@dataclass(frozen=True)
class OptimizeResult:
    """One rewrite and its report. `text` is the candidate — never written
    by this module. `changes` is deterministic and human-readable, the
    shape §9.1 tells `diagram-author` to paste into its own report."""

    text: str
    changes: tuple[str, ...] = ()
    libraries_added: tuple[str, ...] = ()
    libraries_removed: tuple[str, ...] = ()
    styles_factored: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _without_comments(tex: str) -> str:
    """`tex` with comment text blanked, for DETECTION only.

    A commented-out `\\draw[->]` must never trigger a library add, and a
    commented-out `\\node[...]` must never be counted as a real site. This
    never touches the text `optimize` returns — detection and rewriting are
    deliberately separate passes.
    """
    out_lines = []
    for line in tex.splitlines():
        index = _comment_index(line)
        out_lines.append(line if index is None else line[:index])
    return "\n".join(out_lines)


def _comment_index(line: str) -> int | None:
    """The index of this line's first unescaped `%`, or `None`. A `\\%` is
    a literal percent, never a comment opener."""
    for index, char in enumerate(line):
        if char != "%":
            continue
        backslashes = 0
        probe = index - 1
        while probe >= 0 and line[probe] == "\\":
            backslashes += 1
            probe -= 1
        if backslashes % 2 == 0:
            return index
    return None


def scan_libraries(tex: str) -> set:
    """Every member of every `\\usetikzlibrary{...}` in `tex`."""
    found: set = set()
    for match in _USETIKZLIBRARY_RE.finditer(tex):
        for name in match.group(1).split(","):
            stripped = name.strip()
            if stripped:
                found.add(stripped)
    return found


def detect_required_libraries(tex: str) -> set:
    """The libraries `tex`'s own syntax requires, per `_SYNTAX_LIBRARIES`.

    Runs against comment-blanked text so a commented-out construct never
    makes this module add a library nobody uses.
    """
    probe = _without_comments(tex)
    required: set = set()
    for pattern, library in _SYNTAX_LIBRARIES:
        if pattern.search(probe):
            required.add(library)
    return required


def _library_line(libraries) -> str:
    return "\\usetikzlibrary{" + ",".join(sorted(libraries)) + "}"


def merge_libraries(tex: str, libraries) -> str:
    """Fold `libraries` into `tex`'s own `\\usetikzlibrary`, deduped and
    sorted for determinism.

    Every existing `\\usetikzlibrary` is collapsed into the LAST one's
    position — the position an author's own last declaration occupied, so a
    preamble that loads libraries after `\\begin{document}` keeps them
    there. A source with none gains one at the END OF THE PREAMBLE (see
    `_insert_into_preamble`), never after `\\begin{document}`.
    """
    wanted = set(libraries)
    existing = scan_libraries(tex)
    if not wanted - existing and len(_USETIKZLIBRARY_RE.findall(tex)) <= 1:
        return tex
    merged = existing | wanted

    matches = list(_USETIKZLIBRARY_RE.finditer(tex))
    if not matches:
        return _insert_into_preamble(tex, _library_line(merged))
    last = matches[-1]
    head, tail = tex[: last.start()], tex[last.end():]
    for match in reversed(matches[:-1]):
        head = head[: match.start()] + head[match.end():]
    return head + _library_line(merged) + tail


def _insert_after_line(tex: str, anchor: str, block: str) -> str:
    """Insert `block` on its own line immediately after the FIRST `anchor`
    line (or at the very top when `anchor` is absent), preserving whether
    the source ended with a newline."""
    index = tex.find(anchor)
    if index == -1:
        return block + "\n" + tex
    line_end = tex.find("\n", index)
    if line_end == -1:
        return tex + "\n" + block + "\n"
    return tex[: line_end + 1] + block + "\n" + tex[line_end + 1:]


def _insert_after_last(tex: str, anchor: str, block: str) -> str:
    """As `_insert_after_line`, but anchored on the LAST occurrence, so a
    preamble that declares the anchor twice gains the block once at the end
    of that run rather than in the middle of it."""
    index = tex.rfind(anchor)
    if index == -1:
        return block + "\n" + tex
    line_end = tex.find("\n", index)
    if line_end == -1:
        return tex + "\n" + block + "\n"
    return tex[: line_end + 1] + block + "\n" + tex[line_end + 1:]


def _insert_into_preamble(tex: str, block: str) -> str:
    """Insert `block` at the END of the preamble: immediately before
    `\\begin{document}` when the source has one, after `\\documentclass`
    when it does not, and at the very top when it has neither.

    A preamble directive placed AFTER `\\begin{document}` is the bug this
    helper exists to prevent. It often still compiles — which is exactly why
    it would go unnoticed until a library that defines preamble-time keys or
    styles was involved, and by then the failure would look like the
    library's fault rather than this one's.
    """
    document_begin = tex.find("\\begin{document}")
    if document_begin != -1:
        line_start = tex.rfind("\n", 0, document_begin) + 1
        return tex[:line_start] + block + "\n" + tex[line_start:]
    class_match = _DOCUMENTCLASS_RE.search(tex)
    if class_match is not None:
        return _insert_after_line(tex, class_match.group(0), block)
    return block + "\n" + tex


def normalize_header(tex: str) -> tuple:
    """Guarantee a standalone-safe header, and report what was done.

    Three cases, deliberately unequal:

    * **No `\\documentclass` at all** — `STANDALONE_HEADER` is inserted and
      a change is reported. A figure source with no header cannot compile
      standalone, and inserting the header this skill authors against is
      the whole point of normalizing.
    * **`standalone` present, `border` absent from its options** — a
      WARNING only. The author's options are not silently rewritten; adding
      a border is a rendering decision, not a normalization.
    * **A different class** — a WARNING only. Swapping an author's
      `article`/`memoir` class for `standalone` changes the document they
      asked for; that is never this module's call to make.
    """
    match = _DOCUMENTCLASS_RE.search(tex)
    if match is None:
        return STANDALONE_HEADER + "\n" + tex, ("inserted a standalone documentclass header",)
    warnings: list = []
    if match.group("cls").strip() != "standalone":
        warnings.append(
            f"documentclass {match.group('cls').strip()!r} is not 'standalone'; "
            "left as authored (optimize never swaps a document class)"
        )
    elif "border" not in (match.group("options") or ""):
        warnings.append(
            "standalone documentclass declares no 'border'; left as authored "
            "(attach a border deliberately, not as a side effect of optimization)"
        )
    return tex, tuple(warnings)


def strip_directives_and_comments(tex: str) -> str:
    """Strip comment text, PRESERVING every marker this skill reads.

    `% node: <label>` is this skill's own declaration grammar and
    `paper_figure.cross_check_manifest` refuses `MANIFEST_SOURCE_MISMATCH`
    in both directions when one goes missing — so a comment stripper that
    removed it would corrupt the manifest contract, not tidy the source.
    `%!` directives (editor/modelines, `latexmk` hints) survive for the
    same reason: they are instructions, not prose.
    """
    out_lines = []
    for line in tex.splitlines():
        index = _comment_index(line)
        if index is None:
            out_lines.append(line)
            continue
        comment = line[index + 1:].strip()
        if comment.startswith("node:") or comment.startswith("!"):
            out_lines.append(line)
            continue
        out_lines.append(line[:index].rstrip())
    return "\n".join(out_lines)


def _split_options(options: str) -> list:
    """Split an option list on top-level commas only. `label={a, b}` is one
    option, not two — a naive `split(",")` would corrupt it."""
    parts: list = []
    depth = 0
    current: list = []
    for char in options:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _canonical_options(options: str) -> str:
    return ", ".join(_split_options(options))


def _is_factorable(options: str) -> bool:
    """Whether one option list may become a shared style.

    The rules, and why each is here rather than a "contains no node name"
    reading that would have forbidden every `\\node[...] (name) {...}` in
    existence:

    * a generated `ps-` reference is never re-factored (idempotency);
    * a positional key is per-instance by definition;
    * `#1` is a placeholder, not a value;
    * **a parenthesis is a coordinate or a node reference** — `fit=(a)(b)`,
      `at (0,0)`, `label={[x]above:(n)}` — and a shared style that baked one
      in would silently attach every site to one specific place. This is
      the rule that actually protects rendering; the node's own NAME sits
      outside its option list and is irrelevant to it.
    """
    parts = _split_options(options)
    if not parts:
        return False
    if any(_GENERATED_STYLE_RE.fullmatch(part) for part in parts):
        return False
    if any(_POSITIONAL_KEY_RE.match(part) for part in parts):
        return False
    if any("#1" in part for part in parts):
        return False
    if any("(" in part or ")" in part for part in parts):
        return False
    return True


def _style_name(canonical: str) -> str:
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]
    return f"ps-{digest}"


def factor_styles(tex: str) -> tuple:
    """Factor byte-identical, non-positional option lists into one
    `\\tikzset`, and report the style names introduced.

    A site is factored only when `_is_factorable` accepts it AND its
    canonical option string appears at least twice. Replacements are
    applied back-to-front so earlier spans keep their offsets, and the
    `\\tikzset` block is inserted once, after the last `\\usetikzlibrary`.
    """
    groups: dict = {}
    for match in _OPTIONS_RE.finditer(tex):
        options = match.group(3)
        if not _is_factorable(options):
            continue
        canonical = _canonical_options(options)
        if not canonical:
            continue
        groups.setdefault(canonical, []).append(match)

    factorable = {name: sites for name, sites in groups.items() if len(sites) >= 2}
    if not factorable:
        return tex, ()

    replacements: list = []
    styles: list = []
    for canonical in sorted(factorable):
        name = _style_name(canonical)
        styles.append(name)
        for match in factorable[canonical]:
            replacements.append((match.start(3) - 1, match.end(3) + 1, f"[{name}]"))

    rewritten = tex
    for start, end, replacement in sorted(replacements, reverse=True):
        rewritten = rewritten[:start] + replacement + rewritten[end:]

    block = "\\tikzset{\n" + "\n".join(
        f"  {_style_name(canonical)}/.style={{{canonical}}}," for canonical in sorted(factorable)
    ) + "\n}"
    if "\\usetikzlibrary" in rewritten:
        rewritten = _insert_after_last(rewritten, "\\usetikzlibrary", block)
    else:
        rewritten = _insert_into_preamble(rewritten, block)
    return rewritten, tuple(styles)


def scan_font_switches(tex: str) -> tuple:
    """Every relative size switch (`\\small`, `\\footnotesize`, ...) outside
    a comment, as warnings.

    A diagram sets every size with an explicit `\\fontsize{<pt>}{<1.2 pt>}`
    computed from the manuscript body size and the width it is included at,
    so each label prints between 0.70 and 0.90 x the body size (spec S3 of
    `figure-and-table-quality`, S2 of `manuscript-polish-0-54`). A relative
    switch means "whatever this class calls small" and cannot be checked
    from the source. The rule and its scanner live in
    `_core/figure/diagram_audit.find_size_switches`, the same one
    `paper_figure.render`'s post-compile audit fails on; this only reports
    it before a compile is spent. Rewriting the size is the author's call.
    """
    import sys
    from pathlib import Path

    core = Path(__file__).resolve().parents[2] / "_core" / "figure"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import diagram_audit  # noqa: E402  (resolved above)

    return tuple(
        f"relative size switch {item['switch']} on line {item['line']}: use an explicit "
        "\\fontsize{<pt>}{<1.2 pt>}\\selectfont sized for the printed width "
        "(render's audit fails on it)"
        for item in diagram_audit.find_size_switches(tex)
    )


def scan_memory_guards(tex: str) -> tuple:
    """Static, toolchain-independent guards, as warnings.

    **What this deliberately does NOT do.** It does not set, claim, or imply
    a hard TeX main-memory limit on this pipeline.

    **M1, measured on the real toolchain rather than assumed** (TeX Live
    2026, the checkout's own `latexmk`):

    * `kpsewhich -var-value=main_memory` answers `5000000` by default and
      `1000` when `main_memory=1000` is exported — so kpathsea DOES read that
      variable from the environment, and it is not a `texmf.cnf`-only knob.
    * `latexmk` has no `--cnf-line` flag, but it does not scrub its child
      environment, so an exported value reaches pdfTeX.
    * **UNPROVEN, and the reason nothing is enforced here:** that a low value
      actually aborts a runaway expansion. A probe document compiled at
      `main_memory=1000` with no complaint, so a low setting is not by itself
      evidence of a working bound. Constructing a document that genuinely
      exhausts TeX's main memory is the experiment that would settle it, and
      it has not been run.

    A guard that claims to stop memory exhaustion without having proven it
    can is worse than no guard: it manufactures confidence. So what ships is
    what was measured — and the real bound this pipeline already enforces is
    `paper_latex.compile`'s own `timeout`.

    What it does instead is name the source shapes that make a runaway
    expansion likely, so `diagram-author` sees them before a compile
    spending budget on them: many `\\foreach` loops in one figure;
    `\\pgfmath` inside a `\\foreach` body (an unbounded per-iteration
    computation); `\\pgfplotsinvokeforeach`, which plots data and is
    therefore already stop A's business — reported here so it is visible,
    never as a substitute for `scan_data_boundary`; and a macro that expands
    to itself, which can never terminate and can never be legitimate.
    """
    warnings: list = []

    loops = len(_FOREACH_RE.findall(_without_comments(tex)))
    if loops > _FOREACH_COUNT_WARNING:
        warnings.append(
            f"{loops} \\foreach loops in one figure (threshold {_FOREACH_COUNT_WARNING}): "
            "this is the shape a runaway macro expansion takes; consider factoring"
        )

    if _PGFMATH_IN_LOOP_RE.search(_without_comments(tex)):
        warnings.append(
            "\\pgfmath inside a \\foreach body: the per-iteration cost is unbounded by "
            "this source, so the compile timeout is the only limit that applies"
        )

    if _BOUNDED_INVOKE_RE.search(_without_comments(tex)):
        warnings.append(
            "\\pgfplotsinvokeforeach reads a data series; stop A (scan_data_boundary) "
            "is the guard that refuses this, never this warning"
        )

    for name in sorted(set(_MACRO_DEFINITION_RE.findall(_without_comments(tex)))):
        body = _without_comments(tex)
        index = body.find(name)
        while index != -1:
            definition = body.find("{", index)
            if definition == -1:
                break
            depth = 0
            cursor = definition
            while cursor < len(body):
                if body[cursor] == "{":
                    depth += 1
                elif body[cursor] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            if name in body[definition:cursor + 1]:
                warnings.append(
                    f"macro {name} expands to itself: this can never terminate and is "
                    "never legitimate; fix the definition before compiling"
                )
                break
            index = body.find(name, cursor + 1)

    return tuple(warnings)


def optimize(tex: str, *, strip_comments: bool = False) -> OptimizeResult:
    """The whole pure pipeline: guards, header, libraries, styles, comments.

    The order matters and is fixed:

    1. **Guards first**, on the source as authored — an author's `% node:`
       markers and real loops are still intact, so the report describes the
       figure they wrote, not a half-rewritten one.
    2. **Header**, so a headerless source gains its `\\begin{document}`
       anchor before any block needs to be inserted after one.
    3. **Libraries**: prune only what the syntax map can PROVE unused, then
       add what the syntax map detects as required.
    4. **Styles**, so the `\\tikzset` lands after the library line this same
       run just consolidated.
    5. **Comments last**, and only when asked — never by default, because
       `% node:` markers are load-bearing.
    """
    warnings = list(scan_memory_guards(tex))
    warnings.extend(scan_font_switches(tex))
    changes: list = []

    current, header_notes = normalize_header(tex)
    changes.extend(header_notes)
    warnings.extend(note for note in header_notes if "left as authored" in note)

    detected = detect_required_libraries(current)
    existing = scan_libraries(current)
    unused = sorted((existing & _DETECTABLE_LIBRARIES) - detected)
    if unused:
        current = _remove_libraries(current, unused)
        changes.append(f"removed unused libraries: {unused}")

    missing = sorted(detected - scan_libraries(current))
    if missing:
        current = merge_libraries(current, missing)
        changes.append(f"added missing libraries: {missing}")

    current, styles = factor_styles(current)
    if styles:
        changes.append(f"factored {len(styles)} shared style(s): {list(styles)}")

    if strip_comments:
        stripped = strip_directives_and_comments(current)
        if stripped != current:
            changes.append("stripped comments (node markers and directives preserved)")
        current = stripped

    return OptimizeResult(
        text=current,
        changes=tuple(changes),
        libraries_added=tuple(missing),
        libraries_removed=tuple(unused),
        styles_factored=styles,
        warnings=tuple(warnings),
    )


def _remove_libraries(tex: str, libraries) -> str:
    """Drop `libraries` from every `\\usetikzlibrary`, collapsing the rest
    into the last declaration's position. Only ever called with members of
    `_DETECTABLE_LIBRARIES` — an unprovable library stays."""
    removal = set(libraries)
    matches = list(_USETIKZLIBRARY_RE.finditer(tex))
    remaining = scan_libraries(tex) - removal
    if not matches:
        return tex
    last = matches[-1]
    head, tail = tex[: last.start()], tex[last.end():]
    for match in reversed(matches[:-1]):
        head = head[: match.start()] + head[match.end():]
    replacement = _library_line(remaining) if remaining else ""
    if not replacement:
        # Consume the removed line's own trailing newline too, so dropping a
        # library does not leave a blank line where it used to be.
        if tail.startswith("\n"):
            tail = tail[1:]
    elif not tail.startswith("\n"):
        replacement += "\n"
    return head + replacement + tail
