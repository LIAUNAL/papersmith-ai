"""paper_ai_metrics: deterministic writing-quality metrics and F5 invariant
verification for academic prose.

These are style checks, not an AI detector. They measure whether a passage
reads well; they never estimate, and never try to lower, the chance that a
passage is recognized as machine-assisted. Using them does not change the
obligation to declare AI use in the manuscript (publisher policies such as
Elsevier's generative-AI declaration, Springer Nature's rule against
presenting AI output as human-derived, and ICMJE's disclosure guidance).

Computes:
1. Cadence (burstiness): coefficient of variation of sentence length
   (CV = sigma / mu). Readable academic prose alternates short and complex
   sentences (CV >= 0.38); a monotone cadence keeps them flat (CV < 0.25).
2. Overused academic phrasing: a closed catalog of words and patterns that
   are overused in academic drafts (e.g., 'delve', 'testament', 'tapestry',
   'paramount', 'pivotal', triadic parallelism, redundant hedges).
3. Lexical diversity: Type-Token Ratio (TTR) and Hapax Legomena ratio.
4. Style score: 0.0 (clear, varied prose) to 1.0 (needs revision).
5. F5 invariant verification: citations, numbers, statistics, and math
   formulas stay untouched during a style revision.
6. Flow and redundancy (``analyze_flow``, reported under the ``flow`` key):
   stock-connector density and repetition, repeated sentence openings,
   "because" / "where" / ", which" density outside the symbol-defining
   "where" that follows an equation, cross-paragraph repeated phrases and
   near-duplicate sentences, and template phrasing. Every finding names its
   sentence and paragraph and quotes its span; ``flow_score`` runs from 0.0
   (varied, non-redundant) to 1.0 (needs revision). The style score above is
   unchanged by this pass.
"""
from __future__ import annotations

import math
import re
from typing import Any

#: Stated by every style report: the metrics judge readability only.
DISCLOSURE_NOTICE = (
    "Style metrics measure readability only; a passing style score does not "
    "change the obligation to declare AI use in the manuscript."
)

# Closed catalog of overused academic words and hyperbolic vocabulary
OVERUSED_ACADEMIC_WORDS: tuple[str, ...] = (
    "delve", "delves", "delving",
    "testament", "testaments",
    "tapestry", "tapestries",
    "beacon", "beacons",
    "paramount",
    "multifaceted",
    "bespoke",
    "meticulously", "meticulous",
    "underscore", "underscores", "underscoring",
    "seamless", "seamlessly",
    "nuanced", "nuance", "nuances",
    "holistic", "holistically",
    "foster", "fosters", "fostering",
    "pivotal",
    "interplay",
    "overarching",
    "realm", "realms",
    "landscape", "landscapes",
    "bolster", "bolsters", "bolstering",
    "vibrant",
    "revolutionize", "revolutionizes", "revolutionizing",
    "game-changer", "game-changing",
    "crucial", "crucially",
    "indispensable",
    "harness", "harnessing", "harnesses",
    "unravel", "unraveling", "unravels",
    "sheds light", "shed light",
    "pave the way", "paves the way",
    "cornerstone", "cornerstones",
    "imperative",
    "quintessential",
    "intricacies", "intricacy",
)
#: Deprecated alias of ``OVERUSED_ACADEMIC_WORDS``, kept for one release.
CLAUDE_WORDS = OVERUSED_ACADEMIC_WORDS

# Common formulaic transitions and redundant hedges
FORMULAIC_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnot only\b.*?\bbut\s+(?:[a-z]+\s+)?also\b", "not_only_but_also"),
    (r"\bit is (?:worth noting|important to note|noteworthy) that\b", "redundant_hedge"),
    (r"\bin summary,\b|\bin conclusion,\b|\bto summarize,\b", "formulaic_summary"),
    (r"\bplay(?:s)? a (?:crucial|pivotal|vital|key) role in\b", "cliche_role"),
    (r"\ba wide (?:array|variety|range) of\b", "vague_quantifier"),
    (r"\bserve(?:s)? as a testament to\b", "testament_phrase"),
    (r"\bdelv(?:e|es|ed|ing) (?:into|deeper into)\b", "delve_phrase"),
    (r"\bnavigat(?:e|es|ing) the (?:complexities|challenges) of\b", "navigate_cliche"),
)

