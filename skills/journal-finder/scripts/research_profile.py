"""The research profile of a paper and of the works a journal published, and how well they match.

Stdlib only, loaded by path by journal_cli.py. A profile is lexical: English and Spanish cue phrases
counted over a text with accents folded, never a model's judgement, so the same text always reads the
same and the rules can be tested offline. Its four dimensions:

    approach  quantitative | qualitative | mixed | unclear
              mixed when a mixed-methods cue appears, or when both kinds of cue appear and the weaker
              count is at least half the stronger
    ai        True when an artificial-intelligence / machine-learning cue appears
    kind      general | theory | use-inspired | concept | review | unclear (the most frequent cue;
              ties go to the earlier kind in KINDS). The paper's kind comes from its recorded
              `contribution_type` when there is one (General, Theory, Use-Inspired, Concept & Feasibility)
    math      mathematical | moderate | descriptive | unclear. For a work (an abstract): two or more
              mathematical cues read mathematical, one moderate; none reads moderate for quantitative
              work and descriptive for qualitative or descriptive work. For the paper, when its body has
              at least MIN_BODY_WORDS words, the density of LaTeX math (display environments and inline
              formulas per 1000 words) decides instead: >= MATH_DENSE mathematical, >= MATH_SOME moderate

`match` compares the paper with the works one journal published like it: per dimension the share of
works that agree (a mixed approach against quantitative or qualitative, and adjacent math levels, count
half), plus `topic`, the share of works that contain at least two of the paper's terms. A dimension the
paper reads unclear, or no work reads clearly, leaves the score, and the other weights are rescaled.
"""
from __future__ import annotations

import re
import unicodedata

APPROACHES = ("quantitative", "qualitative", "mixed")
KINDS = ("general", "theory", "use-inspired", "concept", "review")
MATH_LEVELS = ("descriptive", "moderate", "mathematical")
WEIGHTS = {"topic": 0.30, "approach": 0.20, "kind": 0.20, "math": 0.15, "ai": 0.15}
MATH_DENSE = 8.0     # math expressions per 1000 words of body text
MATH_SOME = 2.0
MIN_BODY_WORDS = 100
TOPIC_MIN_TERMS = 2
TERM_PREFIX = 6
CONTRIBUTION_KINDS = {"General": "general", "Theory": "theory", "Use-Inspired": "use-inspired",
                      "Concept & Feasibility": "concept"}


def _cues(*patterns: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(patterns) + r")", re.IGNORECASE)


