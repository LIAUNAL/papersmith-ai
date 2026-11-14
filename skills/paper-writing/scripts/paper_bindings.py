"""paper_bindings: the redactor's input contract, its binding map, and the
checks that make "assert nothing outside the evidence set" a property this
CLI *detects* rather than merely instructs (`evidence-bound-drafting` spec).

The CLI never drafts anything — an agent (the redactor, `.claude/agents/
redactor.md`) does, and hands back a JSON envelope: LaTeX plus a binding map.
This module is the judge: sentences are segmented from the emitted LaTeX
itself, never trusted from the redactor's own account, and every binding is
resolved, typed and mode-checked against the block's real evidence set,
facts and mode — never against what the redactor merely claims.

Public surface:

    RedactorInput                              -> the five-input contract shape
    parse_binding(raw)                         -> (kind, ref)
    segment_sentences(latex)                   -> list[str]
    reconcile(latex, binding_entries)          -> list[dict]  (raises UNBOUND_SENTENCE, BINDING_ORPHANED)
    resolve_bindings(bindings, evidence_ids, licensed_facts, licensed_declarations=())
        -> None  (raises EVIDENCE_ID_UNKNOWN, FACT_NOT_LICENSED, DECLARATION_NOT_LICENSED)
    type_structural(bindings, contract_prose)  -> None  (raises STRUCTURAL_CARRIES_CLAIM)
    declaration_ids(ref)                       -> tuple[str, ...]
    declaration_components(value)              -> tuple[str, ...]
    check_declarations(bindings, declared, contract_prose) -> None  (raises
        DECLARATION_UNDECLARED, DECLARATION_VALUE_ABSENT, DECLARATION_CARRIES_CLAIM)
    check_mode_admissibility(bindings, mode, evidence_by_id) -> None  (raises MODE_VIOLATION)
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_vocabulary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: `evidence-bound-drafting` spec, `Requirement: Redactor Input Contract`:
#: exactly five inputs, `style_set`/`source_sections` empty are both valid
#: values. This is a shape contract, not a validator with its own refusal
#: — a caller building a fixture for the redactor simply cannot omit a
#: field. `RedactorInput` has no production constructor anywhere in this
#: skill (`the-redactor-receives-the-section-it-must-transpose`, design.md
#: D3, measured by `rg 'RedactorInput' --type py`) — the field-count
#: assertion `RedactorInputContractTests` carries is this shape's ONLY
#: enforcement.
@dataclass(frozen=True)
class RedactorInput:
    contract_prose: str
    evidence_set: tuple = ()
    mode: str = ""
    style_set: tuple = ()
    #: `the-redactor-receives-the-section-it-must-transpose`, design.md D3/D4:
    #: appended fifth, exact `BlockContract.source_sections`/packet
    #: `source_sections` shape (`{fact, lineage, title, path, byte_start,
    #: byte_end, text}`), empty for a non-`transposition` block, an unbound
    #: block, or a block whose paper root could not be measured.
    source_sections: tuple = ()


#: The four binding kinds a sentence may be classified under
#: (`evidence-bound-drafting` spec, `Requirement: Binding Map Production`).
#: `declaration` carries an operator-recorded declaration's value (the grant
#: code, the repository URL and commit, ...) -- tokens a `fact:` binding is
#: not licensed for and a `structural` sentence may never print.
BINDING_KINDS: tuple[str, ...] = ("evidence", "fact", "declaration", "structural")

_BINDING_RE = re.compile(r"^(evidence|fact|declaration):(?P<ref>.+)$")

#: The `declaration:` id that binds a sentence to the packet's `ai_usage`
#: record (`paper_ai_usage.build`) rather than to a recorded declaration. It
#: is not in `paper_vocabulary.DECLARATIONS` -- nobody declares it -- and is
#: licensed only for the blocks whose packet carries that record
#: (`paper_ai_usage.AI_USAGE_BLOCKS`).
AI_USAGE_DECLARATION = "ai-usage"


@dataclass(frozen=True)
class Binding:
    sentence: str
    kind: str
    ref: str | None
    raw: str = field(default="", compare=False)


def parse_binding(raw: str) -> tuple[str, str | None]:
    """`"evidence:E1"` -> `("evidence", "E1")`; `"fact:results"` ->
    `("fact", "results")`; `"declaration:grant-title,grant-code"` ->
    `("declaration", "grant-title,grant-code")`; `"structural"` ->
    `("structural", None)`. Any other string is not one of the four kinds
    this map may name (`evidence-bound-drafting` spec, `Requirement: Binding
    Map Production`, "every entry names exactly one of `evidence:`, `fact:`,
    `declaration:`, or `structural`") — raised as a plain `ValueError`,
    never a `Refused`: a binding map entry this malformed is not one this
    reconciliation was ever asked to judge, the redactor's contract having
    already promised only these four shapes.
    """
    if raw == "structural":
        return "structural", None
    match = _BINDING_RE.match(raw)
    if match is None:
        raise ValueError(
            f"{raw!r} is not evidence:<id>, fact:<id>, declaration:<id>[,<id>...], or structural"
        )
    return match.group(1), match.group("ref")


#: Splits after a sentence-ending `.`/`!`/`?` followed by whitespace and
#: either a capital letter or a LaTeX command — enough for the contract
#: prose and fixtures this change judges; not a general-purpose sentence
#: tokenizer.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\])")


def segment_sentences(latex: str) -> list[str]:
    """Segments `latex` into sentences from the emitted bytes themselves —
    the CLI's own reading, never the redactor's account of where its
    sentence boundaries fall (`evidence-bound-drafting` spec, `Requirement:
    Draft-Versus-Map Reconciliation`)."""
    text = latex.strip()
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def reconcile(latex: str, binding_entries: list[dict]) -> list[Binding]:
    """Segments `latex` independently and checks it against
    `binding_entries` (each `{"sentence": ..., "binding": "evidence:E1"}`)
    in both directions. Refuses `UNBOUND_SENTENCE` naming a segmented
    sentence absent from the map; refuses `BINDING_ORPHANED` naming a map
    entry matching no segmented sentence."""
    sentences = segment_sentences(latex)
    by_sentence = {entry["sentence"]: entry for entry in binding_entries}

    for sentence in sentences:
        if sentence not in by_sentence:
            raise Refused("UNBOUND_SENTENCE", f"drafted sentence has no binding: {sentence!r}")

    sentence_set = set(sentences)
    for entry in binding_entries:
        if entry["sentence"] not in sentence_set:
            raise Refused(
                "BINDING_ORPHANED",
                f"binding entry matches no segmented draft sentence: {entry['sentence']!r}",
            )

    bindings = []
    for sentence in sentences:
        entry = by_sentence[sentence]
        kind, ref = parse_binding(entry["binding"])
        bindings.append(Binding(sentence=sentence, kind=kind, ref=ref, raw=entry["binding"]))
    return bindings


def declaration_ids(ref: str | None) -> tuple[str, ...]:
    """A `declaration:` binding's ids, in the order written:
    `"grant-title,grant-code"` -> `("grant-title", "grant-code")`. One
    sentence may carry several declarations (a funding entry names the
    project's title and its code together)."""
    return tuple(part.strip() for part in (ref or "").split(","))


def resolve_bindings(
    bindings: list[Binding], evidence_ids: set, licensed_facts: set,
    licensed_declarations=(),
) -> None:
    """Refuses `EVIDENCE_ID_UNKNOWN` naming an `evidence:` binding's id when
    it is absent from the block's evidence set; refuses `FACT_NOT_LICENSED`
    naming a `fact:` binding's id when it sits outside `requires_facts`
    (`evidence-bound-drafting` spec, `Requirement: Binding Resolution`);
    refuses `DECLARATION_NOT_LICENSED` naming a `declaration:` binding's id
    when it sits outside `licensed_declarations` -- the block's own
    `requires_declarations`, plus `AI_USAGE_DECLARATION` for a block whose
    packet carries the `ai_usage` record. The default is empty, so a caller
    that licenses no declaration refuses every `declaration:` binding."""
    licensed = set(licensed_declarations)
    for binding in bindings:
        if binding.kind == "evidence" and binding.ref not in evidence_ids:
            raise Refused("EVIDENCE_ID_UNKNOWN", f"{binding.ref!r} is not in the block's evidence set")
        if binding.kind == "fact" and binding.ref not in licensed_facts:
            raise Refused("FACT_NOT_LICENSED", f"{binding.ref!r} is not in requires_facts")
        if binding.kind == "declaration":
            for declaration_id in declaration_ids(binding.ref):
                if declaration_id in licensed:
                    continue
                if declaration_id == AI_USAGE_DECLARATION:
                    raise Refused(
                        "DECLARATION_NOT_LICENSED",
                        f"{declaration_id!r} is licensed only for the blocks whose packet "
                        "carries the ai_usage record",
                    )
                raise Refused(
                    "DECLARATION_NOT_LICENSED",
                    f"{declaration_id!r} is not in requires_declarations "
                    f"(licensed: {sorted(licensed)})",
                )


_MATH_INLINE_RE = re.compile(r"\$[^$]*\$")
_MATH_DISPLAY_RE = re.compile(
    r"\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(equation|align|gather|math)\*?\}.*?\\end\{\1\*?\}",
    re.DOTALL,
)
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?")
_CITE_RE = re.compile(r"\\cite\w*")
_DIGIT_RE = re.compile(r"\d")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _strip_math(text: str) -> str:
    text = _MATH_DISPLAY_RE.sub(" ", text)
    text = _MATH_INLINE_RE.sub(" ", text)
    return text


def _has_numeral(sentence: str) -> bool:
    stripped = _strip_math(sentence)
    if _DIGIT_RE.search(stripped):
        return True
    words = (w.lower() for w in _WORD_RE.findall(stripped))
    return any(word in paper_vocabulary.NUMBER_WORDS for word in words)


def _has_cite(sentence: str) -> bool:
    return bool(_CITE_RE.search(sentence))


def _has_comparative(sentence: str) -> bool:
    stripped = _strip_math(sentence)
    words = (w.lower() for w in _WORD_RE.findall(stripped))
    return any(word in paper_vocabulary.COMPARATIVES for word in words)


def _named_external_object(sentence: str, contract_prose: str) -> str | None:
    """A non-sentence-initial capitalised token, outside math and outside
    LaTeX commands, absent verbatim from `contract_prose` (`design.md`,
    Decision D3). Mechanical: no proper-noun heuristic, no auditor
    delegation."""
    stripped = _strip_math(sentence)
    stripped = _LATEX_CMD_RE.sub(" ", stripped)
    tokens = _WORD_RE.findall(stripped)
    for index, token in enumerate(tokens):
        if index == 0:
            continue
        if token[0].isupper() and token not in contract_prose:
            return token
    return None


def type_structural(bindings: list[Binding], contract_prose: str) -> None:
    """Refuses `STRUCTURAL_CARRIES_CLAIM` naming the offending sentence for
    a `structural` sentence carrying a numeral, a `\\cite` command, a
    comparative, or a named external object (`evidence-bound-drafting`
    spec, `Requirement: Structural Sentences Are Typed`)."""
    for binding in bindings:
        if binding.kind != "structural":
            continue
        if _has_numeral(binding.sentence):
            raise Refused(
                "STRUCTURAL_CARRIES_CLAIM", f"numeral in structural sentence: {binding.sentence!r}"
            )
        if _has_cite(binding.sentence):
            raise Refused(
                "STRUCTURAL_CARRIES_CLAIM", f"\\cite in structural sentence: {binding.sentence!r}"
            )
        if _has_comparative(binding.sentence):
            raise Refused(
                "STRUCTURAL_CARRIES_CLAIM", f"comparative in structural sentence: {binding.sentence!r}"
            )
        external = _named_external_object(binding.sentence, contract_prose)
        if external is not None:
            raise Refused(
                "STRUCTURAL_CARRIES_CLAIM",
                f"named external object {external!r} in structural sentence: {binding.sentence!r}",
            )


#: LaTeX accent macros a declared value may be typed with in a draft
#: (`m\'aquina`, `\~n`), mapped onto the combining mark that composes the
#: same character the recorded value holds (`máquina`).
_ACCENT_MARKS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
                 "=": "\u0304", ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306",
                 "H": "\u030b"}
_ACCENT_RE = re.compile(r"\\([`'^\"~=.])\{?([A-Za-z])\}?|\\([cvuH])\{([A-Za-z])\}")
_HREF_RE = re.compile(r"\\href\{([^{}]*)\}\{([^{}]*)\}")
_COMMAND_ARG_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}")
_BARE_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?")
_ESCAPED_RE = re.compile(r"\\([&%_#$])")
#: An alphanumeric run: the unit numerals and named objects are compared in.
_RUN_RE = re.compile(r"[^\W_]+")
#: A word on printed text, accented letters included (`Ángel`, `UCaldas–UNAL`
#: is two words); a capitalised one is a named object.
_NAMED_RE = re.compile(r"[^\W\d_](?:[^\W_]|['-](?=[^\W_]))*")