# Triadic parallelism: three parallel adverbs/nouns/adjectives joined by 'and'
TRIADIC_RE = re.compile(
    r"\b([a-zA-Z]+(?:ing|tion|sion|ity|ness|ment|able|ible|ive|al|cy|ence|ance)),\s+"
    r"([a-zA-Z]+(?:ing|tion|sion|ity|ness|ment|able|ible|ive|al|cy|ence|ance)),\s+and\s+"
    r"([a-zA-Z]+(?:ing|tion|sion|ity|ness|ment|able|ible|ive|al|cy|ence|ance))\b",
    re.IGNORECASE,
)

_MATH_INLINE_RE = re.compile(r"\$[^$]*\$|\\\(.*?\\\)")
_MATH_DISPLAY_RE = re.compile(
    r"\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(?:equation|align|gather|math)\*?\}.*?\\end\{(?:equation|align|gather|math)\*?\}",
    re.DOTALL,
)
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
_CITE_RE = re.compile(r"\\(?:cite[a-z]*|citep|citet)\*?(?:\[[^\]]*\])?\{([^}]+)\}|\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
_NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|ms|s|hz|khz|mhz|ghz|db|kb|mb|gb|tb|k|m|b)?\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\\])")
_TOKEN_RE = re.compile(r"[a-z0-9']+")


def strip_latex_markup(text: str) -> str:
    """Removes LaTeX math and commands for clean prose analysis."""
    text = _MATH_DISPLAY_RE.sub(" ", text)
    text = _MATH_INLINE_RE.sub(" ", text)
    text = _LATEX_CMD_RE.sub(" ", text)
    return text


def tokenize(text: str) -> list[str]:
    """Tokenizes text into lowercase word tokens."""
    clean = strip_latex_markup(text)
    return _TOKEN_RE.findall(clean.lower())