CUES = {
    "quantitative": _cues(
        r"quantitativ", r"statistic", r"regression", r"dataset", r"data set", r"accuracy", r"precision", r"recall",
        r"f1[- ]score", r"auc\b", r"rmse", r"cross[- ]validat", r"experiment", r"simulat", r"numerical",
        r"measur", r"metric", r"benchmark", r"estimat", r"correlat", r"anova", r"significant",
        r"\d+ (?:subjects|participants|patients|samples|individuals)",
        r"cuantitativ", r"estadistic", r"regresion", r"conjunto de datos", r"exactitud", r"simulacion",
        r"experiment", r"medicion", r"correlacion", r"significativ", r"\d+ (?:sujetos|participantes|pacientes|muestras)"),
    "qualitative": _cues(
        r"qualitativ", r"interview", r"focus group", r"ethnograph", r"thematic analys", r"grounded theory",
        r"case stud", r"narrative", r"discourse analys", r"phenomenolog", r"hermeneut", r"content analys",
        r"participant observation", r"life stor",
        r"cualitativ", r"entrevista", r"grupos? focal", r"etnograf", r"analisis tematico", r"teoria fundamentada",
        r"estudio de caso", r"narrativ", r"analisis del discurso", r"fenomenolog", r"analisis de contenido",
        r"observacion participante", r"historias? de vida"),
    "mixed": _cues(r"mixed[- ]methods?", r"metodos? mixtos?", r"enfoque mixto", r"investigacion mixta"),
    "ai": _cues(
        r"machine learning", r"deep learning", r"neural network", r"artificial intelligence", r"transformer",
        r"large language model", r"llms?\b", r"reinforcement learning", r"convolutional", r"generative model",
        r"support vector", r"random forest", r"gradient boosting", r"classifier", r"quantum machine learning",
        r"aprendizaje automatico", r"aprendizaje de maquinas?", r"aprendizaje profundo", r"redes? neuronal",
        r"inteligencia artificial", r"modelos? de lenguaje", r"aprendizaje por refuerzo", r"clasificador"),
    "math": _cues(
        r"theorem", r"lemma", r"proof\b", r"we prove", r"closed[- ]form", r"analytical", r"deriv(?:e|ation)",
        r"bounds?\b", r"convergence", r"differential equation", r"stochastic", r"optimi[sz]ation problem",
        r"hilbert", r"eigen", r"variational", r"bayesian", r"mathematical", r"formulation", r"kernel",
        r"teorema", r"lema\b", r"demostra", r"forma cerrada", r"analitic", r"derivacion", r"cotas?\b",
        r"convergencia", r"ecuacion(?:es)? diferencial", r"estocastic", r"problema de optimizacion",
        r"matematic", r"formulacion", r"bayesian"),
    "descriptive": _cues(
        r"describ", r"overview", r"perspective", r"essay", r"reflection", r"commentary", r"historical",
        r"experience report", r"policy",
        r"descri", r"reflexion", r"ensayo", r"perspectiva", r"historic", r"experiencia"),
    "general": _cues(
        r"(?:we |this paper |this work )?propos\w*\s+(?:a|an|the)\s+(?:[\w-]+\s+){0,4}?"
        r"(?:method|algorithm|framework|approach|model|technique|architecture|network|pipeline)",
        r"novel (?:method|algorithm|framework|approach|model|technique|architecture)", r"outperform",
        r"state-of-the-art (?:results|performance)", r"proposed (?:method|model|approach|framework)",
        r"(?:se )?propone(?:mos)? (?:un|una) (?:nuevo |nueva )?(?:metodo|algoritmo|modelo|enfoque|marco|tecnica)",
        r"metodo propuesto", r"modelo propuesto", r"supera a"),
    "theory": _cues(
        r"we prove", r"theorem", r"lemma", r"theoretical (?:analysis|guarantee|result)", r"upper bound",
        r"lower bound", r"demostramos", r"teorema", r"analisis teorico"),
    "use-inspired": _cues(
        r"applied to", r"application of", r"case stud", r"real[- ]world", r"clinical", r"in practice",
        r"practitioner", r"deployment", r"field stud", r"industr", r"decision support",
        r"aplicad[oa] a", r"aplicacion de", r"estudio de caso", r"caso de estudio", r"mundo real", r"clinic",
        r"en la practica", r"implementacion en", r"industri"),
    "concept": _cues(
        r"proof[- ]of[- ]concept", r"feasibility", r"conceptual", r"preliminary", r"exploratory", r"first step",
        r"pilot stud", r"prueba de concepto", r"factibilidad", r"viabilidad", r"exploratori", r"preliminar"),
    "review": _cues(
        r"systematic review", r"literature review", r"scoping review", r"meta-analys", r"state of the art",
        r"overview of", r"survey of", r"surveys the", r"review of",
        r"revision sistematica", r"revision de (?:la )?literatura", r"estado del arte", r"metaanalisis",
        r"revision de alcance"),
}


def fold(text: str) -> str:
    """Lower case without accents: "Análisis" and "analisis" read the same."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def abstract_from_index(index) -> str:
    """OpenAlex's `abstract_inverted_index` as plain text ("" when absent)."""
    if not isinstance(index, dict):
        return ""
    placed = [(position, word) for word, positions in index.items() if isinstance(positions, list)
              for position in positions if isinstance(position, int)]
    return " ".join(word for _, word in sorted(placed))


def signals(text: str) -> dict[str, int]:
    folded = fold(text)
    return {name: len(pattern.findall(folded)) for name, pattern in CUES.items()}


def _approach(found: dict[str, int]) -> str:
    quant, qual = found["quantitative"], found["qualitative"]
    if found["mixed"] or (quant and qual and 2 * min(quant, qual) >= max(quant, qual)):
        return "mixed"
    if quant > qual:
        return "quantitative"
    if qual > quant:
        return "qualitative"
    return "unclear"


def _kind(found: dict[str, int]) -> str:
    best = max(KINDS, key=lambda kind: (found[kind], -KINDS.index(kind)))
    return best if found[best] else "unclear"


def _lexical_math(found: dict[str, int], approach: str) -> str:
    if found["math"] >= 2:
        return "mathematical"
    if found["math"] == 1 or approach == "quantitative":
        return "moderate"
    if approach in ("qualitative", "mixed") or found["descriptive"]:
        return "descriptive"
    return "unclear"


def classify(text: str) -> dict:
    """The lexical profile of one text (a title and abstract)."""
    found = signals(text)
    approach = _approach(found)
    return {"approach": approach, "ai": bool(found["ai"]), "kind": _kind(found),
            "math": _lexical_math(found, approach)}


_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}",
                           re.DOTALL)
