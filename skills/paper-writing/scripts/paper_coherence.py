"""paper_coherence: deterministic, advisory coherence checks over `main.tex`
(issues #180 and #183), reported by `verify` under its own `coherence` key.

Every function is pure over bytes and the already-read declaration record:
this module imports only `re`, opens nothing and writes nothing, the same
lock `paper_verify.py` is held to (`tests/test_paper_coherence.py` applies it
here too). It reports; it never repairs.

**Severity.** Every check is a warning: its verdict is `pass`, `warn` or
`unmeasured`, it never enters `verify`'s `holds`/`fails`/`unmeasured` counts
and never changes `clean`, so a paper that verified clean before still does.
Each heuristic below is lexical and can be wrong; a finding is a prompt to
reread the sentence, never a verdict on the science.

Checks, in report order (`COHERENCE_CHECKS`):

- `caption-results` (#180): a caption carries a result value. Flagged: a
  number with `\\pm` or `±`; a p-value (`p < 0.05`); a number or percentage
  within four words after a metric word (accuracy, AUC, F1, error, RMSE,
  improvement, reduction, ...); a percentage followed by a comparative
  (`12% higher`) or preceded by `by` (`by 12%`). A bare number or percentage
  that decodes the key (`dropout 50%`, `k = 5`, `$\\lambda = 0.1$`) is not
  flagged.
- `caption-interpretation` (#180): a caption uses an interpretive verb
  (shows, indicates, reveals, demonstrates, suggests, confirms, proves,
  outperforms, ...). `shown` and `illustrates` describe and are not flagged.
- `caption-duplicates` (#180): a caption sentence of at least
  `DUPLICATE_N` words repeats the body: at least `DUPLICATE_SHARE` of its
  word `DUPLICATE_N`-grams (lowercased word tokens) also occur in the body
  prose outside captions.
- `caption-identifiers` (#180): a caption carries an identifier-like token:
  a word mixing letters and digits (`K1`, `S8`, `r0h0`, `subject-v300`).
  Not flagged: panel letters, pure numbers, a number with a unit (`5ms`,
  `10Hz`), ordinals, compounds of a number and a word (`32-channel`),
  common technical names (`F1`, `L1`, `L2`, `R2`, `2D`, `3D`), and anything
  inside `\\ref`, `\\label`, `\\cite` or `\\eqref`. Product names such
  as `XYZ1234` are flagged too: advisory, for the author to keep or move.
- `overclaiming` (#183): an abstract or introduction sentence uses an
  overclaiming word (solves, proves, guarantees, always, outperforms all,
  eliminates, perfectly, ...).
- `claims-findings` (#183): an abstract or introduction sentence asserts a
  number or a comparison (outperforms, improves, higher, reduces, ...) and
  no results sentence shares a quoted number with it or at least
  `CLAIM_SHARED_TERMS` of its key terms (lowercased words of four letters or
  more, minus stopwords and the comparison words themselves). Pointers
  (`Section 3`, `Table 2`) and enumerations (`(1)`) are not numbers.
  `unmeasured`, `CLAIM_SECTIONS_ABSENT` or `RESULTS_SECTION_ABSENT`.
- `not-performed` (#183): a sentence reports excluded or not-performed work
  ("we did not", "was not performed", "excluded", "left out", "beyond the
  scope", ...). The limitations section, whose job that is, is exempt.
- `symbol-redefinition` (#183): a symbol table is read from the methods
  section (`$x$ denotes ...`, `where $x$ is ...`, `$x$ represents ...`), and
  a sentence in another section defining the same symbol with a meaning
  that shares less than half of its content words is flagged.
  `unmeasured`, `METHODS_SECTION_ABSENT` or `NO_SYMBOL_DEFINED`.
- `naming-consistency` (#183): the declared contribution names
  (`couplings.json` `facts.contributions`) and property/chain words
  (`chain.links[].word`) are compared with every same-length run of words in
  the prose; a run whose crude stems match a declared name but whose text
  differs (`Adaptive-Caching`, `Bounded Retries`, or `adaptive caching` for
  the title-cased `Adaptive Caching`) is flagged; the first letter alone and
  lowercasing a sentence-cased name are not. Abbreviations are not matched.
  `unmeasured`, `NO_DECLARED_NAMES`, when none are declared.

Sections are found two ways: a block marker `<section>.<block>` names its
section; elsewhere `\\begin{abstract}` and each `\\section{...}` title
(classified by keyword) set it.
"""
from __future__ import annotations