def split_sentences(text: str) -> list[str]:
    """Splits body text into sentences while protecting citations and math."""
    # First protect display math from splitting
    cleaned = _MATH_DISPLAY_RE.sub(" [DISPLAY_MATH] ", text)
    raw_sentences = _SENTENCE_SPLIT_RE.split(cleaned.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences


def compute_burstiness(sentences: list[str]) -> dict[str, Any]:
    """Computes sentence length distribution and burstiness metrics."""
    if not sentences:
        return {
            "sentence_count": 0,
            "mean_length": 0.0,
            "std_length": 0.0,
            "cv": 0.0,
            "burstiness_penalty": 1.0,
        }

    lengths = [len(tokenize(s)) for s in sentences]
    # Filter out empty lengths if any
    valid_lengths = [l for l in lengths if l > 0]
    if not valid_lengths:
        return {
            "sentence_count": 0,
            "mean_length": 0.0,
            "std_length": 0.0,
            "cv": 0.0,
            "burstiness_penalty": 1.0,
        }

    n = len(valid_lengths)
    mean_len = sum(valid_lengths) / n
    if n > 1:
        variance = sum((l - mean_len) ** 2 for l in valid_lengths) / (n - 1)
        std_len = math.sqrt(variance)
    else:
        std_len = 0.0

    cv = (std_len / mean_len) if mean_len > 0 else 0.0

    # Burstiness penalty:
    # CV >= 0.45: 0.0 (varied cadence)
    # CV == 0.35: ~0.2
    # CV <= 0.20: 1.0 (monotone cadence)
    if cv >= 0.45:
        burstiness_penalty = 0.0
    elif cv <= 0.20:
        burstiness_penalty = 1.0
    else:
        burstiness_penalty = (0.45 - cv) / 0.25

    return {
        "sentence_count": n,
        "lengths": valid_lengths,
        "mean_length": round(mean_len, 2),
        "std_length": round(std_len, 2),
        "cv": round(cv, 3),
        "burstiness_penalty": round(burstiness_penalty, 3),
    }


def detect_cliches(text: str) -> list[dict[str, Any]]:
    """Detects overused academic words, hyperbolic vocabulary, and formulaic patterns."""
    findings: list[dict[str, Any]] = []
    clean_text = strip_latex_markup(text)

    # 1. Overused academic words
    for word in OVERUSED_ACADEMIC_WORDS:
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            start = max(0, match.start() - 25)
            end = min(len(clean_text), match.end() + 25)
            context = clean_text[start:end].strip()
            findings.append({
                "type": "word",
                "target": match.group(0),
                "category": "overused_word",
                "start": match.start(),
                "end": match.end(),
                "context": f"...{context}...",
            })

    # 2. Formulaic phrases
    for regex_str, category in FORMULAIC_PATTERNS:
        pattern = re.compile(regex_str, re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            findings.append({
                "type": "phrase",
                "target": match.group(0),
                "category": category,
                "start": match.start(),
                "end": match.end(),
                "context": match.group(0),
            })

    # 3. Triadic parallelism
    for match in TRIADIC_RE.finditer(clean_text):
        findings.append({
            "type": "syntax",
            "target": match.group(0),
            "category": "triadic_parallelism",
            "start": match.start(),
            "end": match.end(),
            "context": match.group(0),
        })

    return findings


def compute_lexical_diversity(tokens: list[str]) -> dict[str, float]:
    """Computes Type-Token Ratio (TTR) and Hapax Legomena ratio."""
    total = len(tokens)
    if total == 0:
        return {"ttr": 0.0, "hapax_ratio": 0.0}

    unique = set(tokens)
    ttr = len(unique) / total
    hapax_count = sum(1 for token in unique if tokens.count(token) == 1)
    hapax_ratio = hapax_count / len(unique) if unique else 0.0

    return {
        "ttr": round(ttr, 3),
        "hapax_ratio": round(hapax_ratio, 3),
    }


# --- flow and redundancy ------------------------------------------------------

#: Stock connectors that open a sentence. Each is legitimate once; the pass
#: flags density and repetition, never a single use.
STOCK_CONNECTORS: tuple[str, ...] = (
    "taken together", "in particular", "in addition", "in contrast", "as a result",
    "to this end", "in this context", "in this regard", "on the other hand",
    "in summary", "in conclusion", "to summarize", "in short", "all in all",
    "however", "moreover", "furthermore", "additionally", "notably", "specifically",
    "overall", "importantly", "consequently", "therefore", "thus", "hence", "indeed",
    "conversely", "finally", "interestingly", "crucially", "accordingly",
    "nevertheless", "nonetheless", "similarly", "likewise", "subsequently", "ultimately",
)
#: Connectors that announce a synthesis; repeated, they close every paragraph alike.
SYNTHESIS_CONNECTORS: tuple[str, ...] = (
    "overall", "taken together", "in summary", "in conclusion", "to summarize",
    "in short", "all in all",
)

#: Template phrasing that reads as filler in academic prose (label, regex).
ROBOTIC_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("it_is_worth_noting", r"\bit (?:is|should be) (?:worth noting|important to note|noted|noteworthy) that\b"),
    ("plays_a_role", r"\bplay(?:s|ed|ing)? an? (?:crucial|key|pivotal|vital|central|significant|critical|fundamental|important) role\b"),
    ("in_this_context", r"\bin this (?:context|regard|sense)\b"),
    ("serves_as", r"\bserv(?:e|es|ed|ing) as\b"),
    ("this_highlights", r"\b(?:this|these|which) (?:highlights?|underscores?|demonstrates?|emphasizes?|showcases?)\b"),
    ("findings_suggest", r"\bthese (?:findings|results) (?:highlight|underscore|demonstrate|suggest|indicate|confirm|reveal)\b"),
    ("participle_tail", r",\s+(?:highlighting|underscoring|demonstrating|showcasing|emphasizing|showing|yielding|enabling|paving)\b"),
    ("evaluative_which_tail", r",\s+which (?:indicates|suggests|highlights|demonstrates|underscores|shows|confirms|reflects|makes)\b"),
    ("growing_attention", r"\b(?:a growing body of|in recent years|has (?:garnered|gained) (?:significant |considerable |increasing )?attention)\b"),
    ("paves_the_way", r"\b(?:pav(?:e|es|ed|ing) the way|open(?:s|ed|ing)? (?:up )?new avenues)\b"),
    ("it_is_clear", r"\bit is (?:clear|evident|apparent) that\b"),
    ("by_leveraging", r"\bleverag(?:e|es|ed|ing)\b"),
    ("in_order_to", r"\bin order to\b"),
)

#: Thresholds of the flow pass; reported with every result so a reader can
#: re-derive each finding.
FLOW_THRESHOLDS: dict[str, float] = {
    "connector_window_sentences": 5,          # same connector twice within N sentences
    "connector_opener_share": 0.25,           # share of sentences opened by a stock connector
    "connector_overuse_per_1000": 3.0,        # one connector, at least 3 uses, above this rate
    "synthesis_per_1000": 0.5,                # synthesis connectors in texts of 1000+ words
    "opening_dominant_share": 0.15,           # one opening bigram opening this share of sentences
    "demonstrative_opener_share": 0.15,       # "This/These + noun" openers
    "because_per_1000": 4.0,
    "where_prose_per_1000": 2.0,
    "which_tail_per_1000": 3.0,
    "clause_window_sentences": 3,             # same subordinator twice within N sentences
    "ngram_size": 5,
    "ngram_min_paragraphs": 2,                # with at least 3 sentences
    "near_duplicate_jaccard": 0.6,
    "near_duplicate_min_words": 6,
}

#: Rewrite instruction per finding category, emitted beside the findings.
FLOW_GUIDANCE: dict[str, str] = {
    "connector_repeat": "Do not open two nearby sentences with the same connector. Name the relation "
        "(contrast, cause, consequence, elaboration, example) and express it with the sentence's own "
        "content, or drop the connector when the order of the sentences already carries it.",
    "connector_density": "Too many sentences open with a stock connector. Remove most of them; keep a "
        "connector only where the logical relation would otherwise be lost.",
    "connector_overuse": "One connector carries most transitions. Vary the means: a subordinate clause "
        "(although, since, so that), a subject that points back (that gap, this cost), or no connector.",
    "synthesis_repeat": "Several paragraphs close with a synthesis connector (Overall, Taken together). "
        "State the conclusion directly, once, where it is earned.",
    "opening_repeat": "Consecutive sentences start with the same words. Reorder so the new information "
        "or the subject that changed comes first.",
    "opening_dominant": "One opening dominates the passage. Vary sentence openings: subject, "
        "a short clause, a figure or table as subject, or an object fronted for emphasis.",
    "demonstrative_opener": "Too many sentences open with This/These + noun. Name the referent "
        "precisely or merge the sentence into the one before it.",
    "because_density": "\"because\" recurs. Keep it for causes the method or data establish; express "
        "other causal links with a verb (stems from, follows from) or by sentence order.",
    "where_prose": "\"where\" is used outside equations. Keep \"where\" for the clause that defines "
        "symbols after an equation; elsewhere use \"in which\", \"when\", or two sentences.",
    "which_tail": "Sentences trail off in \", which ...\" clauses. Promote the evaluation to its own "
        "sentence or make it the main verb.",
    "clause_repeat": "The same subordinator recurs in nearby sentences. Vary the construction or split "
        "the sentence.",
    "repeated_phrase": "The same multi-word phrase recurs across paragraphs. After its first full use, "
        "refer to it by its short name or by what changed.",
    "near_duplicate": "Two sentences say nearly the same thing. Keep the stronger one and cut or merge "
        "the other.",
    "robotic_template": "Template phrasing adds words without content. Replace it with the specific "
        "claim, or delete it.",
}
#: Always emitted with the guidance: the boundaries of a style revision.
FLOW_INVARIANTS = (
    "Keep every fact, number, statistic, citation, label, and equation byte-identical (F5); "
    "change wording and order only. The revision improves readability; it never aims to hide "
    "AI assistance, and the manuscript's AI-use declaration stays as written."
)

_STOPWORDS = frozenset(
    "a an the of in on at to for from by with and or but nor so as is are was were be been being "
    "this that these those it its their they them we our which who whom whose than then there "
    "into onto over under between across not no all each every any both per via also only".split()
)
_COMMENT_RE = re.compile(r"(?m)(?<!\\)%.*$")
_DISPLAY_TOKEN = "DISPLAYMATHTOKEN"
_DISPLAY_WHERE_RE = re.compile(_DISPLAY_TOKEN + r"[\s,.;:]*where\b", re.IGNORECASE)
_SYMBOL_WHERE_RE = re.compile(r"\bwhere\s*(?:\$|\\\()", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)
_BECAUSE_RE = re.compile(r"\bbecause\b", re.IGNORECASE)
_WHICH_TAIL_RE = re.compile(r",\s+which\b", re.IGNORECASE)
_DEMONSTRATIVE_RE = re.compile(r"^(this|these)\s+([a-z][a-z-]*)\b", re.IGNORECASE)
_VERBS_AFTER_DEMONSTRATIVE = frozenset(
    "is are was were has have shows show suggests suggest indicates indicate means".split()
)


def _flow_units(text: str) -> tuple[list[dict[str, Any]], int]:
    """Splits text into sentences with their paragraph, keeping a marker where a
    displayed equation stood so the symbol-defining "where" can be told apart."""
    text = _COMMENT_RE.sub("", text)
    text = _MATH_DISPLAY_RE.sub(f" {_DISPLAY_TOKEN} ", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[dict[str, Any]] = []
    for p_idx, para in enumerate(paragraphs, start=1):
        flat = re.sub(r"\s+", " ", para).strip()
        for raw in _SENTENCE_SPLIT_RE.split(flat):
            raw = raw.strip()
            prose = re.sub(r"\s+", " ", strip_latex_markup(raw).replace(_DISPLAY_TOKEN, " ")).strip()
            words = _TOKEN_RE.findall(prose.lower())
            if not words:
                continue
            units.append({"index": len(units) + 1, "paragraph": p_idx, "raw": raw,
                          "prose": prose, "words": words})
    return units, len(paragraphs)


def _opening_connector(prose: str) -> str | None:
    head = prose.lstrip(" ([{\"'").lower()
    for conn in STOCK_CONNECTORS:
        if head.startswith(conn) and (len(head) == len(conn) or not head[len(conn)].isalnum()):
            return conn
    return None


def _finding(category: str, unit: dict[str, Any], span: str, **extra: Any) -> dict[str, Any]:
    return {"category": category, "sentence": unit["index"], "paragraph": unit["paragraph"],
            "span": span, **extra}


def analyze_flow(text: str) -> dict[str, Any]:
    """Measures transitions, sentence openings, subordinate-clause density,
    redundancy, and template phrasing. Every finding carries its sentence and
    paragraph index (1-based, counted by this pass) and the quoted span."""
    th = FLOW_THRESHOLDS
    units, paragraph_count = _flow_units(text)
    words = sum(len(u["words"]) for u in units)
    per_1000 = (lambda k: round(1000.0 * k / words, 2)) if words else (lambda k: 0.0)
    n = len(units)

    # 1. Connectors.
    connector_findings: list[dict[str, Any]] = []
    openers = [(u, _opening_connector(u["prose"])) for u in units]
    counts: dict[str, int] = {}
    last_seen: dict[str, int] = {}
    for u, conn in openers:
        if not conn:
            continue
        counts[conn] = counts.get(conn, 0) + 1
        prev = last_seen.get(conn)
        if prev is not None and u["index"] - prev < th["connector_window_sentences"]:
            connector_findings.append(_finding("connector_repeat", u, conn, previous_sentence=prev))
        last_seen[conn] = u["index"]
    opened = sum(counts.values())
    opener_share = round(opened / n, 3) if n else 0.0
    if n >= 4 and opener_share > th["connector_opener_share"]:
        connector_findings.append({"category": "connector_density", "sentence": None, "paragraph": None,
                                   "span": f"{opened} of {n} sentences open with a stock connector"})
    for conn, k in sorted(counts.items()):
        if k >= 3 and per_1000(k) > th["connector_overuse_per_1000"]:
            first = next(u for u, c in openers if c == conn)
            connector_findings.append(_finding("connector_overuse", first, conn, count=k))
    synth = [(u, c) for u, c in openers if c in SYNTHESIS_CONNECTORS]
    if len(synth) >= 2 and (words < 1000 or per_1000(len(synth)) > th["synthesis_per_1000"]):
        for u, c in synth[1:]:
            connector_findings.append(_finding("synthesis_repeat", u, c, count=len(synth)))

    # 2. Sentence openings.
    opening_findings: list[dict[str, Any]] = []
    bigrams = [" ".join(u["words"][:2]) for u in units]
    for i in range(1, n):
        if len(units[i]["words"]) >= 2 and bigrams[i] == bigrams[i - 1]:
            opening_findings.append(_finding("opening_repeat", units[i], bigrams[i],
                                             previous_sentence=units[i - 1]["index"]))
    bigram_counts: dict[str, int] = {}
    for b in bigrams:
        bigram_counts[b] = bigram_counts.get(b, 0) + 1
    for b, k in sorted(bigram_counts.items()):
        if n >= 6 and k >= 3 and k / n > th["opening_dominant_share"]:
            first = units[bigrams.index(b)]
            opening_findings.append(_finding("opening_dominant", first, b, count=k))
    demonstratives = []
    for u in units:
        m = _DEMONSTRATIVE_RE.match(u["prose"])
        if m and m.group(2).lower() not in _VERBS_AFTER_DEMONSTRATIVE:
            demonstratives.append((u, m.group(0)))
    if n >= 4 and len(demonstratives) >= 3 and len(demonstratives) / n > th["demonstrative_opener_share"]:
        for u, span in demonstratives:
            opening_findings.append(_finding("demonstrative_opener", u, span, count=len(demonstratives)))

    # 3. Subordinate clauses: because, prose where, ", which" tails.
    clause_findings: list[dict[str, Any]] = []
    because_hits, where_hits, which_hits = [], [], []
    exempt_where = 0
    for u in units:
        raw = u["raw"]
        exempt = {m.end() for m in _DISPLAY_WHERE_RE.finditer(raw)} | {
            m.start() + 5 for m in _SYMBOL_WHERE_RE.finditer(raw)}
        for m in _WHERE_RE.finditer(raw):
            if m.end() in exempt or raw[: m.start()].strip() == "" and u["prose"].lower().startswith("where"):
                exempt_where += 1
            else:
                where_hits.append(u)
        because_hits += [u] * len(_BECAUSE_RE.findall(u["prose"]))
        which_hits += [u] * len(_WHICH_TAIL_RE.findall(u["prose"]))
    clause_stats = {
        "because": {"count": len(because_hits), "per_1000_words": per_1000(len(because_hits))},
        "where_prose": {"count": len(where_hits), "per_1000_words": per_1000(len(where_hits)),
                        "exempt_equation_where": exempt_where},
        "which_tail": {"count": len(which_hits), "per_1000_words": per_1000(len(which_hits))},
    }
    for key, hits, category, word, limit in (
        ("because", because_hits, "because_density", "because", th["because_per_1000"]),
        ("where_prose", where_hits, "where_prose", "where", th["where_prose_per_1000"]),
        ("which_tail", which_hits, "which_tail", ", which", th["which_tail_per_1000"]),
    ):
        if len(hits) >= 2 and clause_stats[key]["per_1000_words"] > limit:
            for u in {h["index"]: h for h in hits}.values():
                clause_findings.append(_finding(category, u, word))
        seen: int | None = None
        for u in hits:
            if seen is not None and 0 < u["index"] - seen < th["clause_window_sentences"]:
                clause_findings.append(_finding("clause_repeat", u, word, previous_sentence=seen))
            seen = u["index"]

    # 4. Redundancy: repeated phrases across paragraphs, near-duplicate sentences.
    redundancy_findings: list[dict[str, Any]] = []
    size = int(th["ngram_size"])
    where_gram: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for u in units:
        w = u["words"]
        for i in range(len(w) - size + 1):
            gram = tuple(w[i:i + size])
            if sum(1 for t in gram if t not in _STOPWORDS) >= 3:
                where_gram.setdefault(gram, []).append(u)
    min_paras = th["ngram_min_paragraphs"] if paragraph_count >= 2 else 1
    reported: list[str] = []
    for gram, hits in sorted(where_gram.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sentences = sorted({h["index"] for h in hits})
        paragraphs = sorted({h["paragraph"] for h in hits})
        if len(sentences) < 3 or len(paragraphs) < min_paras:
            continue
        phrase = " ".join(gram)
        if any(" ".join(gram[:-1]) in r or " ".join(gram[1:]) in r for r in reported):
            continue
        reported.append(phrase)
        redundancy_findings.append(_finding("repeated_phrase", hits[0], phrase, count=len(sentences),
                                            sentences=sentences, paragraphs=paragraphs))
    content = [frozenset(t for t in u["words"] if t not in _STOPWORDS and not t.isdigit()) for u in units]
    for i in range(n):
        if len(content[i]) < th["near_duplicate_min_words"]:
            continue
        for j in range(i + 1, n):
            if len(content[j]) < th["near_duplicate_min_words"]:
                continue
            jac = len(content[i] & content[j]) / len(content[i] | content[j])
            if jac >= th["near_duplicate_jaccard"]:
                redundancy_findings.append(_finding("near_duplicate", units[j], units[j]["prose"][:160],
                                                    duplicate_of=units[i]["index"], jaccard=round(jac, 2)))

    # 5. Template phrasing.
    template_findings: list[dict[str, Any]] = []
    for u in units:
        for label, regex in ROBOTIC_TEMPLATES:
            for m in re.finditer(regex, u["prose"], re.IGNORECASE):
                template_findings.append(_finding("robotic_template", u, m.group(0).strip(", "), template=label))
    template_density = round(100.0 * len(template_findings) / words, 2) if words else 0.0

    # Score: each family 0..1, weighted.
    def clip(x: float) -> float:
        return max(0.0, min(1.0, x))

    families = {
        "connectors": clip(len(connector_findings) / 3.0),
        "openings": clip(len(opening_findings) / 4.0),
        "clauses": clip(len(clause_findings) / 4.0),
        "redundancy": clip(len(redundancy_findings) / 3.0),
        "templates": clip(template_density / 1.0),
    }
    weights = {"connectors": 0.25, "openings": 0.15, "clauses": 0.15, "redundancy": 0.25, "templates": 0.20}
    flow_score = round(sum(weights[k] * v for k, v in families.items()), 3) if n else 0.0
    flow_verdict = next(style for bound, style, _ in _STYLE_VERDICTS if flow_score <= bound)

    findings = connector_findings + opening_findings + clause_findings + redundancy_findings + template_findings
    fired = list(dict.fromkeys(f["category"] for f in findings))
    return {
        "flow_score": flow_score,
        "flow_verdict": flow_verdict,
        "word_count": words,
        "sentence_count": n,
        "paragraph_count": paragraph_count,
        "family_penalties": {k: round(v, 3) for k, v in families.items()},
        "connectors": {
            "opening_counts": counts,
            "opener_share": opener_share,
            "per_1000_words": {c: per_1000(k) for c, k in counts.items()},
            "findings": connector_findings,
        },
        "sentence_openings": {
            "demonstrative_openers": len(demonstratives),
            "findings": opening_findings,
        },
        "clauses": {**clause_stats, "findings": clause_findings},
        "redundancy": {"findings": redundancy_findings},
        "robotic_templates": {"count": len(template_findings),
                              "density_per_100_words": template_density,
                              "findings": template_findings},
        "findings": findings,
        "guidance": [FLOW_GUIDANCE[c] for c in fired if c in FLOW_GUIDANCE] + [FLOW_INVARIANTS],
        "thresholds": dict(FLOW_THRESHOLDS),
    }


#: Quality verdict per style-score band, beside the deprecated label the
#: ``verdict`` key carried before (kept for one release so existing readers,
#: e.g. the command center, keep working).
_STYLE_VERDICTS = ((0.20, "clear", "human"), (0.45, "uneven", "mixed"), (1.0, "needs_revision", "ai_flagged"))
DEPRECATED_KEYS: tuple[str, ...] = ("composite_score", "verdict")


def analyze_style(text: str) -> dict[str, Any]:
    """Runs the deterministic writing-quality metrics over one passage."""
    sentences = split_sentences(text)
    tokens = tokenize(text)
    burstiness = compute_burstiness(sentences)
    cliches = detect_cliches(text)
    lexical = compute_lexical_diversity(tokens)

    # Overused-phrasing density: findings per 100 words
    total_tokens = len(tokens)
    cliche_count = len(cliches)
    cliche_density = (cliche_count / (total_tokens / 100.0)) if total_tokens >= 50 else (cliche_count * 2.0)

    # Score components (0.0 to 1.0):
    # - Overused phrasing: density >= 3.0 findings/100w -> 1.0
    cliche_score = min(1.0, cliche_density / 3.0)
    # - Monotone cadence: directly from compute_burstiness
    burstiness_score = burstiness["burstiness_penalty"]
    # - Lexical repetitiveness: low TTR in short texts is penalized
    # Normal academic TTR for 200-500 words is ~0.45 - 0.65
    lexical_penalty = 1.0 - min(1.0, max(0.0, (lexical["ttr"] - 0.35) / 0.25))

    # Style score: without overused phrasing, cadence is a mild check (never
    # above 0.20 on its own); with it, a monotone cadence and low lexical
    # diversity weigh in fully.
    if cliche_count == 0:
        score = (0.15 * burstiness_score) + (0.05 * lexical_penalty)
    else:
        score = (0.50 * cliche_score) + (0.35 * burstiness_score) + (0.15 * lexical_penalty)
    score = round(min(1.0, max(0.0, score)), 3)

    style_verdict, legacy_verdict = next(
        (style, legacy) for bound, style, legacy in _STYLE_VERDICTS if score <= bound
    )

    # Per-sentence evaluation
    sentence_reports = []
    for idx, s in enumerate(sentences):
        s_tokens = tokenize(s)
        s_len = len(s_tokens)
        s_cliches = detect_cliches(s)
        sentence_reports.append({
            "index": idx + 1,
            "sentence": s,
            "word_count": s_len,
            "cliche_count": len(s_cliches),
            "cliches": [c["target"] for c in s_cliches],
            "flagged": len(s_cliches) > 0 or s_len > 45,
        })

    overused = {
        "total_count": cliche_count,
        "density_per_100_words": round(cliche_density, 2),
        "findings": cliches,
    }
    return {
        "style_score": score,
        "style_verdict": style_verdict,
        "monotone_cadence": burstiness_score > 0.5,
        "overused_phrasing": overused,
        "burstiness": burstiness,
        "cliches": overused,
        "lexical_diversity": lexical,
        "sentences": sentence_reports,
        "flow": analyze_flow(text),
        "disclosure_notice": DISCLOSURE_NOTICE,
        # Deprecated aliases, removed in the next release.
        "composite_score": score,
        "verdict": legacy_verdict,
        "deprecated_keys": list(DEPRECATED_KEYS),
    }


#: Deprecated entry point, kept for one release; call ``analyze_style``.
analyze_ai_signatures = analyze_style


def extract_f5_invariants(latex_text: str) -> dict[str, list[str]]:
    """Extracts immutable invariants under the F5 contract."""
    # 1. Citations
    raw_cites = _CITE_RE.findall(latex_text)
    citations: list[str] = []
    for c in raw_cites:
        if isinstance(c, tuple):
            citations.extend(item for item in c if item)
        elif c:
            citations.append(c)

    # 2. Numbers and statistics
    # Strip math environments first so we only check prose-embedded figures
    prose_without_math = _MATH_DISPLAY_RE.sub(" ", latex_text)
    prose_without_math = _MATH_INLINE_RE.sub(" ", prose_without_math)
    numbers = _NUMERIC_RE.findall(prose_without_math.lower())

    # 3. Math environments
    math_displays = _MATH_DISPLAY_RE.findall(latex_text)
    math_inlines = _MATH_INLINE_RE.findall(latex_text)

    return {
        "citations": sorted(citations),
        "numbers": sorted(numbers),
        "math_displays": math_displays,
        "math_inlines": math_inlines,
    }


def verify_f5_invariants(original_latex: str, revised_latex: str) -> tuple[bool, list[str]]:
    """Verifies that a style-revised block preserved every F5 invariant:
    citations, numbers/statistics, and mathematical formulas.
    Returns (passed, list_of_violations).
    """
    violations: list[str] = []
    orig = extract_f5_invariants(original_latex)
    hum = extract_f5_invariants(revised_latex)

    # Check citations
    missing_cites = [c for c in orig["citations"] if c not in hum["citations"]]
    extra_cites = [c for c in hum["citations"] if c not in orig["citations"]]
    if missing_cites:
        violations.append(f"Citations missing or altered: {missing_cites}")
    if extra_cites:
        violations.append(f"Unauthorized citations introduced: {extra_cites}")

    # Check numbers / statistics
    if orig["numbers"] != hum["numbers"]:
        missing_nums = [n for n in orig["numbers"] if orig["numbers"].count(n) > hum["numbers"].count(n)]
        altered_nums = [n for n in hum["numbers"] if hum["numbers"].count(n) > orig["numbers"].count(n)]
        violations.append(
            f"Factual numbers or statistics altered: expected {orig['numbers']}, "
            f"got {hum['numbers']} (missing: {missing_nums}, unauthorized: {altered_nums})"
        )

    # Check display equations
    if len(orig["math_displays"]) != len(hum["math_displays"]):
        violations.append(
            f"Displayed equation count mismatch: original has {len(orig['math_displays'])}, "
            f"revised has {len(hum['math_displays'])}"
        )

    return len(violations) == 0, violations


#: Deprecated alias matching the ``ai_audit`` CLI verb; call ``analyze_style``.
audit_ai_metrics = analyze_style