_INLINE_MATH = re.compile(r"(?<![\\$])\$[^$]+\$(?!\$)|\\\(.*?\\\)", re.DOTALL)
_ENVIRONMENT_BODY = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)(\*?)\}.*?\\end\{\1\2\}",
                               re.DOTALL)


def _without_math(tex: str) -> str:
    text = _ENVIRONMENT_BODY.sub(" ", tex)
    text = re.sub(r"\$\$.*?\$\$|\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    return _INLINE_MATH.sub(" ", text)


def body_words(tex: str) -> int:
    text = re.sub(r"\\[A-Za-z]+\*?", " ", _without_math(re.sub(r"(?<!\\)%[^\n]*", "", tex or "")))
    return len(re.findall(r"[^\W\d_]{2,}", text))


def math_density(tex: str) -> float:
    """Math expressions (display environments and inline formulas) per 1000 words of text."""
    tex = re.sub(r"(?<!\\)%[^\n]*", "", tex or "")
    expressions = len(_DISPLAY_MATH.findall(tex)) + len(_INLINE_MATH.findall(_ENVIRONMENT_BODY.sub(" ", tex)))
    return 1000.0 * expressions / max(body_words(tex), 1)


def paper_profile(title: str, abstract: str, keywords, body_tex: str, contribution_type=None) -> dict:
    """The paper's profile: title, abstract and keywords for the cues, its LaTeX body for the math level,
    its recorded contribution type for the kind."""
    text = " ".join([title or "", abstract or "", ", ".join(keywords or [])])
    profile = classify(text)
    profile.update(kind_basis="lexical", math_basis="lexical", math_density=None)
    if body_words(body_tex) >= MIN_BODY_WORDS:
        density = math_density(body_tex)
        profile["math"] = ("mathematical" if density >= MATH_DENSE else "moderate" if density >= MATH_SOME
                           else "descriptive")
        profile.update(math_basis="equations", math_density=round(density, 2))
    kind = CONTRIBUTION_KINDS.get((contribution_type or {}).get("type")) if isinstance(contribution_type, dict) \
        else None
    if kind:
        profile.update(kind=kind, kind_basis="contribution_type")
    return profile


def shares(profiles: list[dict]) -> dict:
    """How the works of one journal spread over each dimension (unclear readings left out)."""
    def spread(dimension: str) -> dict[str, float]:
        clear = [p[dimension] for p in profiles if p.get(dimension) not in (None, "unclear")]
        return {label: round(clear.count(label) / len(clear), 4) for label in dict.fromkeys(clear)} if clear else {}

    return {"n": len(profiles), "approach": spread("approach"), "kind": spread("kind"), "math": spread("math"),
            "ai": round(sum(1 for p in profiles if p.get("ai")) / len(profiles), 4) if profiles else None}


def _agreement(dimension: str, paper: str, work: str) -> float:
    if paper == work:
        return 1.0
    if dimension == "approach" and "mixed" in (paper, work):
        return 0.5
    if dimension == "math" and abs(MATH_LEVELS.index(paper) - MATH_LEVELS.index(work)) == 1:
        return 0.5
    return 0.0


def _stems(terms) -> list[str]:
    return list(dict.fromkeys(fold(term)[:TERM_PREFIX] for term in terms or [] if len(term) >= 3))


def match(paper: dict, profiles: list[dict], texts: list[str], terms) -> dict:
    """How well one journal's works like the paper match it, per dimension and overall (0..1, None when
    nothing could be compared)."""
    dimensions: dict[str, float] = {}
    stems = _stems(terms)
    if texts and stems:
        needed = min(TOPIC_MIN_TERMS, len(stems))
        words = [set(re.findall(r"[^\W_]+", fold(text))) for text in texts]
        hits = sum(1 for found in words if sum(any(w.startswith(s) for w in found) for s in stems) >= needed)
        dimensions["topic"] = round(hits / len(texts), 4)
    for dimension in ("approach", "kind", "math"):
        mine = paper.get(dimension)
        clear = [p[dimension] for p in profiles if p.get(dimension) not in (None, "unclear")]
        if mine in (None, "unclear") or not clear:
            continue
        dimensions[dimension] = round(sum(_agreement(dimension, mine, theirs) for theirs in clear) / len(clear), 4)
    if profiles:
        dimensions["ai"] = round(sum(1 for p in profiles if bool(p.get("ai")) == bool(paper.get("ai")))
                                 / len(profiles), 4)
    active = [name for name in WEIGHTS if name in dimensions]
    total = sum(WEIGHTS[name] for name in active)
    score = round(sum(WEIGHTS[name] * dimensions[name] for name in active) / total, 4) if total else None
    return {"dimensions": dimensions, "active": active, "score": score}