import re

COHERENCE_CHECKS: tuple[str, ...] = (
    "caption-results",
    "caption-interpretation",
    "caption-duplicates",
    "caption-identifiers",
    "overclaiming",
    "claims-findings",
    "not-performed",
    "symbol-redefinition",
    "naming-consistency",
)
COHERENCE_VERDICTS: tuple[str, ...] = ("pass", "warn", "unmeasured")
COHERENCE_UNMEASURED_REASONS: tuple[str, ...] = (
    "NO_CAPTION",
    "CLAIM_SECTIONS_ABSENT",
    "RESULTS_SECTION_ABSENT",
    "METHODS_SECTION_ABSENT",
    "NO_SYMBOL_DEFINED",
    "NO_DECLARED_NAMES",
    "CHECK_FAILED",
)
SEVERITY = "warning"

DUPLICATE_N = 5
DUPLICATE_SHARE = 0.5
CLAIM_SHARED_TERMS = 2
_METRIC_WINDOW = 4
_EXCERPT = 240

CLAIM_SECTIONS = ("abstract", "introduction")
RESULTS_SECTIONS = ("results-and-discussion",)
METHODS_SECTIONS = ("materials-and-methods",)
NOT_PERFORMED_EXEMPT = ("limitations",)

# --------------------------------------------------------------------------
# Manuscript reading
# --------------------------------------------------------------------------

_MARKER_RE = re.compile(r"^%% paper-writing block ([\w.-]+) (begin|end)\b.*$")
_SECTION_RE = re.compile(r"\\section\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_COMMENT_RE = re.compile(r"(?<!\\)%.*$")
_SECTION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("abstract", "abstract"),
    ("introduction", "introduction"),
    ("related", "related-work"),
    ("limitation", "limitations"),
    ("conclusion", "conclusions"),
    ("result", "results-and-discussion"),
    ("discussion", "results-and-discussion"),
    ("evaluation", "results-and-discussion"),
    ("finding", "results-and-discussion"),
    ("experiment", "experimental-setup"),
    ("setup", "experimental-setup"),
    ("set-up", "experimental-setup"),
    ("method", "materials-and-methods"),
    ("material", "materials-and-methods"),
    ("approach", "materials-and-methods"),
    ("model", "materials-and-methods"),
    ("acknowledg", "back-matter"),
    ("appendi", "back-matter"),
)


def _classify_title(title: str) -> str:
    lowered = title.lower()
    for keyword, section in _SECTION_KEYWORDS:
        if keyword in lowered:
            return section
    return "other"


def _document_body(text: str) -> str:
    begin = text.find("\\begin{document}")
    end = text.find("\\end{document}")
    if begin != -1:
        text = text[begin + len("\\begin{document}"):end if end > begin else None]
    return text


