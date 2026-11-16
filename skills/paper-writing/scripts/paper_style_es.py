# Copyright the papersmith-ai authors.
# Licensed under the Apache License, Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0).
# Adapted from LIAUNAL/propuestasmorfeo-ia scripts/estilo_es.py (Apache-2.0):
# the pattern catalog, the flow and redundancy findings, the score and its
# thresholds, and the fact comparison of `verificar`. Run-specific parts
# (run sections, MGA vocabulary, institutions, SGR exemptions, cohorts, TRL,
# report files) were dropped; the protected-term collapser takes a per-paper
# glossary instead.
"""paper_style_es: a readability index for Spanish manuscript prose, and the
EN->ES fidelity check of the translation step.

`audit_text` scores one block of LaTeX prose and locates what slows a reader
down: stock phrases, English calques, chatbot templates, closing gerunds,
spaced dashes, long sentences, repeated openings and connectors, repeated
phrases and near-duplicate sentences. `audit_document` does the same per block
and also lists the repetition that crosses blocks. `compare_facts` lists every
fact of an English block that its Spanish version does not keep: citation
keys, label and reference targets, math, numbers with their units, and the
paragraph count.

Scores: `style_score`, `flow_score` and `redundancy_score` run from 0.0
(nothing to revise) to 1.0; `index` = 100 * (1 - (style + flow) / 2), so
higher is better. Counts are normalized per 1000 words. The thresholds are
provisional constants (`THRESHOLDS`). A score never refuses anything.

Pure: standard library only, no disk access.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

NOTICE = (
    "This index measures the readability and flow of Spanish prose. It is a "
    "writing-quality estimate, not an authorship test: it says nothing about who or "
    "what wrote the text, nor about its scientific value, and its thresholds are "
    "provisional. It guides a revision; it never approves one."
)

THRESHOLDS: dict = {
    "bands": {"clear": 0.20, "uneven": 0.45},
    "min_words_for_normalization": 200,
    "mattr_window": 200,
    "mattr_floor": 0.45,
    "mattr_ceiling": 0.65,
    "long_sentence_words": 45,
    "long_share_floor": 0.05,
    "long_share_ceiling": 0.30,
    "ngram": 5,
    "ngram_content_words": 3,
    "ngram_sentences": 3,
    "ngram_paragraphs": 2,
    "jaccard": 0.6,
    "jaccard_min_words": 6,
    "connector_window": 5,
    "connector_share": 0.25,
    "connector_overuse_per_1000": 3.0,
    "synthesis_per_1000": 0.5,
    "opening_dominant": 0.15,
    "demonstrative_share": 0.15,
    "causal_per_1000": 4.0,
    "relative_tail_per_1000": 3.0,
    "clause_window": 3,
    "triad_per_1000": 3.0,
    "overuse_min_count": 8,
    "overuse_times_median": 4.0,
    "overuse_types_for_median": 20,
    "overuse_noun_context": 0.4,
    "overuse_max": 10,
    "saturation_per_1000": {"catalog": 15.0, "overuse": 2.0, "connectors": 6.0, "openings": 6.0,
                            "clauses": 6.0, "redundancy": 8.0, "templates": 5.0},
    "style_weights": {"catalog": 0.50, "long_sentences": 0.30, "mattr": 0.10, "overuse": 0.10},
    "flow_weights": {"connectors": 0.25, "openings": 0.15, "clauses": 0.15, "redundancy": 0.25,
                     "templates": 0.20},
}


def fold(word: str) -> str:
    """The word without its accents."""
    return "".join(c for c in unicodedata.normalize("NFD", word) if unicodedata.category(c) != "Mn")


# Words that carry no topic, folded (no accents).
FUNCTION_WORDS = frozenset("""
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada casi como con cual cuales cuyo
    cuya de del dos e el ella ellas ello ellos en era eran es esa esas ese eso esos esta estan estar este esto
    estos fue fueron ha han hay la las le les lo los mas me muy ni no nos o os otra otro para pero poco por pues
    que se sea sean segun ser si sin sino siempre son su sus tal tambien tan tanto te tiene tienen toda todo tres
    tu u un una unas uno unos ya y
    cuanto dentro fuera luego mientras nunca solo tras varios varias vez veces ademas
    sobre entre desde hasta hacia contra durante donde cuando porque aunque puede pueden mismo misma mismos mismas
    estas otros otras todos todas parte forma
    mediante aquellos aquellas traves nivel niveles grado mayor menor mejor peor general medio medios