def _accent(match: re.Match) -> str:
    mark, letter = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
    return letter + _ACCENT_MARKS[mark]


def _normalize(text: str) -> str:
    """The printed text of `text`, so a declared value and a sentence that
    typesets it compare equal: accent macros composed, `\\url{X}` and
    `\\href{X}{Y}` reduced to their text, any other `\\cmd{X}` to `X`, TeX
    dashes and quotes to the characters they print, `~` to a space, escaped
    specials unescaped, and whitespace collapsed. Applied to both sides."""
    text = unicodedata.normalize("NFC", _ACCENT_RE.sub(_accent, text))
    text = _HREF_RE.sub(r"\1 \2", text)
    previous = None
    while previous != text:
        previous, text = text, _COMMAND_ARG_RE.sub(r"\1", text)
    text = _BARE_COMMAND_RE.sub(" ", text)
    text = _ESCAPED_RE.sub(r"\1", text)
    text = text.replace("---", "\u2014").replace("--", "\u2013")
    text = text.replace("``", '"').replace("''", '"').replace("~", " ")
    text = text.replace("\\,", " ").replace("\\ ", " ")
    return " ".join(text.split())


_PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")


def _date_runs(text: str) -> set:
    """The other runs an ISO date in a value prints as: `2026-11-03` may be
    written `3 November 2026` or `Nov. 3, 2026`, so the month's name and
    abbreviation and the unpadded month and day are runs of the value too."""
    runs: set = set()
    for _year, month, day in _ISO_DATE_RE.findall(text):
        if 1 <= int(month) <= 12:
            name = _MONTHS[int(month) - 1]
            runs |= {name, name[:3], str(int(month)), str(int(day))}
    return runs


