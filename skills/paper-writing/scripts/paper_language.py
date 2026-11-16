"""paper_language: the manuscript is English unless the paper declares otherwise.

Spec S4 of `odd/tasks/manuscript-polish-0-54.md`: no Spanish and no
placeholder text in the manuscript. This module is the one detector both
sides of that promise share:

- the repository's own language guard (`tests/test_language_guard.py`)
  imports `is_spanish` and its lexicon from here, so the heuristic that
  keeps the repository English and the one that keeps the manuscript
  English are one implementation;
- `paper_write.write_block` refuses a draft whose prose is Spanish or that
  still carries a placeholder marker, before any ledger or byte is touched;
- `paper_verify.check_language` reports the same scan over the whole
  `main.tex` (`cmd_verify` resolves it, since `paper_verify` reads nothing);
- `_core/figure/manuscript_qa.py` lists every hit as a `language` or
  `placeholder` finding of the QA report.

The detector is a heuristic, not a parser of Spanish. A line is Spanish
when it opens a question or exclamation with an inverted mark, when it
pairs an accented letter with a Spanish function word, or when it holds
three function words no English sentence uses (`is_spanish`). The
manuscript variant (`is_spanish_prose`) reads a line after LaTeX has been
peeled off it, and counts an accented letter only inside a lowercase word:
a capitalized accented word is a proper name (a surname, an institution),
and `et al.` is Latin, so neither makes a cited author or an affiliation
read as Spanish.

A span the paper itself marks as another language, `\\foreignlanguage{<lang>}{...}`
or an `otherlanguage` environment, is exempt from the Spanish check
(`mask_foreign_spans`); a placeholder inside it still counts.

A paper may declare another language the way LaTeX itself does: the main
language of `babel` (`main=` or the last option) or polyglossia's
`\\setmainlanguage`. A paper whose declared main language is not English
is exempt from the Spanish check; a placeholder marker is a defect in any
language.

Pure: standard library `re` only, no disk access. Callers read the bytes.
"""
from __future__ import annotations

import re

ACCENTED = re.compile(r"[áéíóúñÁÉÍÓÚÑ]")
INVERTED = re.compile(r"[¿¡]\w")
WORD = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)
#: Spanish function words that are not English words either.
STRONG = frozenset(
    "que los las una para pero como esta este esto cuando donde porque desde "
    "hasta entre sus cada hay muy nunca siempre todos toda puede tiene también "
    "más está nada nadie algo eso ese esa así mismo otro otra poder ser igual "
    "parte ya".split())
#: Short Spanish words that collide with English or code on their own, so they
#: only count next to an accented letter.
WEAK = STRONG | frozenset("de la el en y es se lo un al su no del con por sin".split())

#: Declared main languages that are English.
ENGLISH_NAMES = frozenset({
    "english", "american", "british", "usenglish", "ukenglish", "canadian",
    "australian", "newzealand", "en", "en-us", "en-gb",
})

#: Placeholder markers no submitted manuscript carries. The English markers
#: are matched case-sensitively (`todo` is also a Spanish word, judged by the
#: Spanish check instead); the Spanish ones in any case.
PLACEHOLDER_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("por definir", re.compile(r"\b(?:por|a)\s+definir\b", re.IGNORECASE)),
    ("por completar", re.compile(r"\bpor\s+(?:completar|confirmar)\b", re.IGNORECASE)),
    ("pendiente", re.compile(r"\bpendientes?\b", re.IGNORECASE)),
    ("TODO", re.compile(r"\bTODO\b")),
    ("TBD", re.compile(r"\bTBD\b")),
    ("FIXME", re.compile(r"\bFIXME\b")),
)
#: `\todo{...}` (todonotes) is read as the `TODO` marker.
_TODO_COMMAND = re.compile(r"\\todo\b")

#: Environments whose content is not prose.
SKIPPED_ENVIRONMENTS = frozenset({
    "equation", "equation*", "align", "align*", "gather", "gather*", "multline",
    "multline*", "eqnarray", "eqnarray*", "displaymath", "math", "flalign", "flalign*",
    "alignat", "alignat*", "verbatim", "verbatim*", "lstlisting", "minted", "comment",
    "tikzpicture", "thebibliography", "filecontents", "filecontents*",
})
#: Preamble commands whose argument is front matter the reader sees.
FRONT_MATTER = re.compile(r"\\(?:title|author|date|affil|affiliation|address|thanks|keywords)\b")

_COMMENT = re.compile(r"(?<!\\)%.*$")
_BEGIN = re.compile(r"\\begin\{([^}]+)\}")
_END = re.compile(r"\\end\{([^}]+)\}")
_INLINE_MATH = re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]")
#: Commands whose arguments are keys, paths or code, never prose.
_KEY_COMMANDS = re.compile(
    r"\\(?:cite[a-z]*|[a-z]*ref|label|url|href|includegraphics|input|include|bibliography"
    r"|bibliographystyle|usepackage|RequirePackage|documentclass|begin|end|eqref|autoref"
    r"|cref|Cref|nocite|hypersetup|setlength|newcommand|renewcommand|DeclareMathOperator)"
    r"\*?(?:\s*\[[^\]]*\])*(?:\s*\{[^}]*\})?"
)
_COMMAND = re.compile(r"\\[A-Za-z@]+\*?|\\.")
_ET_AL = re.compile(r"\bet\s+al\b\.?", re.IGNORECASE)
_SETMAINLANGUAGE = re.compile(r"\\setmainlanguage(?:\[[^\]]*\])?\{([^}]+)\}")
_BABEL = re.compile(r"\\usepackage\[([^\]]*)\]\{babel\}")