def segments(main_tex: bytes) -> list[tuple[str, str]]:
    """`[(section, text)]` in document order, comments and markers removed.
    A block marker `<section>.<id>` sets the section for its body; outside
    any qualified block, `\\begin{abstract}` and `\\section{...}` set it."""
    text = _document_body(main_tex.decode("utf-8", errors="replace"))
    out: list[tuple[str, list[str]]] = []
    heading = "other"
    block_section: str | None = None

    def emit(section: str, line: str) -> None:
        if out and out[-1][0] == section:
            out[-1][1].append(line)
        else:
            out.append((section, [line]))

    for raw in text.split("\n"):
        marker = _MARKER_RE.match(raw)
        if marker:
            block_id, edge = marker.groups()
            if edge == "begin":
                block_section = block_id.split(".", 1)[0] if "." in block_id else None
            else:
                block_section = None
            continue
        line = _COMMENT_RE.sub("", raw)
        if "\\begin{abstract}" in line:
            heading = "abstract"
            line = line.replace("\\begin{abstract}", " ")
        if "\\end{abstract}" in line:
            emit(block_section or heading, line.replace("\\end{abstract}", " "))
            heading = "other"
            continue
        match = _SECTION_RE.search(line)
        if match:
            heading = _classify_title(match.group(1))
            line = line[:match.start()] + line[match.end():]
        emit(block_section or heading, line)
    return [(section, "\n".join(lines)) for section, lines in out]


def _balanced(text: str, start: int) -> int:
    """Index just past the `}` matching the `{` at `start`, or -1."""
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


_CAPTION_OPEN_RE = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\]\s*)?\{")


def captions(text: str) -> list[tuple[int, int, str]]:
    """`[(start, end, inner)]` for every `\\caption{...}` in `text`."""
    found = []
    for match in _CAPTION_OPEN_RE.finditer(text):
        end = _balanced(text, match.end() - 1)
        if end == -1:
            continue
        found.append((match.start(), end, text[match.end():end - 1]))
    return found


_REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|label|cite[a-z]*)\*?\s*(?:\[[^\]]*\]\s*)*\{[^}]*\}")
_CMD_ARG_KEEP_RE = re.compile(r"\\(?:textbf|textit|emph|text|mathrm|mathbf|underline|textsc)\s*\{([^{}]*)\}")
_CMD_RE = re.compile(r"\\[A-Za-z@]+\*?")
_ENV_DROP_RE = re.compile(
    r"\\begin\{(figure|table|tabular|tabularx|equation|align|gather|multline|eqnarray|tikzpicture)\*?\}"
    r".*?\\end\{\1\*?\}", re.S)


def _plain(text: str, *, keep_math: bool = True) -> str:
    """LaTeX to readable prose: refs and citations dropped, formatting
    commands unwrapped, other commands removed, `~` to a space."""
    text = _REF_RE.sub(" ", text)
    for _ in range(3):
        text = _CMD_ARG_KEEP_RE.sub(r"\1", text)
    if not keep_math:
        text = re.sub(r"\$[^$]*\$", " ", text)
    text = text.replace("\\%", "%").replace("~", " ").replace("\\pm", " ± ")
    text = _CMD_RE.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ").replace("$", " ")
    return re.sub(r"\s+", " ", text).strip()


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\\$])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _prose(text: str) -> str:
    """Section text without floats or display math, captions included in
    neither: what a reader reads as running prose."""
    return _ENV_DROP_RE.sub(" ", text)


def _excerpt(sentence: str) -> str:
    return sentence if len(sentence) <= _EXCERPT else sentence[:_EXCERPT - 3] + "..."


def _section_sentences(segs, wanted=None, *, keep_math: bool = False) -> list[tuple[str, str]]:
    out = []
    for section, text in segs:
        if wanted is not None and section not in wanted:
            continue
        for sentence in sentences(_plain(_prose(text), keep_math=keep_math)):
            out.append((section, sentence))
    return out


def _result(check: str, verdict: str, findings: list, *, evidence: dict | None = None,
            reason: str | None = None, rule: str) -> dict:
    if verdict not in COHERENCE_VERDICTS:
        raise AssertionError(f"{verdict!r} is not one of {COHERENCE_VERDICTS}")
    if (verdict == "unmeasured") != (reason is not None):
        raise AssertionError("unmeasured_reason is set exactly when the verdict is unmeasured")
    if reason is not None and reason not in COHERENCE_UNMEASURED_REASONS:
        raise AssertionError(f"{reason!r} is not a declared coherence reason")
    return {
        "check": check, "classification": "mechanical", "severity": SEVERITY,
        "verdict": verdict, "findings": findings, "evidence": evidence or {},
        "rule": rule, "unmeasured_reason": reason,
    }