def declaration_components(value: str) -> tuple[str, ...]:
    """The parts of a recorded declaration value a sentence may carry, each
    verbatim: the whole value, every parenthetical group's text, and every
    `;`- or newline-separated part of what remains, each stripped of
    surrounding whitespace and trailing `.`/`,`/`:`.
    `"https://x/y; commit 06faa71 (branch main); checked 2026-11-13"` ->
    the whole value, `"branch main"`, `"https://x/y"`, `"commit 06faa71"`,
    `"checked 2026-11-13"`."""
    pieces = [value]
    outer = value
    while True:
        inner = _PARENTHETICAL_RE.findall(outer)
        if not inner:
            break
        pieces.extend(inner)
        outer = _PARENTHETICAL_RE.sub(" ", outer)
    for piece in [outer, *pieces[1:]]:
        pieces.extend(re.split(r"[;\n]", piece))
    components: list[str] = []
    for piece in pieces:
        cleaned = " ".join(piece.split()).strip(" .,:")
        if cleaned and cleaned not in components:
            components.append(cleaned)
    return tuple(components)


def _carries(sentence: str, component: str) -> bool:
    pattern = r"(?<![^\W_])" + re.escape(_normalize(component)) + r"(?![^\W_])"
    return re.search(pattern, sentence) is not None