def is_spanish(line: str) -> bool:
    """The repository guard's heuristic, over a raw line."""
    if INVERTED.search(line):
        return True
    words = {word.lower() for word in WORD.findall(line)}
    if ACCENTED.search(line) and words & WEAK:
        return True
    strong = len(words & STRONG)
    return strong >= 3 or (strong >= 1 and len(words & WEAK) >= 4)


def is_spanish_prose(text: str) -> bool:
    """`is_spanish` for manuscript prose: an accent counts only inside a
    lowercase word (a capitalized accented word is a name), and `et al.`
    is dropped first."""
    text = _ET_AL.sub(" ", text)
    if INVERTED.search(text):
        return True
    tokens = WORD.findall(text)
    words = {token.lower() for token in tokens}
    lowercase_accent = any(ACCENTED.search(token) and token[0].islower() for token in tokens)
    if lowercase_accent and words & WEAK:
        return True
    strong = len(words & STRONG)
    return strong >= 3 or (strong >= 1 and len(words & WEAK) >= 4)


def declared_language(tex: str) -> str | None:
    """The main language `main.tex` declares, lowercased, or `None`."""
    preamble = tex.split("\\begin{document}", 1)[0]
    preamble = "\n".join(_COMMENT.sub("", line) for line in preamble.split("\n"))
    match = _SETMAINLANGUAGE.search(preamble)
    if match:
        return match.group(1).strip().lower()
    match = _BABEL.search(preamble)
    if match:
        options = [opt.strip() for opt in match.group(1).split(",") if opt.strip()]
        for option in options:
            if option.lower().startswith("main="):
                return option.split("=", 1)[1].strip().lower()
        if options:
            return options[-1].lower()
    return None


def is_english(language: str | None) -> bool:
    """`None` (nothing declared) is English: the contract's default."""
    return language is None or language.lower() in ENGLISH_NAMES


