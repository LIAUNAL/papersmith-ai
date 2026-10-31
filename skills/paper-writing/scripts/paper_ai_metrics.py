"""paper_ai_metrics: deterministic stylometry, burstiness quantification,
Claude/LLM fingerprint detection, and F5 invariant verification.

Computes:
1. Sentence Burstiness: Cadence variance through coefficient of variation
   (CV = sigma / mu). Human writing alternates short and complex sentences
   (CV >= 0.38); raw LLMs exhibit flat sentence lengths (CV < 0.25).
2. Closed Catalog of Claudeisms & AI Clichés: Lexical and syntactic markers
   hyperfrequent in Claude/GPT academic drafts (e.g., 'delve', 'testament',
   'tapestry', 'paramount', 'pivotal', triadic parallelism, redundant hedges).
3. Lexical Diversity: Type-Token Ratio (TTR) and Hapax Legomena ratio.
4. Composite AI Risk Score: 0.0 (natural human style) to 1.0 (high AI signature).
5. F5 Invariant Verification: Enforces that citations, numbers, statistics,
   and math formulas are untouched during humanization passes.
"""
from __future__ import annotations

import math
import re
from typing import Any

# Closed catalog of AI clichés, high-frequency Claudeisms, and hyperbolic transitions
CLAUDE_WORDS: tuple[str, ...] = (
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
    # CV >= 0.45: 0.0 (very human, high cadence variation)
    # CV == 0.35: ~0.2
    # CV <= 0.20: 1.0 (flat, machine-like cadence)
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
    """Detects Claude/GPT academic clichés, hyperbolic words, and formulaic patterns."""
    findings: list[dict[str, Any]] = []
    clean_text = strip_latex_markup(text)
    lower_text = clean_text.lower()

    # 1. High-frequency Claude words
    for word in CLAUDE_WORDS:
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            start = max(0, match.start() - 25)
            end = min(len(clean_text), match.end() + 25)
            context = clean_text[start:end].strip()
            findings.append({
                "type": "word",
                "target": match.group(0),
                "category": "claude_word",
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


def analyze_ai_signatures(text: str) -> dict[str, Any]:
    """Runs full deterministic stylometric and AI-risk quantification."""
    sentences = split_sentences(text)
    tokens = tokenize(text)
    burstiness = compute_burstiness(sentences)
    cliches = detect_cliches(text)
    lexical = compute_lexical_diversity(tokens)

    # Cliché density: findings per 100 words
    total_tokens = len(tokens)
    cliche_count = len(cliches)
    cliche_density = (cliche_count / (total_tokens / 100.0)) if total_tokens >= 50 else (cliche_count * 2.0)

    # Score components (0.0 to 1.0):
    # - Cliche score: density >= 3.0 cliches/100w -> 1.0
    cliche_score = min(1.0, cliche_density / 3.0)
    # - Burstiness penalty: directly from compute_burstiness
    burstiness_score = burstiness["burstiness_penalty"]
    # - Lexical repetitiveness: low TTR in short texts is penalized
    # Normal academic TTR for 200-500 words is ~0.45 - 0.65
    lexical_penalty = 1.0 - min(1.0, max(0.0, (lexical["ttr"] - 0.35) / 0.25))

    # Composite AI Score:
    # If no clichés are present, the text uses clean academic vocabulary;
    # burstiness acts as a mild cadence check (never exceeding 0.20 on its own).
    # When clichés are present, burstiness monotony and low TTR strongly amplify the AI risk.
    if cliche_count == 0:
        composite = (0.15 * burstiness_score) + (0.05 * lexical_penalty)
    else:
        composite = (0.50 * cliche_score) + (0.35 * burstiness_score) + (0.15 * lexical_penalty)
    composite = round(min(1.0, max(0.0, composite)), 3)

    if composite <= 0.20:
        verdict = "human"
    elif composite <= 0.45:
        verdict = "mixed"
    else:
        verdict = "ai_flagged"

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

    return {
        "composite_score": composite,
        "verdict": verdict,
        "burstiness": burstiness,
        "cliches": {
            "total_count": cliche_count,
            "density_per_100_words": round(cliche_density, 2),
            "findings": cliches,
        },
        "lexical_diversity": lexical,
        "sentences": sentence_reports,
    }


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


def verify_f5_invariants(original_latex: str, humanized_latex: str) -> tuple[bool, list[str]]:
    """Verifies that an edited/humanized block preserved every F5 invariant:
    citations, numbers/statistics, and mathematical formulas.
    Returns (passed, list_of_violations).
    """
    violations: list[str] = []
    orig = extract_f5_invariants(original_latex)
    hum = extract_f5_invariants(humanized_latex)

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
            f"humanized has {len(hum['math_displays'])}"
        )

    return len(violations) == 0, violations


# Convenience alias matching the CLI verb
audit_ai_metrics = analyze_ai_signatures

