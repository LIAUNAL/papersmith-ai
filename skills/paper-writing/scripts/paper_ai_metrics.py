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