def check_declarations(bindings: list[Binding], declared: dict, contract_prose: str) -> None:
    """Judges every `declaration:` sentence against the values it names.
    `declared` maps a licensed id to its value -- a recorded declaration's
    string, or, for `AI_USAGE_DECLARATION`, a `(components, extra)` pair
    (`paper_ai_usage.declarable`). An id absent from `declared` has no
    recorded value. Run after `resolve_bindings`, so every id is licensed.

    Three refusals, each naming the sentence:

    * `DECLARATION_UNDECLARED` -- a named id has no recorded value;
    * `DECLARATION_VALUE_ABSENT` -- for some named id, the sentence carries
      none of its components (`declaration_components`) verbatim, compared
      on printed text (`_normalize`) between alphanumeric boundaries;
    * `DECLARATION_CARRIES_CLAIM` -- outside math, the sentence prints an
      alphanumeric run holding a digit that no named value holds as a run
      (an ISO date also holds its month's name and its unpadded month and
      day, `_date_runs`; the contract prose never licenses a numeral: its examples are not
      this paper's values), or a capitalised word -- not opening the
      sentence or following a `.`/`:`/`!`/`?` (a bold label) -- that is
      neither in the contract prose (verbatim, as `type_structural` reads
      it) nor a value's run (any case), or a comparative
      (`paper_vocabulary.COMPARATIVES`, as `type_structural` refuses it)
      that no value holds. A declaration licenses its own tokens, never
      others.
    """
    for binding in bindings:
        if binding.kind != "declaration":
            continue
        ids = declaration_ids(binding.ref)
        sentence = _normalize(_strip_math(binding.sentence))
        universe: list[str] = []
        for declaration_id in ids:
            if declaration_id not in declared or declared[declaration_id] is None:
                raise Refused(
                    "DECLARATION_UNDECLARED",
                    f"{declaration_id!r} has no recorded value; record it with "
                    f"`declare --declaration {declaration_id} --value <value>` before binding "
                    f"a sentence to it: {binding.sentence!r}",
                )
            value = declared[declaration_id]
            if isinstance(value, str):
                components, extra = declaration_components(value), ()
            else:
                components, extra = tuple(value[0]), tuple(value[1])
            if not any(_carries(sentence, component) for component in components):
                raise Refused(
                    "DECLARATION_VALUE_ABSENT",
                    f"sentence bound to {declaration_id!r} carries none of its recorded value "
                    f"verbatim (any one of {list(components)}): {binding.sentence!r}",
                )
            universe.extend(components)
            universe.extend(extra)
        runs = {run for text in universe for run in _RUN_RE.findall(_normalize(text))}
        runs |= {run for text in universe for run in _date_runs(text)}
        lowered = {run.lower() for run in runs}
        for run in _RUN_RE.findall(sentence):
            if any(ch.isdigit() for ch in run) and run not in runs:
                raise Refused(
                    "DECLARATION_CARRIES_CLAIM",
                    f"numeral {run!r} is in no value the sentence is bound to "
                    f"({list(ids)}): {binding.sentence!r}",
                )
        for word in _WORD_RE.findall(sentence):
            if word.lower() in paper_vocabulary.COMPARATIVES and word.lower() not in lowered:
                raise Refused(
                    "DECLARATION_CARRIES_CLAIM",
                    f"comparative {word!r} is in no value the sentence is bound to "
                    f"({list(ids)}): {binding.sentence!r}",
                )
        for match in _NAMED_RE.finditer(sentence):
            token = match.group(0)
            if not token[0].isupper() or token in contract_prose:
                continue
            before = sentence[: match.start()].rstrip()
            if not before or before[-1] in ".:!?":
                continue  # sentence- or label-initial (`\textbf{Funding.} The ...`)
            if all(part.lower() in lowered for part in _RUN_RE.findall(token)):
                continue
            raise Refused(
                "DECLARATION_CARRIES_CLAIM",
                f"named object {token!r} is in no value the sentence is bound to "
                f"({list(ids)}) nor in the contract prose: {binding.sentence!r}",
            )