def _verdict(findings: list) -> str:
    return "warn" if findings else "pass"


# --------------------------------------------------------------------------
# #180: captions
# --------------------------------------------------------------------------

_METRIC_WORDS = (
    "accuracy", "auc", "auroc", "f1", "error", "errors", "rmse", "mae", "mse", "precision",
    "recall", "score", "scores", "improvement", "improves", "improved", "gain", "gains",
    "reduction", "reduces", "reduced", "increase", "increases", "increased", "decrease",
    "decreases", "decreased", "correlation", "speedup", "speed-up", "kappa", "bleu", "loss",
)
_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_PM_RE = re.compile(_NUMBER + r"\s*±\s*" + _NUMBER)
_PVALUE_RE = re.compile(r"\bp\s*[<>=≤]\s*0?\.\d+")
_PERCENT_COMPARATIVE_RE = re.compile(
    r"(?:\bby\s+" + _NUMBER + r"\s*%|" + _NUMBER
    + r"\s*%\s+(?:higher|lower|more|less|better|worse|faster|slower|fewer|greater|smaller|larger))",
    re.I)
_WORD_OR_NUMBER_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*|" + _NUMBER + r"\s*%?")


def _metric_values(text: str) -> list[str]:
    tokens = [m.group(0).strip() for m in _WORD_OR_NUMBER_RE.finditer(text)]
    hits = []
    for i, token in enumerate(tokens):
        if token.lower() not in _METRIC_WORDS:
            continue
        for follower in tokens[i + 1:i + 1 + _METRIC_WINDOW]:
            if re.fullmatch(_NUMBER + r"\s*%?", follower):
                hits.append(f"{token} ... {follower}")
                break
    return hits


def result_values(caption: str) -> list[str]:
    """The result values a caption carries (`caption-results`' rule)."""
    plain = _plain(caption)
    hits = [m.group(0) for m in _PM_RE.finditer(plain)]
    hits += [m.group(0) for m in _PVALUE_RE.finditer(plain)]
    hits += [m.group(0) for m in _PERCENT_COMPARATIVE_RE.finditer(plain)]
    hits += _metric_values(plain)
    return hits


_INTERPRETIVE_RE = re.compile(
    r"\b(shows?|showed|showing|indicates?|indicated|indicating|reveals?|revealed|revealing|"
    r"demonstrates?|demonstrated|demonstrating|suggests?|suggested|suggesting|confirms?|"
    r"confirmed|confirming|proves?|proved|outperforms?|outperformed)\b", re.I)


def interpretive_verbs(caption: str) -> list[str]:
    return [m.group(0) for m in _INTERPRETIVE_RE.finditer(_plain(caption))]


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")
_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?(?:ms|s|hz|khz|mhz|ghz|mm|cm|m|km|kg|g|mg|ml|nm|um|px|db|k|v|mv|w|kw|kb|mb|gb|tb|h|"
    r"min|d|x|bit|bits|fps)", re.I)
_ORDINAL_RE = re.compile(r"\d+(?:st|nd|rd|th)", re.I)
_TECHNICAL_TOKENS = frozenset({"f1", "l1", "l2", "r2", "1d", "2d", "3d", "4d", "co2", "h2o", "mp3", "mp4",
                               "utf-8", "sha256", "int8", "fp16", "fp32", "float32", "float64",
                               "int32", "int64", "x86", "arm64", "covid-19", "sars-cov-2"})


def identifiers(caption: str) -> list[str]:
    """Identifier-like tokens (`caption-identifiers`' rule)."""
    text = _REF_RE.sub(" ", caption)
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
    found = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if not (re.search(r"[A-Za-z]", token) and re.search(r"\d", token)):
            continue
        if token.lower() in _TECHNICAL_TOKENS or _UNIT_RE.fullmatch(token) or _ORDINAL_RE.fullmatch(token):
            continue
        parts = re.split(r"[-_]", token)
        if all(part.isdigit() or part.isalpha() for part in parts):
            continue  # a compound such as `32-channel` or `3-layer`, never a code
        found.append(token)
    return found