""".split())
NOUN_CONTEXT = frozenset("el la los las un una unos unas del al de este esta estos estas ese esa esos esas su sus cada".split())

# (category, regex), seeded from the estilo-natural-es catalog.
_CATALOG_SOURCE = (
    ("cliche", r"\bse erigen? como\b"),
    ("cliche", r"\b(?:juegan?|desempeñan?) un (?:papel|rol) (?:\w+ )?(?:fundamental|crucial|clave|vital|central|esencial)\b"),
    ("cliche", r"\bmarcan? un antes y un después\b"),
    ("cliche", r"\bun punto de inflexión\b"),
    ("cliche", r"\bsent(?:ando|ar|ó|a|an) las bases\b"),
    ("cliche", r"\ben el corazón de\b"),
    ("cliche", r"\bhorizonte prometedor\b"),
    ("cliche", r"\bsin duda, un avance\b"),
    ("cliche", r"\barrojan? luz sobre\b"),
    ("comodin", r"\b(?:robust[oa]s?|crucial(?:es)?|fundamental(?:es)?|ecosistemas?|tapiz|entramados?)\b"),
    ("comodin", r"\bun abanico de\b"),
    ("comodin", r"\ben última instancia\b"),
    ("comodin", r"\bde la mano de\b"),
    ("promocional", r"\b(?:vibrantes?|revolucionari[oa]s?|impresionantes?|innovador(?:a|es|as)?)\b"),
    ("promocional", r"\b(?:de vanguardia|rico patrimonio|profundo impacto)\b"),
    ("atribucion_vaga", r"\bdiversos (?:expertos|autores|estudios)\b"),
    ("atribucion_vaga", r"\bestudios recientes (?:señalan|muestran|indican|sugieren|demuestran)\b"),
    ("atribucion_vaga", r"\bla literatura (?:sugiere|señala|indica|muestra)\b"),
    ("perifrasis", r"\bcon el fin de lograr este propósito\b"),
    ("perifrasis", r"\bdebido al hecho de que\b"),
    ("perifrasis", r"\btienen? la capacidad de\b"),
    ("perifrasis", r"\bllevar a cabo\b"),
    ("copula_evitada", r"\bse posicionan? como\b"),
    ("copula_evitada", r"\b(?:constituyen?|albergan?|cuentan? con)\b"),
    ("calco", r"\bhacer sentido\b"),
    ("calco", r"\beventualmente\b"),
    ("calco", r"\bremo(?:ver|viendo|vió|vido)\b"),
    ("calco", r"\bconsistentes? con\b"),
    ("calco", r"\ben orden de\b"),
    ("calco", r"\bdramátic(?:o|a|os|as|amente)\b"),
    ("calco", r"\bbasad[oa]s? en el hecho\b"),
    ("calco", r"\ben base a\b"),
    ("calco", r"\b(?:es|son|fue|fueron) (?:propuest|desarrollad|implementad)[oa]s? por\b"),
    ("plantilla", r"\bcabe (?:destacar|mencionar|señalar|resaltar)(?: que)?\b"),
    ("plantilla", r"\bes (?:importante|fundamental|necesario) (?:destacar|mencionar|señalar|comprender|resaltar) que\b"),
    ("plantilla", r"\b(?:en el mundo actual|en la era digital|hoy en día)\b"),
    ("plantilla", r"\ba continuación (?:se (?:presenta|describe|procede)|presento)\b"),
    ("plantilla", r"\ben esta sección (?:se |procederemos)"),
    ("plantilla", r"\b(?:la verdad es que|siendo honestos|a decir verdad)\b"),
    ("plantilla", r"\b(?:la verdadera pregunta es|lo que de verdad importa)\b"),
    ("plantilla", r"\bespero que esta sección\b"),
    ("plantilla", r"\bpor supuesto\b"),
    ("paralelismo_negativo", r"\bno solo\b[^.;]{1,120}?\bsino\b"),
    ("paralelismo_negativo", r"\bno se trata de\b[^.;]{1,120}?\bsino\b"),
    ("falso_rango", r"\bdesde\b(?![^.;]{0,8}\d)[^.;\d]{3,80}?\bhasta\b(?!\s+\S*\d)"),
    # Neutral academic register: no second person (tuteo, voseo, vosotros) and
    # no regional vocabulary where a neutral form exists.
    ("register", r"\b(?:tú|vos|vosotr[oa]s|os)\b"),
    ("register", r"\b(?:puedes|tienes|debes|sabes|quieres|ves|podés|tenés|sabés|querés)\b"),
    ("register", r"\b(?:ordenador(?:es)?|cog(?:er|e|en|ió|imos))\b"),
)
CATALOG = tuple((category, re.compile(pattern, re.I)) for category, pattern in _CATALOG_SOURCE)
TEMPLATE_CATEGORIES = frozenset({"plantilla", "paralelismo_negativo", "falso_rango"})
STYLE_CATEGORIES = frozenset({"cliche", "comodin", "promocional", "atribucion_vaga", "perifrasis",
                              "copula_evitada", "calco", "register", "triad", "spaced_dash"})
CONNECTOR_CATEGORIES = frozenset({"connector_repeat", "connector_density", "connector_overuse", "synthesis_repeat"})
OPENING_CATEGORIES = frozenset({"opening_repeat", "opening_dominant", "demonstrative_opening"})
CLAUSE_CATEGORIES = frozenset({"causal_density", "relative_tail", "clause_repeat", "closing_gerund"})
REDUNDANCY_CATEGORIES = frozenset({"repeated_phrase", "near_duplicate"})

# Folded, longest first where one contains another.
CONNECTORS = (
    "por consiguiente", "en este sentido", "en tal sentido", "de igual manera", "de igual forma", "de ahi que",
    "por otro lado", "por otra parte", "por una parte", "en primer lugar", "en segundo lugar", "en tercer lugar",
    "sin embargo", "no obstante", "por lo tanto", "por tanto", "por ende", "en consecuencia", "de este modo",
    "de esta manera", "de esta forma", "con todo", "ahora bien", "en concreto", "a su vez", "en contraposicion",
    "asi las cosas", "en efecto", "asimismo", "adicionalmente", "ademas", "finalmente",
)
SYNTHESIS_CONNECTORS = ("en resumen", "en sintesis", "en conclusion", "en suma", "en definitiva", "en conjunto")
_ALL_CONNECTORS = tuple(sorted(CONNECTORS + SYNTHESIS_CONNECTORS, key=len, reverse=True))
CONNECTOR_RE = re.compile(r"(" + "|".join(_ALL_CONNECTORS) + r")\b")
DEMONSTRATIVE_RE = re.compile(r"(?:Este|Esta|Estos|Estas|Dicho|Dicha|Dichos|Dichas)\s+([^\W\d_]+)")
VERBS_AFTER_DEMONSTRATIVE = frozenset({"es", "son", "fue", "fueron", "será", "serán", "ha", "han", "tiene", "tienen"})
CAUSAL_RE = re.compile(r"\b(?:porque|ya que|puesto que)\b", re.I)
TAIL_RE = re.compile(r",\s+lo (?:cual|que)\b", re.I)
GERUND_TAIL_RE = re.compile(r",\s+([^\W\d_]+(?:ando|iendo|yendo))\b[^,;:]*[.!?]?\s*$", re.I)
NOT_GERUNDS = frozenset({"cuando", "comando", "mando", "bando", "contrabando", "demando", "estruendo", "aprendo",
                         "entiendo", "comprendo", "vendo", "ando", "doctorando", "graduando", "educando"})
TRIAD_RE = re.compile(r"(?<!, )\b([^\W\d_]{4,}), ([^\W\d_]{4,}) [ye] ([^\W\d_]{4,})\b")
DASH_RE = re.compile(r"\s—\s|\s-{2,3}\s|(?<=[^\W\d_])-{2,3}(?=[^\W\d_])")

TOKEN_RE = re.compile(r"⟦[^⟧]*⟧|\d+(?:[.,]\d+)*|[^\W\d_]+(?:[-'’][^\W\d_]+)*")
CITE_TOKEN = "⟦c⟧"
PLACEHOLDER_RE = re.compile(r"⟦(\d+)⟧")
CITE_MARK = "\ue001"
DOLLAR = "\ue000"
ITEM_MARK = "\ue002"

ABBREVIATIONS = frozenset({
    "p", "pp", "ej", "fig", "figs", "tab", "núm", "num", "vol", "ed", "eds", "cap", "caps", "sec", "dr", "dra",
    "sr", "sra", "prof", "ing", "art", "inc", "aprox", "máx", "mín", "cf", "vs", "ca", "ec", "ecs", "e.g", "i.e",
    "et",
})
SENTENCE_END_RE = re.compile(r"[.!?…]+[\"»”)\]\ue001]*\s+")
OPENING_PUNCTUATION = "¿¡«\"“([" + CITE_MARK

# --- LaTeX ------------------------------------------------------------------

NON_PROSE_ENVS = (
    "tabular", "tabularx", "xltabular", "longtable", "tikzpicture", "verbatim", "lstlisting", "equation",
    "align", "gather", "multline", "eqnarray", "flalign", "alignat", "math", "displaymath", "figure", "table",
    "algorithm", "algorithmic",
)
CITE_RE = re.compile(
    r"\\(cite|citep|citet|citealp|citealt|citeauthor|citeyear|citeyearpar|nocite|parencite|textcite|autocite)\*?"
    r"(?:\[[^\]]*\]){0,2}\{([^}]*)\}",
    re.S,
)
BEGIN_RE = re.compile(r"\\begin\{(" + "|".join(NON_PROSE_ENVS) + r")\*?\}")
END_RE = re.compile(r"\\end\{(" + "|".join(NON_PROSE_ENVS) + r")\*?\}")
SECTION_COMMANDS = ("part", "chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph")
DROPPED_COMMANDS = (
    "label", "ref", "cref", "Cref", "pageref", "eqref", "autoref", "nameref", "includegraphics", "input", "include",
    "vspace", "hspace", "setlength", "addtolength", "setcounter", "addtocounter", "bibliography",
    "bibliographystyle", "newcommand", "renewcommand", "rowcolor", "cellcolor", "color", "pagestyle",
    "thispagestyle", "captionsetup", "hypersetup", "addcontentsline", "fontsize", "linespread", "url", "href",
)


def strip_comment(line: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", line)


def prose_lines(text: str):
    """Yield (line number, text) for narrative lines: no comments, tables, drawings or math."""
    depth = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = strip_comment(raw)
        opens, closes = len(BEGIN_RE.findall(line)), len(END_RE.findall(line))
        if depth == 0 and opens == 0:
            prose = re.sub(r"\\url\{[^}]*\}|\\href\{[^}]*\}", "", line)
            prose = re.sub(r"\$[^$]*\$", "", prose)
            prose = re.sub(r"\\\(.*?\\\)|\\\[.*?\\\]", "", prose)
            yield number, prose
        depth = max(0, depth + opens - closes)


def _group_end(text: str, position: int) -> int:
    """Index just after the [..] or {..} group that opens at `position`."""
    opening = text[position]
    closing = "]" if opening == "[" else "}"
    depth, i = 0, position
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _skip_groups(text: str, position: int) -> int:
    while position < len(text) and text[position] in "[{":
        position = _group_end(text, position)
    return position


def _drop_commands(text: str, names, replacement: str = " ") -> str:
    pattern = re.compile(r"\\(?:" + "|".join(names) + r")\*?(?![a-zA-Z])")
    out, position = [], 0
    for match in pattern.finditer(text):
        if match.start() < position:
            continue
        out.append(text[position:match.start()])
        out.append(replacement)
        position = _skip_groups(text, match.end())
    out.append(text[position:])
    return "".join(out)


def _unwrap_caption(text: str) -> str:
    out, position = [], 0
    for match in re.finditer(r"\\caption\*?", text):
        if match.start() < position:
            continue
        out.append(text[position:match.start()])
        start = match.end()
        if text[start:start + 1] == "[":
            start = _group_end(text, start)
        if text[start:start + 1] != "{":
            position = start
            continue
        end = _group_end(text, start)
        out.append("\n\n" + text[start + 1:end - 1] + "\n\n")
        position = end
    out.append(text[position:])
    return "".join(out)


def _strip_inline(text: str) -> str:
    def citation(match: re.Match) -> str:
        return (CITE_TOKEN if match.group(1) in ("citet", "citealt", "citeauthor", "textcite") else "") + CITE_MARK

    text = CITE_RE.sub(citation, text)
    text = _drop_commands(text, DROPPED_COMMANDS)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?", "\n\n", text)
    text = re.sub(r"\\([%&_#])", r"\1", text)
    text = re.sub(r"\\[,;:! ]|\\\\(?:\[[^\]]*\])?", " ", text).replace("~", " ")
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", "").replace("}", "").replace("``", '"').replace("''", '"')
    return text.replace(DOLLAR, "$")


@dataclass
class Paragraph:
    text: str
    listed: bool = False


def latex_paragraphs(tex: str) -> list[Paragraph]:
    """Narrative paragraphs of a LaTeX fragment: the markup goes and its text stays."""
    source = tex.replace(r"\$", DOLLAR)
    raw = source.splitlines()
    lines, last = [], 0
    for number, line in prose_lines(source):
        if raw[number - 1].lstrip().startswith("%"):
            last = number
            continue
        if number != last + 1:
            lines.append("")
        lines.append(line)
        last = number
    text = "\n".join(lines)
    text = _drop_commands(text, SECTION_COMMANDS, "\n\n")
    text = _unwrap_caption(text)
    text = re.sub(r"\\item(?:\[[^\]]*\])?", "\n\n" + ITEM_MARK, text)
    text = _strip_inline(text)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        listed = ITEM_MARK in block
        clean = re.sub(r"\s+", " ", block.replace(ITEM_MARK, " ")).strip()
        clean = re.sub(r"\s+(\ue001*[.,;:])", r"\1", clean)
        if TOKEN_RE.search(clean.replace(CITE_TOKEN, "")):
            paragraphs.append(Paragraph(clean, listed))
    return paragraphs


# --- Text model ---------------------------------------------------------------

@dataclass
class Sentence:
    block: str
    paragraph: int
    index: int
    text: str
    collapsed: str
    words: list[str]
    cited: bool
    listed: bool


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _is_abbreviation(text: str, dot: int) -> bool:
    if text[dot] != ".":
        return False
    match = re.search(r"([^\W\d_]+(?:\.[^\W\d_]+)*)$", text[:dot])
    if not match:
        return False
    word = match.group(1)
    if len(word) == 1 and word.isupper():
        return True
    if word.lower() == "al":
        return text[:match.start()].rstrip().lower().endswith("et")
    return word.lower() in ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    sentences, start = [], 0
    for match in SENTENCE_END_RE.finditer(text):
        position = match.end()
        while position < len(text) and text[position] in OPENING_PUNCTUATION:
            position += 1
        if position >= len(text):
            continue
        following = text[position]
        opens = following.isupper() or following.isdigit() or following == "⟦" or text[match.end()] in "¿¡"
        if opens and not _is_abbreviation(text, match.start()):
            sentences.append(text[start:match.end()].strip())
            start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def mattr(words: list[str], window: int) -> float | None:
    """Mean type-token ratio over sliding windows; None below one full window."""
    if len(words) < window:
        return None
    counts = Counter(words[:window])
    total = len(counts)
    windows = 1
    for i in range(window, len(words)):
        counts[words[i]] += 1
        counts[words[i - window]] -= 1
        if counts[words[i - window]] == 0:
            del counts[words[i - window]]
        total += len(counts)
        windows += 1
    return total / (windows * window)


class Collapser:
    """Replaces each glossary phrase with one placeholder token, longest phrase
    first, so a protected term never feeds n-grams, Jaccard, MATTR or the catalog."""

    def __init__(self, glossary: Sequence[str]) -> None:
        self.labels: list[str] = []
        self.words: list[tuple[str, ...]] = []
        for label in glossary:
            words = tuple(fold(w) for w in tokenize(str(label)))
            if words and words not in self.words:
                self.words.append(words)
                self.labels.append(str(label))
        self.by_first: dict[str, list[int]] = {}
        for i, words in enumerate(self.words):
            self.by_first.setdefault(words[0], []).append(i)
        for candidates in self.by_first.values():
            candidates.sort(key=lambda i: -len(self.words[i]))

    def collapse(self, text: str) -> str:
        matches = list(TOKEN_RE.finditer(text))
        folded = [fold(m.group(0).lower()) for m in matches]
        out, position, i = [], 0, 0
        while i < len(matches):
            hit = None
            for index in self.by_first.get(folded[i], ()):
                words = self.words[index]
                if tuple(folded[i:i + len(words)]) == words:
                    hit = index
                    break
            if hit is None:
                i += 1
                continue
            out.append(text[position:matches[i].start()])
            out.append(f"⟦{hit}⟧")
            position = matches[i + len(self.words[hit]) - 1].end()
            i += len(self.words[hit])
        out.append(text[position:])
        return "".join(out)

    def restore(self, text: str) -> str:
        text = PLACEHOLDER_RE.sub(lambda m: self.labels[int(m.group(1))], text)
        return text.replace(CITE_TOKEN, "(cite)").replace(CITE_MARK, "")


def build_sentences(blocks: Mapping[str, str], collapser: Collapser) -> list[Sentence]:
    sentences = []
    for block_id, tex in blocks.items():
        index = 0
        for number, paragraph in enumerate(latex_paragraphs(tex), start=1):
            for text in split_sentences(paragraph.text):
                collapsed = collapser.collapse(text)
                words = tokenize(collapsed)
                if not words:
                    continue
                index += 1
                sentences.append(Sentence(block_id, number, index, collapser.restore(text), collapsed, words,
                                          CITE_MARK in text, paragraph.listed))
    return sentences


# --- Findings -----------------------------------------------------------------

HINTS = {
    "cliche": "Replace the stock phrase with what the work does: a direct verb, its object and, when there is one, its figure.",
    "comodin": "Keep the adjective only when it states something measurable; otherwise name the concrete property.",
    "promocional": "Replace the praise with the technical scope or the evidence that supports it.",
    "atribucion_vaga": "Cite the source in the same sentence, or state the fact without a vague subject.",
    "perifrasis": "Use the short form (a plain verb or preposition) when the periphrasis adds nothing.",
    "copula_evitada": "Prefer a plain copula or 'tener' when the substitute verb adds no meaning.",
    "calco": "Replace the English calque with the native academic Spanish form.",
    "plantilla": "Drop the preamble and open with the substantive statement.",
    "paralelismo_negativo": "State directly what the method does, without the prefabricated contrast.",
    "falso_rango": "Check that both ends sit on one scale; otherwise list the dimensions separately.",
    "register": "Use the neutral academic register: impersonal or first person plural, no second person, no regional vocabulary.",
    "closing_gerund": "Turn the closing gerund into a clause with a conjugated verb, or end on the main statement.",
    "spaced_dash": "Resolve the aside with commas, a semicolon or parentheses; no spaced em dash and no '--' in prose.",
    "long_sentence": "Split the sentence where the idea changes; more than 45 words tire the reader.",
    "triad": "Keep the two items that matter, or rank the enumeration in clauses.",
    "connector_repeat": "Name the logical relation between the sentences and carry it with their content; do not swap one connector for another.",
    "connector_density": "Remove most opening connectors; keep the one whose relation would otherwise be lost.",
    "connector_overuse": "One connector carries the transitions: rebuild some with a subordinate clause or a subject that resumes the previous one.",
    "synthesis_repeat": "Do not close several paragraphs with the same summary formula; end on the result.",
    "opening_repeat": "Change how one of the two sentences opens: a complement, a condition or a figure.",
    "opening_dominant": "Too many sentences open the same way; vary the subject or the opening complement.",
    "demonstrative_opening": "Name the referent instead of opening with a demonstrative and a noun.",
    "causal_density": "Many causal clauses together: keep the explicit relation only where the reader cannot infer it.",
    "relative_tail": "Turn the trailing relative clause into a sentence of its own with a concrete subject.",
    "clause_repeat": "The same subordinate clause repeats in neighbouring sentences; reorder or merge the ideas.",
    "repeated_phrase": "Decide where the phrase belongs and refer back to it briefly afterwards; technical terms stay.",
    "near_duplicate": "Two sentences say almost the same: keep the better wording and every figure.",
    "overuse": "The word weighs far more than the rest of the vocabulary; check whether each use adds something.",
}


def _per_1000(count: float, words: int) -> float:
    return 1000.0 * count / max(words, THRESHOLDS["min_words_for_normalization"])


def _finding(category: str, sentence: Sentence, span: str) -> dict:
    return {"block": sentence.block, "category": category, "fragment": span, "hint": HINTS[category],
            "paragraph": sentence.paragraph, "sentence": sentence.index}


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _is_content(word: str) -> bool:
    return not word.startswith("⟦") and not word[0].isdigit() and fold(word) not in FUNCTION_WORDS


def catalog_findings(sentences: list[Sentence], collapser: Collapser) -> list[dict]:
    th = THRESHOLDS
    findings = []
    words = sum(len(s.words) for s in sentences)
    triads = []
    for s in sentences:
        taken: list[tuple[int, int]] = []
        for category, regex in CATALOG:
            if category == "atribucion_vaga" and s.cited:
                continue
            for match in regex.finditer(s.collapsed):
                if any(a < match.end() and match.start() < b for a, b in taken):
                    continue
                taken.append(match.span())
                findings.append(_finding(category, s, collapser.restore(match.group(0))))
        tail = GERUND_TAIL_RE.search(s.collapsed)
        if tail and tail.group(1).lower() not in NOT_GERUNDS:
            findings.append(_finding("closing_gerund", s, collapser.restore(tail.group(0).strip(" ,."))))
        for match in DASH_RE.finditer(s.collapsed):
            findings.append(_finding("spaced_dash", s,
                                     collapser.restore(s.collapsed[max(0, match.start() - 20):match.end() + 20])))
        if len(s.words) > th["long_sentence_words"]:
            findings.append(_finding("long_sentence", s, s.text[:160]))
        if not s.listed:
            for match in TRIAD_RE.finditer(s.collapsed):
                if not {fold(g.lower()) for g in match.groups()} & FUNCTION_WORDS:
                    triads.append((s, match.group(0)))
    if len(triads) >= 2 and _per_1000(len(triads), words) > th["triad_per_1000"]:
        findings += [_finding("triad", s, span) for s, span in triads]
    return findings


def _opening_connector(sentence: Sentence) -> str | None:
    match = CONNECTOR_RE.match(fold(sentence.collapsed.lstrip("¿¡«\"(").lower()))
    return match.group(1) if match else None


def flow_findings(sentences: list[Sentence]) -> list[dict]:
    """Connector, opening and clause patterns of one block (windows never cross blocks)."""
    th = THRESHOLDS
    prose = [s for s in sentences if not s.listed]
    words = sum(len(s.words) for s in sentences)
    n = len(prose)
    findings: list[dict] = []

    openers = [(s, _opening_connector(s)) for s in prose]
    counts: Counter = Counter()
    last_seen: dict[str, int] = {}
    for position, (s, connector) in enumerate(openers):
        if not connector:
            continue
        counts[connector] += 1
        previous = last_seen.get(connector)
        if previous is not None and position - previous < th["connector_window"]:
            findings.append(_finding("connector_repeat", s, connector))
        last_seen[connector] = position
    opened = sum(counts.values())
    if n >= 4 and opened / n > th["connector_share"]:
        findings.append(_finding("connector_density", prose[0], f"{opened} of {n} sentences open with a connector"))
    for connector, count in sorted(counts.items()):
        if count >= 3 and _per_1000(count, words) > th["connector_overuse_per_1000"]:
            first = next(s for s, c in openers if c == connector)
            findings.append(_finding("connector_overuse", first, connector))
    synthesis = [(s, c) for s, c in openers if c in SYNTHESIS_CONNECTORS]
    if len(synthesis) >= 2 and (words < 1000 or _per_1000(len(synthesis), words) > th["synthesis_per_1000"]):
        findings += [_finding("synthesis_repeat", s, c) for s, c in synthesis[1:]]

    def opening(s: Sentence) -> str | None:
        head = s.words[:2]
        return " ".join(head) if len(head) == 2 and not any(w.startswith("⟦") for w in head) else None

    bigrams = [opening(s) for s in prose]
    for i in range(1, n):
        if bigrams[i] and bigrams[i] == bigrams[i - 1]:
            findings.append(_finding("opening_repeat", prose[i], bigrams[i]))
    for bigram, count in sorted(Counter(b for b in bigrams if b).items()):
        if n >= 6 and count >= 3 and count / n > th["opening_dominant"]:
            findings.append(_finding("opening_dominant", prose[bigrams.index(bigram)], bigram))
    demonstratives = []
    for s in prose:
        match = DEMONSTRATIVE_RE.match(s.collapsed)
        if match and match.group(1).lower() not in VERBS_AFTER_DEMONSTRATIVE:
            demonstratives.append((s, match.group(0)))
    if n >= 4 and len(demonstratives) >= 3 and len(demonstratives) / n > th["demonstrative_share"]:
        findings += [_finding("demonstrative_opening", s, span) for s, span in demonstratives]

    for regex, category, limit in ((CAUSAL_RE, "causal_density", th["causal_per_1000"]),
                                   (TAIL_RE, "relative_tail", th["relative_tail_per_1000"])):
        hits = [(position, s, m.group(0).strip(", ")) for position, s in enumerate(prose)
                for m in regex.finditer(s.collapsed)]
        if len(hits) >= 2 and _per_1000(len(hits), words) > limit:
            seen = set()
            for _, s, span in hits:
                if s.index not in seen:
                    seen.add(s.index)
                    findings.append(_finding(category, s, span))
        for (before, _, _), (position, s, span) in zip(hits, hits[1:]):
            if 0 < position - before < th["clause_window"]:
                findings.append(_finding("clause_repeat", s, span))
    return findings


SUMMARY_BLOCK_RE = re.compile(r"abstract|resumen|summary|highlight|keyword|title", re.I)


def redundancy_findings(sentences: list[Sentence], collapser: Collapser) -> list[dict]:
    """Repeated phrases and near-duplicates inside `sentences`. An abstract may
    repeat the body it condenses, so that pairing alone never produces a finding.
    Each finding carries `locations`, the (block, sentence) pairs it spans."""
    th = THRESHOLDS
    size = th["ngram"]

    def is_summary(s: Sentence) -> bool:
        return bool(SUMMARY_BLOCK_RE.search(s.block))

    grams: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    for i, s in enumerate(sentences):
        for start in range(len(s.words) - size + 1):
            gram = tuple(s.words[start:start + size])
            if sum(1 for w in gram if _is_content(w)) >= th["ngram_content_words"]:
                grams.setdefault(gram, []).append((i, start))
    paragraphs_total = len({(s.block, s.paragraph) for s in sentences})
    minimum_paragraphs = th["ngram_paragraphs"] if paragraphs_total >= 2 else 1

    def qualifies(hits) -> bool:
        return (len({i for i, _ in hits}) >= th["ngram_sentences"]
                and len({(sentences[i].block, sentences[i].paragraph) for i, _ in hits}) >= minimum_paragraphs)

    covered: dict[int, set[int]] = {}
    for gram, hits in grams.items():
        if not qualifies(hits):
            continue
        body = [h for h in hits if not is_summary(sentences[h[0]])] or hits
        if not qualifies(body):
            continue
        for i, start in hits:
            covered.setdefault(i, set()).update(range(start, start + size))

    phrases: dict[tuple[str, ...], list[int]] = {}
    for i, positions in covered.items():
        ordered = sorted(positions)
        begin = previous = ordered[0]
        for position in ordered[1:] + [None]:
            if position is not None and position == previous + 1:
                previous = position
                continue
            phrases.setdefault(tuple(sentences[i].words[begin:previous + 1]), []).append(i)
            if position is not None:
                begin = previous = position
    findings: list[dict] = []
    reported: list[tuple[str, set[int]]] = []
    for phrase, hits in sorted(phrases.items(), key=lambda kv: (-len(kv[0]), kv[0])):
        text = " ".join(phrase)
        if any(text in longer and set(hits) <= where for longer, where in reported):
            continue
        reported.append((text, set(hits)))
        ordered = sorted(set(hits))
        finding = _finding("repeated_phrase", sentences[ordered[0]], collapser.restore(text))
        finding["locations"] = [sentences[i] for i in ordered]
        findings.append(finding)

    content = [frozenset(fold(w) for w in s.words if _is_content(w)) for s in sentences]
    least, limit = th["jaccard_min_words"], th["jaccard"]
    for i, one in enumerate(content):
        if len(one) < least:
            continue
        for j in range(i + 1, len(content)):
            two = content[j]
            if len(two) < least or min(len(one), len(two)) < limit * max(len(one), len(two)):
                continue
            if len(one & two) / len(one | two) < limit:
                continue
            a, b = sentences[i], sentences[j]
            if is_summary(a) != is_summary(b):
                continue
            finding = _finding("near_duplicate", b, b.text[:160])
            finding["locations"] = [a, b]
            findings.append(finding)
    return findings


def overuse_findings(sentences: list[Sentence], domain: set[str]) -> list[dict]:
    """Words far above the text's own vocabulary, most used first. A word that
    mostly follows an article or `de` is topic vocabulary and stays out, and so
    does every word of the glossary."""
    th = THRESHOLDS
    counts: Counter = Counter()
    nominal: Counter = Counter()
    for s in sentences:
        for previous, word in zip([""] + s.words, s.words):
            if len(word) >= 5 and word[0].isalpha() and fold(word) not in FUNCTION_WORDS:
                counts[word] += 1
                nominal[word] += previous in NOUN_CONTEXT
    repeated = [c for c in counts.values() if c >= 2]
    baseline = statistics.median(repeated) if len(repeated) >= th["overuse_types_for_median"] else 1
    limit = max(th["overuse_min_count"], th["overuse_times_median"] * baseline)
    findings = []
    for word, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < limit or nominal[word] / count >= th["overuse_noun_context"] or fold(word) in domain:
            continue
        if len(findings) == th["overuse_max"]:
            break
        first = next(s for s in sentences if word in s.words)
        findings.append(_finding("overuse", first, word))
    return findings


# --- Scoring ------------------------------------------------------------------

def _counts_by_family(findings: list[dict]) -> dict[str, int]:
    families = {"catalog": STYLE_CATEGORIES, "overuse": {"overuse"}, "connectors": CONNECTOR_CATEGORIES,
                "openings": OPENING_CATEGORIES, "clauses": CLAUSE_CATEGORIES,
                "redundancy": REDUNDANCY_CATEGORIES, "templates": TEMPLATE_CATEGORIES}
    return {name: sum(1 for f in findings if f["category"] in categories) for name, categories in families.items()}


def score(sentences: list[Sentence], findings: list[dict]) -> dict:
    """`index`, the three scores (0 to 1, lower is better) and the verdict."""
    th = THRESHOLDS
    words = [w for s in sentences for w in s.words]
    total = len(words)
    if not total:
        return {"index": None, "style_score": None, "flow_score": None, "redundancy_score": None, "verdict": None}
    lengths = [len(s.words) for s in sentences]
    alpha = [w for w in words if not w[0].isdigit() and w != CITE_TOKEN]
    diversity = mattr(alpha, th["mattr_window"])
    long_share = sum(1 for n in lengths if n > th["long_sentence_words"]) / len(lengths)

    counts = _counts_by_family(findings)
    saturation = th["saturation_per_1000"]
    families = {name: _clip(_per_1000(count, total) / saturation[name]) for name, count in counts.items()}
    families["long_sentences"] = _clip((long_share - th["long_share_floor"])
                                       / (th["long_share_ceiling"] - th["long_share_floor"]))
    families["mattr"] = 0.0 if diversity is None else 1.0 - _clip(
        (diversity - th["mattr_floor"]) / (th["mattr_ceiling"] - th["mattr_floor"]))
    style = round(sum(weight * families[name] for name, weight in th["style_weights"].items()), 3)
    flow = round(sum(weight * families[name] for name, weight in th["flow_weights"].items()), 3)
    penalty = (style + flow) / 2
    bands = th["bands"]
    verdict = "clear" if penalty <= bands["clear"] else "uneven" if penalty <= bands["uneven"] else "needs_revision"
    return {"index": round(100 * (1 - penalty)), "style_score": style, "flow_score": flow,
            "redundancy_score": round(families["redundancy"], 3), "verdict": verdict}


def _public(finding: dict) -> dict:
    return {key: finding[key] for key in ("category", "fragment", "hint", "paragraph", "sentence")}


def _order(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: (f["paragraph"], f["sentence"], f["category"], f["fragment"]))


def audit_text(text: str, *, glossary: Sequence[str] = ()) -> dict:
    """The index, the three scores, the verdict and every finding of one block."""
    collapser = Collapser(glossary)
    sentences = build_sentences({"text": text}, collapser)
    domain = {w for words in collapser.words for w in words}
    findings = (catalog_findings(sentences, collapser) + flow_findings(sentences)
                + redundancy_findings(sentences, collapser) + overuse_findings(sentences, domain))
    report = score(sentences, findings)
    report["findings"] = [_public(f) for f in _order(findings)]
    return report


def audit_document(blocks: Mapping[str, str], *, glossary: Sequence[str] = ()) -> dict:
    """Each block scored on its own, the whole document scored together, and the
    repeated phrases and near-duplicates that cross blocks."""
    collapser = Collapser(glossary)
    every = build_sentences(blocks, collapser)
    domain = {w for words in collapser.words for w in words}
    by_block = {block_id: [s for s in every if s.block == block_id] for block_id in blocks}

    local: dict[str, list[dict]] = {}
    for block_id, group in by_block.items():
        local[block_id] = (catalog_findings(group, collapser) + flow_findings(group)
                           + redundancy_findings(group, collapser))
    crossing, cross_findings = [], []
    for finding in redundancy_findings(every, collapser):
        places = sorted({s.block for s in finding["locations"]}, key=list(blocks).index)
        if len(places) < 2:
            continue
        cross_findings.append(finding)
        key = "phrase" if finding["category"] == "repeated_phrase" else "sentence"
        crossing.append({key: finding["fragment"], "blocks": places})
    overuse = overuse_findings(every, domain)
    for finding in overuse:
        local[finding["block"]].append(finding)

    all_findings = [f for group in local.values() for f in group] + cross_findings
    report_blocks = []
    for block_id, group in by_block.items():
        entry = {"id": block_id, **score(group, local[block_id])}
        entry["findings"] = [_public(f) for f in _order(local[block_id])]
        report_blocks.append(entry)
    return {"document": score(every, all_findings), "blocks": report_blocks, "cross_block_redundancy": crossing}


# --- Fidelity -----------------------------------------------------------------

MATH_RE = re.compile(r"(?<!\\)\$\$(.*?)(?<!\\)\$\$|(?<!\\)\$((?:[^$\\]|\\.)*?)(?<!\\)\$|\\\((.*?)\\\)|\\\[(.*?)\\\]", re.S)
DISPLAY_ENV_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|flalign|alignat|math|displaymath)(\*?)\}(.*?)"
    r"\\end\{\1\2\}", re.S)
# An attached unit is part of the figure: 120ms and 125ms differ as whole tokens.
NUMBER_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*[^\W_]*")
DIGIT_GROUP_RE = re.compile(r"(?<=\d)(?:\s|\\,|~|\\;|\\ )(?=\d{3}(?!\d))")
REF_RE = re.compile(r"\\(?:ref|cref|Cref|pageref|eqref|autoref|nameref)\*?\{([^}]*)\}")
LABEL_RE = re.compile(r"\\label\{([^}]*)\}")


def _normal_math(text: str) -> str:
    return re.sub(r"\s+|~", "", text).replace("{,}", ".")


def _normal_number(token: str) -> str:
    """1,500 / 1.500 / 1500 are one number; 0,25 and 0.25 are one number."""
    match = re.match(r"(\d+(?:[.,]\d+)*)(.*)", token)
    figure, unit = match.group(1), match.group(2)
    figure = figure.replace(",", ".")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", figure) and not figure.startswith("0"):
        figure = figure.replace(".", "")
    return figure + unit


def extract_facts(text: str) -> dict[str, Counter]:
    body = "\n".join(strip_comment(line) for line in text.splitlines())
    keys = [key.strip() for match in CITE_RE.finditer(body) for key in match.group(2).split(",") if key.strip()]
    refs = [key.strip() for match in REF_RE.finditer(body) for key in match.group(1).split(",") if key.strip()]
    labels = LABEL_RE.findall(body)
    math = [_normal_math(m.group(3)) for m in DISPLAY_ENV_RE.finditer(body)]
    visible = DISPLAY_ENV_RE.sub(" ", body)
    math += [_normal_math(next(g for g in m.groups() if g is not None)) for m in MATH_RE.finditer(visible)]
    # A citation keeps its page locator; keys and layout arguments are not facts of the text.
    visible = CITE_RE.sub(lambda m: " ".join(re.findall(r"\[([^\]]*)\]", m.group(0).split("{")[0])), visible)
    visible = MATH_RE.sub(" ", visible)
    visible = _drop_commands(visible, DROPPED_COMMANDS)
    visible = visible.replace(r"\$", " ").replace(r"\%", " %")
    visible = DIGIT_GROUP_RE.sub("", visible)
    return {
        "number": Counter(_normal_number(n) for n in NUMBER_RE.findall(visible)),
        "citation": Counter(keys),
        "label": Counter(labels),
        "reference": Counter(refs),
        "math": Counter(math),
    }


def compare_facts(english: str, spanish: str) -> list[str]:
    """Every fact of `english` that `spanish` does not keep, one line each; empty
    when the translation is faithful in citations, label and reference targets,
    math, numbers with their units and paragraph count."""
    differences = []
    one, two = extract_facts(english), extract_facts(spanish)
    for kind in one:
        missing = sorted((one[kind] - two[kind]).elements())
        added = sorted((two[kind] - one[kind]).elements())
        if missing or added:
            differences.append(f"{kind}: missing {missing}; added {added}")
    paragraphs = len(latex_paragraphs(english)), len(latex_paragraphs(spanish))
    if paragraphs[0] != paragraphs[1]:
        differences.append(f"paragraphs: english {paragraphs[0]}, spanish {paragraphs[1]}")
    return differences