#: `evidence-bound-drafting` spec, `Requirement: Mode-Admissible Bindings`.
#: `transposition` admits only `fact`/`structural`/`resolution`-class
#: evidence; `argument` additionally admits `discovery`-class evidence.
#: `none` (no external source at all) is strictly more restrictive than
#: `resolution` and belongs in every mode's admitted set for that reason:
#: an evidence record's `regime` is inherited from its own block's
#: `citations` field (`paper_cli._resolve_regime` ->
#: `paper_validate.read_citations_regime`, fallback `"none"`), so a mode
#: that refuses `none` would refuse the very blocks that declare no
#: citation source at all -- measured against the real corpus in
#: `tests/test_paper_writing.py::CorpusModeCitationsAdmissibilityTests`.
_MODE_ADMITTED_EVIDENCE_REGIMES: dict = {
    "transposition": frozenset({"none", "resolution"}),
    "argument": frozenset({"none", "resolution", "discovery"}),
}


def check_mode_admissibility(bindings: list[Binding], mode: str, evidence_by_id: dict) -> None:
    """Refuses `MODE_VIOLATION` naming an `evidence:` binding's id when its
    record's `regime` is outside the set `mode` admits. `fact:`,
    `declaration:` and `structural` bindings are always admitted — mode
    admissibility is an evidence-class question only."""
    paper_vocabulary.validate_mode(mode)
    admitted = _MODE_ADMITTED_EVIDENCE_REGIMES[mode]
    for binding in bindings:
        if binding.kind != "evidence":
            continue
        record = evidence_by_id.get(binding.ref)
        regime = record.get("regime") if record else None
        if regime not in admitted:
            raise Refused(
                "MODE_VIOLATION",
                f"{binding.ref!r} (regime={regime!r}) is not admitted under mode {mode!r}",
            )