_NGRAM_WORD_RE = re.compile(r"[a-z0-9]+")


def _ngrams(text: str, n: int) -> set:
    words = _NGRAM_WORD_RE.findall(text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def check_captions(segs) -> list[dict]:
    """The four caption checks, in `COHERENCE_CHECKS` order."""
    found = []
    body_parts = []
    for section, text in segs:
        last = 0
        for start, end, inner in captions(text):
            found.append((section, inner))
            body_parts.append(text[last:start])
            last = end
        body_parts.append(text[last:])
    rules = {
        "caption-results": "a number with ±, a p-value, a number within four words after a metric "
                           "word, or a comparative percentage",
        "caption-interpretation": "an interpretive verb (shows, indicates, reveals, demonstrates, "
                                  "suggests, confirms, proves, outperforms)",
        "caption-duplicates": f"at least {int(DUPLICATE_SHARE * 100)}% of a caption sentence's word "
                              f"{DUPLICATE_N}-grams occur in the body",
        "caption-identifiers": "a token mixing letters and digits, units, ordinals and common "
                               "technical names excepted",
    }
    if not found:
        return [_result(check, "unmeasured", [], reason="NO_CAPTION", rule=rules[check])
                for check in ("caption-results", "caption-interpretation",
                              "caption-duplicates", "caption-identifiers")]
    body = _plain(_prose("\n".join(body_parts)))
    body_grams = _ngrams(body, DUPLICATE_N)
    results, verbs, duplicates, ids = [], [], [], []
    for section, inner in found:
        caption_text = _excerpt(_plain(inner))
        values = result_values(inner)
        if values:
            results.append({"section": section, "caption": caption_text, "values": values})
        hits = interpretive_verbs(inner)
        if hits:
            verbs.append({"section": section, "caption": caption_text, "verbs": hits})
        for sentence in sentences(_plain(inner)):
            grams = _ngrams(sentence, DUPLICATE_N)
            if not grams:
                continue
            share = len(grams & body_grams) / len(grams)
            if share >= DUPLICATE_SHARE:
                duplicates.append({"section": section, "sentence": _excerpt(sentence),
                                   "overlap": round(share, 2)})
        tokens = identifiers(inner)
        if tokens:
            ids.append({"section": section, "caption": caption_text, "tokens": tokens})
    evidence = {"captions": len(found)}
    return [
        _result("caption-results", _verdict(results), results, evidence=evidence,
                rule=rules["caption-results"]),
        _result("caption-interpretation", _verdict(verbs), verbs, evidence=evidence,
                rule=rules["caption-interpretation"]),
        _result("caption-duplicates", _verdict(duplicates), duplicates,
                evidence={**evidence, "n": DUPLICATE_N, "share": DUPLICATE_SHARE},
                rule=rules["caption-duplicates"]),
        _result("caption-identifiers", _verdict(ids), ids, evidence=evidence,
                rule=rules["caption-identifiers"]),
    ]


# --------------------------------------------------------------------------
# #183: claims, not-performed work, symbols, names
# --------------------------------------------------------------------------

_OVERCLAIM_RE = re.compile(
    r"\b(solves?|solved|proves?|proved|proven|guarantees?|guaranteed|always|never fails|"
    r"outperforms? (?:all|every|any)|eliminates?|eliminated|perfectly|definitively|undoubtedly|"
    r"conclusively|unequivocally|completely solves?)\b", re.I)


def check_overclaiming(segs) -> dict:
    rule = "an overclaiming word in the abstract or introduction (solves, proves, guarantees, " \
           "always, outperforms all, eliminates, perfectly, ...)"
    claims = _section_sentences(segs, CLAIM_SECTIONS)
    if not claims:
        return _result("overclaiming", "unmeasured", [], reason="CLAIM_SECTIONS_ABSENT", rule=rule)
    findings = []
    for section, sentence in claims:
        words = [m.group(0) for m in _OVERCLAIM_RE.finditer(sentence)]
        if words:
            findings.append({"section": section, "sentence": _excerpt(sentence), "words": words})
    return _result("overclaiming", _verdict(findings), findings,
                   evidence={"sentences": len(claims)}, rule=rule)


_COMPARATIVE_WORDS = frozenset({
    "outperform", "outperforms", "outperformed", "improve", "improves", "improved", "improvement",
    "better", "higher", "lower", "faster", "slower", "reduce", "reduces", "reduced", "reduction",
    "increase", "increases", "increased", "exceed", "exceeds", "exceeded", "surpass", "surpasses",
    "surpassed", "beats", "superior", "fewer", "smaller", "larger", "greater",
})
_STOPWORDS = frozenset({
    "this", "that", "these", "those", "with", "from", "into", "than", "then", "when", "which",
    "while", "their", "there", "where", "were", "been", "being", "have", "has", "had", "does",
    "also", "both", "each", "more", "most", "less", "such", "only", "over", "under", "between",
    "across", "about", "after", "before", "other", "same", "show", "shows", "showed", "paper",
    "work", "study", "approach", "method", "methods", "propose", "proposed", "results", "result",
    "find", "found", "here", "they", "them", "what", "will", "would", "could", "should", "using",
    "used", "uses", "data", "time", "well", "very", "much", "many", "even", "within", "without",
    "through", "baseline", "baselines", "compared", "against", "while",
})
_NUMBER_IN_TEXT_RE = re.compile(r"\d+(?:\.\d+)?")
_KEYWORD_RE = re.compile(r"[a-z][a-z-]{3,}")


def _key_terms(sentence: str) -> set:
    return {w for w in _KEYWORD_RE.findall(sentence.lower())
            if w not in _STOPWORDS and w not in _COMPARATIVE_WORDS}


_POINTER_RE = re.compile(
    r"\b(?:Sections?|Sec\.|Figures?|Figs?\.|Tables?|Tab\.|Equations?|Eqs?\.|Appendix|Chapter|"
    r"Algorithm|Hypothesis|Hypotheses|H)\s*\d+(?:\.\d+)*|\(\d+\)")


def _quoted_numbers(sentence: str) -> set:
    """Numbers a sentence asserts: pointers (`Section 3`, `Table 2`) and
    enumerations (`(1)`) are not quantities."""
    return set(_NUMBER_IN_TEXT_RE.findall(_POINTER_RE.sub(" ", sentence)))


def _is_claim(sentence: str) -> bool:
    words = set(re.findall(r"[a-z]+", sentence.lower()))
    return bool(_quoted_numbers(sentence)) or bool(words & _COMPARATIVE_WORDS)


def check_claims_findings(segs) -> dict:
    rule = (f"an abstract or introduction sentence with a number or a comparison maps to a results "
            f"sentence sharing a quoted number or at least {CLAIM_SHARED_TERMS} key terms")
    claim_sentences = _section_sentences(segs, CLAIM_SECTIONS)
    if not claim_sentences:
        return _result("claims-findings", "unmeasured", [], reason="CLAIM_SECTIONS_ABSENT", rule=rule)
    claims = [(s, t) for s, t in claim_sentences if _is_claim(t)]
    results = [t for _, t in _section_sentences(segs, RESULTS_SECTIONS)]
    if not results:
        return _result("claims-findings", "unmeasured", [], reason="RESULTS_SECTION_ABSENT", rule=rule)
    result_terms = [(_key_terms(t), _quoted_numbers(t)) for t in results]
    findings = []
    for section, sentence in claims:
        terms = _key_terms(sentence)
        numbers = _quoted_numbers(sentence)
        need = min(CLAIM_SHARED_TERMS, len(terms)) or 1
        mapped = any((numbers & r_numbers) or len(terms & r_terms) >= need
                     for r_terms, r_numbers in result_terms)
        if not mapped:
            findings.append({"section": section, "sentence": _excerpt(sentence),
                             "key_terms": sorted(terms)})
    return _result("claims-findings", _verdict(findings), findings,
                   evidence={"claims": len(claims), "result_sentences": len(results)}, rule=rule)


_NOT_PERFORMED_RE = re.compile(
    r"\b(we (?:did|do) not|(?:was|were|is|are|has|have) not (?:been )?"
    r"(?:performed|conducted|evaluated|run|tested|explored|considered|included|assessed|analy[sz]ed)|"
    r"excluded|left out|omitted|beyond the scope|outside the scope|out of scope|not addressed)\b",
    re.I)


def check_not_performed(segs) -> dict:
    rule = ("a sentence about excluded or not-performed work (we did not, was not performed, "
            "excluded, left out, beyond the scope, ...); the limitations section is exempt")
    findings = []
    for section, sentence in _section_sentences(segs):
        if section in NOT_PERFORMED_EXEMPT:
            continue
        phrases = [m.group(0) for m in _NOT_PERFORMED_RE.finditer(sentence)]
        if phrases:
            findings.append({"section": section, "sentence": _excerpt(sentence), "phrases": phrases})
    return _result("not-performed", _verdict(findings), findings,
                   evidence={"exempt_sections": list(NOT_PERFORMED_EXEMPT)}, rule=rule)


_SYMBOL_DEF_RES = (
    re.compile(r"\$([^$]{1,40})\$\s*,?\s*(?:denotes|represents|stands for|is defined as|is(?=\s+(?:the|a|an)\s))\s+([^.;:$]+)"),
    re.compile(r"\bwhere\s+\$([^$]{1,40})\$\s*(?:denotes|represents|stands for|is)\s+([^.;:$]+)"),
)
_MEANING_STOP_RE = re.compile(r",|\band\b|\bwhere\b|\bwith\b")
_ARTICLES = frozenset({"the", "a", "an", "of", "for", "to", "in", "on", "at", "by", "its", "our"})


def _normalize_symbol(symbol: str) -> str:
    return re.sub(r"\s+", "", symbol)


def _meaning_words(meaning: str) -> tuple:
    head = _MEANING_STOP_RE.split(meaning, maxsplit=1)[0]
    words = [w for w in re.findall(r"[a-z][a-z-]*", head.lower()) if w not in _ARTICLES]
    return tuple(words[:8])


def symbol_definitions(text: str) -> list[tuple[str, tuple, str]]:
    """`[(symbol, meaning words, sentence)]` for every definition in `text`."""
    found = []
    flat = re.sub(r"\s+", " ", _REF_RE.sub(" ", text))
    for pattern in _SYMBOL_DEF_RES:
        for match in pattern.finditer(flat):
            meaning = _meaning_words(match.group(2))
            if meaning:
                found.append((_normalize_symbol(match.group(1)), meaning, match.group(0).strip()))
    return found


def check_symbol_redefinition(segs) -> dict:
    rule = ("a symbol defined in the methods ($x$ denotes ..., where $x$ is ...) is defined in "
            "another section with a meaning sharing less than half of its content words")
    methods = [text for section, text in segs if section in METHODS_SECTIONS]
    if not methods:
        return _result("symbol-redefinition", "unmeasured", [], reason="METHODS_SECTION_ABSENT", rule=rule)
    table: dict = {}
    for text in methods:
        for symbol, meaning, _ in symbol_definitions(_prose(text)):
            table.setdefault(symbol, meaning)
    if not table:
        return _result("symbol-redefinition", "unmeasured", [], reason="NO_SYMBOL_DEFINED", rule=rule)
    findings = []
    for section, text in segs:
        if section in METHODS_SECTIONS:
            continue
        for symbol, meaning, sentence in symbol_definitions(_prose(text)):
            if symbol not in table:
                continue
            first, later = set(table[symbol]), set(meaning)
            if len(first & later) / max(len(first | later), 1) < 0.5:
                findings.append({"symbol": symbol, "section": section,
                                 "methods_meaning": " ".join(table[symbol]),
                                 "meaning": " ".join(meaning), "sentence": _excerpt(sentence)})
    return _result("symbol-redefinition", _verdict(findings), findings,
                   evidence={"symbol_table": {k: " ".join(v) for k, v in sorted(table.items())}},
                   rule=rule)


def _stem(word: str) -> str:
    word = word.lower()
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""), ("e", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)] + replacement
    return word