def prose_lines(tex: str) -> list[tuple[int, str]]:
    """`(line number, prose)` for every line a reader sees as text: comments
    (and so `%% paper-writing` markers), math, non-prose environments and
    the arguments of key/path commands removed, command names dropped.
    With a `\\begin{document}`, the preamble contributes only its front
    matter (`\\title`, `\\author`, ...); without one (a block body), every
    line is body."""
    lines = tex.split("\n")
    has_document = any("\\begin{document}" in _COMMENT.sub("", line) for line in lines)
    in_body = not has_document
    skip_stack: list[str] = []
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(lines, 1):
        line = _COMMENT.sub("", raw)
        if not in_body:
            if "\\begin{document}" in line:
                in_body = True
                line = line.split("\\begin{document}", 1)[1]
            elif not FRONT_MATTER.search(line):
                continue
        if "\\end{document}" in line:
            line = line.split("\\end{document}", 1)[0]
            in_body = False
            has_document = True
        kept = []
        cursor = 0
        while cursor <= len(line):
            if skip_stack:
                end = _END.search(line, cursor)
                while end and end.group(1).strip() != skip_stack[-1]:
                    end = _END.search(line, end.end())
                if end is None:
                    break
                skip_stack.pop()
                cursor = end.end()
                continue
            begin = None
            for candidate in _BEGIN.finditer(line, cursor):
                if candidate.group(1).strip() in SKIPPED_ENVIRONMENTS:
                    begin = candidate
                    break
            if begin is None:
                kept.append(line[cursor:])
                break
            kept.append(line[cursor:begin.start()])
            skip_stack.append(begin.group(1).strip())
            cursor = begin.end()
        text = "".join(kept)
        text = _INLINE_MATH.sub(" ", text)
        text = _KEY_COMMANDS.sub(" ", text)
        # A `\todo{...}` note is a placeholder; keep it visible as one.
        text = _TODO_COMMAND.sub(" TODO ", text)
        text = _COMMAND.sub(" ", text)
        text = re.sub(r"[{}~]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append((number, text))
    return out


#: A paragraph or list item that opens on emphasis: a bold run-in label
#: (`\textbf{Partition.}`, `{\bf …}`), a run-in heading (`\paragraph{…}`),
#: a bold item (`\item \textbf{Name:}`) or a description label
#: (`\item[Name:]`, which LaTeX sets in bold).
_LEAD_IN = re.compile(
    r"^\s*(?:\\noindent\s*)?(?:\\item\s*)?"
    r"(?:\\textbf\s*\{|\{\s*\\bf\b|\\(?:sub)?paragraph\*?\s*\{)"
)
_DESCRIPTION_LABEL = re.compile(r"^\s*\\item\s*\[")
_SECTIONING = re.compile(r"\\(?:chapter|section|subsection|subsubsection)\*?\s*[\[{]")
_TABULAR_BEGIN = re.compile(r"\\begin\{(?:tabular\*?|tabularx|longtable|array)\}")
_TABULAR_END = re.compile(r"\\end\{(?:tabular\*?|tabularx|longtable|array)\}")


def bold_lead_ins(tex: str) -> list[dict]:
    """Paragraphs and list items that open on emphasis, outside tables.

    A paragraph starts on the first line of the text or after a blank line;
    every `\\item` starts an item. Emphasis inside a sentence and every table
    cell are free. Each hit is `{line, text}`, 1-based."""
    hits: list[dict] = []
    in_table = 0
    paragraph_start = True
    for number, line in enumerate(tex.splitlines(), 1):
        if not line.strip():
            # Only a blank line ends a paragraph; a comment-only line does not.
            paragraph_start = True
            continue
        stripped = _COMMENT.sub("", line).strip()
        if not stripped:
            continue
        if _TABULAR_BEGIN.search(stripped):
            in_table += 1
        starts = paragraph_start or stripped.startswith("\\item")
        if not in_table and starts and not stripped.startswith("\\begin") \
                and (_LEAD_IN.match(stripped) or _DESCRIPTION_LABEL.match(stripped)):
            hits.append({"line": number, "text": stripped[:80]})
        if _TABULAR_END.search(stripped):
            in_table = max(0, in_table - 1)
        # The line after an environment boundary or a sectioning command
        # starts a paragraph of its own.
        paragraph_start = (stripped.startswith(("\\begin", "\\end"))
                           or bool(_SECTIONING.match(stripped)))
    return hits


_FOREIGN_COMMAND = re.compile(r"\\foreignlanguage\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}\s*\{")
_OTHERLANGUAGE_BEGIN = re.compile(r"\\begin\{(otherlanguage\*?)\}\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}")


def _blank(text: str) -> str:
    """`text` with every character but a newline turned into a space, so line numbers survive."""
    return "".join(char if char == "\n" else " " for char in text)


def _closing_brace(tex: str, start: int) -> int:
    """The index just past the brace closing the group opened right before `start`, or `len(tex)`."""
    depth = 1
    index = start
    while index < len(tex):
        char = tex[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(tex)


def mask_foreign_spans(tex: str) -> str:
    """`tex` with the text a paper marks as another language blanked out.

    The argument of `\\foreignlanguage{<lang>}{...}` (braces balanced, across
    lines) and the body of an `otherlanguage` or `otherlanguage*` environment
    are replaced by spaces when `<lang>` is not English, newlines kept: the
    Spanish check exempts such a span (issue #184 item 3, a funding-programme
    title the back matter keeps in its original language). Only the Spanish
    check reads the masked text; a placeholder marker inside a span still counts.
    """
    out: list[str] = []
    cursor = 0
    while True:
        command = _FOREIGN_COMMAND.search(tex, cursor)
        environment = _OTHERLANGUAGE_BEGIN.search(tex, cursor)
        match = min((m for m in (command, environment) if m), key=lambda m: m.start(), default=None)
        if match is None:
            out.append(tex[cursor:])
            return "".join(out)
        if match is command:
            language, body_start = match.group(1), match.end()
            body_end = _closing_brace(tex, body_start)
            closing = max(body_start, body_end - 1)
        else:
            language, body_start = match.group(2), match.end()
            end = re.compile(r"\\end\{" + re.escape(match.group(1)) + r"\}").search(tex, body_start)
            closing = body_end = end.start() if end else len(tex)
        out.append(tex[cursor:body_start])
        if is_english(language.strip()):
            out.append(tex[body_start:closing])
        else:
            out.append(_blank(tex[body_start:closing]))
        cursor = closing


def scan(tex: str, *, language: str | None = None) -> dict:
    """Every Spanish line and placeholder marker of `tex`'s prose.

    `language` is the paper's declared main language (`declared_language`
    over `main.tex`); a block body declares nothing itself, so the write
    gate passes the manuscript's. When it is `None`, `tex`'s own
    declaration (if any) is used.

    Returns `{"language", "english", "spanish": [{"line", "text"}],
    "placeholders": [{"line", "marker", "text"}], "clean"}`.
    """
    if language is None:
        language = declared_language(tex)
    english = is_english(language)
    spanish: list[dict] = []
    placeholders: list[dict] = []
    for number, text in prose_lines(tex):
        for marker, pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(text):
                placeholders.append({"line": number, "marker": marker, "text": text[:160]})
                break
    if english:
        for number, text in prose_lines(mask_foreign_spans(tex)):
            if is_spanish_prose(text):
                spanish.append({"line": number, "text": text[:160]})
    return {
        "language": language or "english",
        "english": english,
        "spanish": spanish,
        "placeholders": placeholders,
        "clean": not spanish and not placeholders,
    }