_NAME_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def declared_names(record: dict) -> list[str]:
    """Contribution names and property/chain words the paper declares in
    `couplings.json`, deduplicated in declaration order."""
    names = []
    facts = record.get("facts") if isinstance(record, dict) else None
    for name in (facts or {}).get("contributions") or []:
        if isinstance(name, str):
            names.append(name)
    chain = record.get("chain") if isinstance(record, dict) else None
    for link in (chain or {}).get("links") or []:
        if isinstance(link, dict) and isinstance(link.get("word"), str):
            names.append(link["word"])
    return list(dict.fromkeys(n.strip() for n in names if n.strip()))


def _differs(name: str, variant: str) -> bool:
    """A variant differs beyond case (hyphenation, plural, inflection), or
    changes the case of a title-cased name (`Adaptive Caching` written
    `adaptive caching`). The first letter alone never counts, and a
    sentence-cased name (`Verbatim-evidence substrate`) may be lowercased."""
    if name.lower() != variant.lower():
        return True
    return name[1:] != variant[1:] and any(char.isupper() for char in name[1:])


def check_naming_consistency(segs, record: dict) -> dict:
    rule = ("a run of words whose stems match a declared contribution or property name but whose "
            "text differs (hyphenation, plural, or the case of a title-cased name)")
    names = declared_names(record)
    if not names:
        return _result("naming-consistency", "unmeasured", [], reason="NO_DECLARED_NAMES", rule=rule)
    findings = []
    seen = set()
    for section, text in segs:
        plain = _plain(_prose(text), keep_math=False)
        words = list(_NAME_WORD_RE.finditer(plain))
        stems = [_stem(m.group(0)) for m in words]
        for name in names:
            target = [_stem(w) for w in _NAME_WORD_RE.findall(name)]
            size = len(target)
            if not size:
                continue
            for i in range(len(words) - size + 1):
                if stems[i:i + size] != target:
                    continue
                variant = plain[words[i].start():words[i + size - 1].end()]
                if not _differs(name, variant):
                    continue
                key = (name, variant, section)
                if key not in seen:
                    seen.add(key)
                    findings.append({"name": name, "variant": variant, "section": section})
    return _result("naming-consistency", _verdict(findings), findings,
                   evidence={"declared": names}, rule=rule)


def run(main_tex: bytes, record: dict | None = None) -> list[dict]:
    """One entry per `COHERENCE_CHECKS` member, in that order."""
    segs = segments(main_tex)
    entries = check_captions(segs) + [
        check_overclaiming(segs),
        check_claims_findings(segs),
        check_not_performed(segs),
        check_symbol_redefinition(segs),
        check_naming_consistency(segs, record or {}),
    ]
    assert [e["check"] for e in entries] == list(COHERENCE_CHECKS)
    return entries


def run_guarded(main_tex: bytes, record: dict | None = None) -> list[dict]:
    """`run`, but advisory all the way down: a failure on unusual manuscript
    bytes reports every check `unmeasured` (`CHECK_FAILED`) instead of
    aborting the `verify` report these warnings ride on."""
    try:
        return run(main_tex, record)
    except Exception as exc:  # noqa: BLE001 -- an advisory check must never fail verify
        rule = f"the coherence checks could not run ({type(exc).__name__})"
        return [_result(check, "unmeasured", [], reason="CHECK_FAILED", rule=rule) for check in COHERENCE_CHECKS]
