"""Idea clusters of the papers a manuscript cites.

``cluster_papers`` is a computed view, never a claim of the manuscript and never
a graph node: it groups papers by what their text says and by how they are cited
together, for a paper of any field. There is no domain vocabulary and no fixed
number of clusters. Standard library only, pure and deterministic: every step
walks papers in sorted key order, so the answer depends on neither input order
nor hash seed.

1. Terms: TF-IDF over title, keywords and abstract, with the title heaviest.
   Accents and plurals never split a term; a label keeps the spelling it read.
2. Similarity: cosine, plus bounded bonuses for co-citation, a shared idea and
   the same family. A family alone stays under the floor, so it never links.
3. Graph: each paper keeps its nearest neighbours above the floor.
4. Communities: Louvain modularity, aggregating until nothing merges. How many
   there are comes out of the data.
5. Labels: the terms that are frequent in a cluster and rare outside it.

A paper with no text, or with no neighbour, is ``unclustered``.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from itertools import combinations
from typing import Any

METHOD = "TF-IDF cosine with citation bonuses, kNN graph, Louvain modularity"

MIN_PAPERS = 3
MIN_TOKEN = 3
TITLE_WEIGHT = 3.0
KEYWORD_WEIGHT = 2.0
ABSTRACT_WEIGHT = 1.0
MAX_TERMS = 48  # per paper: keeps the strongest terms, and the pair loop fast
UBIQUITY = 0.05  # IDF floor, so a term in every paper still gives a vector

SIMILARITY_FLOOR = 0.08
COCITE_STEP, COCITE_CAP = 0.10, 0.25
IDEA_STEP, IDEA_CAP = 0.10, 0.20
FAMILY_BONUS = 0.05
MIN_NEIGHBOURS, MAX_NEIGHBOURS = 3, 10

MAX_SWEEPS = 50
MIN_GAIN = 1e-12
LABEL_TERMS = 3
REPORTED_TERMS = 6
LABEL_SEPARATOR = " · "
LABEL_SMOOTHING = 0.01
FAMILY_MAJORITY = 0.5

# Written without accents because a token is folded before this check. Function
# words and the boilerplate of any paper, never the vocabulary of a field.
STOP_WORDS = frozenset("""
    a about above across after again against all almost also although always am among an and another any
    are around as at be because been before being below between both but by can cannot could did do does
    doing done down during each either else even ever every few for from further had has have having he
    her here hers him his how however i if in into is it its itself just least less like made make many
    may me might more most much must my neither no nor not now of off often on once one only onto or other
    others our ours out over own per quite rather same she should since so some still such than that the
    their theirs them themselves then there therefore these they this those through thus to too toward
    towards two under until up upon us very via was we were what when where whether which while who whom
    whose why will with within without would yet you your yours
    al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque cada cal como con contra cual
    cuales cuando cuanto de del desde donde dos durante e el ella ellas ello ellos en entre era eran es esa
    esas ese eso esos esta estaba estan estar estas este esto estos fue fueron ha habia han hasta hay la las
    le les lo los mas me mediante mi mientras mis mucho muchos muy ni no nos nosotros nuestra nuestro o otra
    otras otro otros para pero poco por porque puede pueden que quien quienes se segun ser si sido siempre
    sin sino sobre son su sus tal tambien tan tanto te tiene tienen toda todas todo todos tras tu tus u un
    una unas uno unos usando ya y
    analysis approach article based case effect evaluation finding method novel paper present proposed
    propose research result review show showing study survey toward use used using work
    analisis articulo basado caso efecto enfoque estudio evaluacion metodo nuevo nueva presente propuesta
    resultado revision trabajo
""".split())
STOP_COMPOUNDS = frozenset({"state-of-the-art", "state-of-art"})

_TOKEN = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
_HYPHENS = str.maketrans({"‐": "-", "‑": "-"})


def cluster_papers(papers: list[dict], cocited: list[list[str]] | None = None) -> dict[str, Any]:
    """Group ``papers``; ``cocited`` holds the key groups of each ``\\cite{a,b}``. Never raises."""
    chosen = _papers(papers)
    bags = {key: _bag(paper) for key, paper in chosen.items()}
    keys = sorted(key for key, (weights, _) in bags.items() if weights)
    if len(keys) < MIN_PAPERS:
        return _answer([], sorted(chosen), [])

    index = {key: position for position, key in enumerate(keys)}
    weights = [bags[key][0] for key in keys]
    cocited_pairs = _cocited_pairs(cocited, index)
    idea_pairs = _idea_pairs([chosen[key] for key in keys])
    families = [_text(chosen[key].get("family")).strip() for key in keys]
    similarity = _cosines(_vectors(weights))
    for pair in (*cocited_pairs, *idea_pairs):
        similarity.setdefault(pair, 0.0)

    family_used = False
    for pair in sorted(similarity):
        first, second = pair
        same_family = bool(families[first]) and families[first] == families[second]
        family_used = family_used or same_family
        similarity[pair] += (min(COCITE_CAP, COCITE_STEP * cocited_pairs.get(pair, 0))
                             + min(IDEA_CAP, IDEA_STEP * idea_pairs.get(pair, 0))
                             + (FAMILY_BONUS if same_family else 0.0))

    members: dict[int, list[int]] = {}
    for position, community in enumerate(_louvain(len(keys), _neighbour_edges(len(keys), similarity))):
        members.setdefault(community, []).append(position)

    surfaces = [bags[key][1] for key in keys]
    clusters = [_cluster(group, keys, weights, surfaces, families, cocited_pairs, idea_pairs)
                for group in members.values() if len(group) > 1]
    clusters.sort(key=lambda cluster: (-cluster["size"], cluster["label"], cluster["id"]))
    placed = {key for cluster in clusters for key in cluster["keys"]}
    signals = ["text"]
    signals += ["cocitation"] if cocited_pairs else []
    signals += ["family"] if family_used else []
    signals += ["shared_idea"] if idea_pairs else []
    return _answer(clusters, sorted(set(chosen) - placed), signals)


def _answer(clusters: list[dict], unclustered: list[str], signals: list[str]) -> dict[str, Any]:
    return {"method": METHOD, "signals": signals, "clusters": clusters, "unclustered": unclustered}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _keywords(value: Any) -> str:
    """Keywords as text. A DataCite "FOS:" subject tag names a repository shelf, not a topic."""
    if not isinstance(value, (list, tuple)):
        return _text(value)
    return " ".join(_text(item) for item in value if not _text(item).casefold().startswith("fos:"))


def _papers(papers: Any) -> dict[str, dict]:
    """Well-formed papers by key. A repeated key keeps one winner, whatever the input order."""
    chosen: dict[str, dict] = {}

    def rank(paper: dict) -> tuple[str, str, str]:
        return _text(paper.get("title")), _text(paper.get("abstract")), _keywords(paper.get("keywords"))

    for paper in papers if isinstance(papers, (list, tuple)) else ():
        key = paper.get("key") if isinstance(paper, dict) else None
        if isinstance(key, str) and key and (key not in chosen or rank(paper) > rank(chosen[key])):
            chosen[key] = paper
    return chosen


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _stem(word: str) -> str:
    """Singular of a word, for matching only: a label shows what was written."""
    if len(word) > 4 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _is_word(word: str) -> bool:
    return (len(word) >= MIN_TOKEN and not word.isdigit()
            and word not in STOP_WORDS and _stem(word) not in STOP_WORDS)


def _terms(text: str) -> list[tuple[str, str]]:
    """``(term, surface)`` pairs. A hyphenated term stands beside its parts, so it still meets them."""
    found: list[tuple[str, str]] = []
    prepared = unicodedata.normalize("NFC", text.translate(_HYPHENS)).lower()
    for match in _TOKEN.finditer(prepared):
        surface = match.group()
        folded = _fold(surface)
        if folded in STOP_COMPOUNDS:
            continue
        parts = folded.split("-")
        found.extend((_stem(part), part) for part in parts if _is_word(part))
        if len(parts) > 1 and not any(part in STOP_WORDS or len(part) < 2 for part in parts):
            found.append((_stem(folded), surface))
        elif len(parts) == 1 and _is_word(folded):
            found[-1] = (_stem(folded), surface)
    return found


def _bag(paper: dict) -> tuple[dict[str, float], dict[str, Counter]]:
    """Weighted term counts of a paper, and how each term was spelled."""
    weights: Counter = Counter()
    surfaces: dict[str, Counter] = {}
    for text, weight in ((_text(paper.get("title")), TITLE_WEIGHT),
                         (_keywords(paper.get("keywords")), KEYWORD_WEIGHT),
                         (_text(paper.get("abstract")), ABSTRACT_WEIGHT)):
        for term, surface in _terms(text):
            weights[term] += weight
            surfaces.setdefault(term, Counter())[surface] += 1
    return dict(weights), surfaces


def _vectors(bags: list[dict[str, float]]) -> list[dict[str, float]]:
    """Unit TF-IDF vectors holding each paper's strongest terms."""
    total = len(bags)
    frequency = Counter(term for bag in bags for term in bag)
    vectors = []
    for bag in bags:
        scored = {term: (1.0 + math.log(count)) * (math.log((1 + total) / (1 + frequency[term])) + UBIQUITY)
                  for term, count in bag.items()}
        strongest = sorted(scored, key=lambda term: (-scored[term], term))[:MAX_TERMS]
        norm = math.sqrt(sum(scored[term] ** 2 for term in strongest))
        vectors.append({term: scored[term] / norm for term in sorted(strongest)})
    return vectors


def _cosines(vectors: list[dict[str, float]]) -> dict[tuple[int, int], float]:
    """Cosine of every pair that shares a term, through an inverted index."""
    postings: dict[str, list[tuple[int, float]]] = {}
    for position, vector in enumerate(vectors):
        for term, weight in vector.items():
            postings.setdefault(term, []).append((position, weight))
    cosines: dict[tuple[int, int], float] = {}
    for term in sorted(postings):
        for (first, left), (second, right) in combinations(postings[term], 2):
            pair = (first, second)
            cosines[pair] = cosines.get(pair, 0.0) + left * right
    return cosines


def _cocited_pairs(cocited: Any, index: dict[str, int]) -> Counter:
    pairs: Counter = Counter()
    for group in cocited if isinstance(cocited, (list, tuple)) else ():
        if isinstance(group, (list, tuple)):
            known = sorted({index[key] for key in group if isinstance(key, str) and key in index})
            pairs.update(combinations(known, 2))
    return pairs


def _idea_pairs(papers: list[dict]) -> Counter:
    holders: dict[str, list[int]] = {}
    for position, paper in enumerate(papers):
        ideas = paper.get("ideas")
        held = {_text(item.get("idea")).strip() for item in ideas if isinstance(item, dict)} \
            if isinstance(ideas, (list, tuple)) else set()
        for idea in sorted(held - {""}):
            holders.setdefault(idea, []).append(position)
    pairs: Counter = Counter()
    for idea in sorted(holders):
        pairs.update(combinations(holders[idea], 2))
    return pairs


def _neighbour_edges(size: int, similarity: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """The union of every paper's nearest neighbours above the floor."""
    near: list[list[tuple[float, int]]] = [[] for _ in range(size)]
    for (first, second), value in sorted(similarity.items()):
        if value >= SIMILARITY_FLOOR:
            near[first].append((-value, second))
            near[second].append((-value, first))
    keep = max(MIN_NEIGHBOURS, min(MAX_NEIGHBOURS, round(math.sqrt(size))))
    edges: dict[tuple[int, int], float] = {}
    for position, candidates in enumerate(near):
        for negative, other in sorted(candidates)[:keep]:
            edges[(min(position, other), max(position, other))] = -negative
    return edges


def _local_moves(size: int, edges: dict[tuple[int, int], float]) -> list[int]:
    """One Louvain level: move each node to the community that gains the most modularity."""
    links: list[list[tuple[int, float]]] = [[] for _ in range(size)]
    degree = [0.0] * size
    for (first, second), weight in sorted(edges.items()):
        degree[first] += weight
        degree[second] += weight
        if first != second:
            links[first].append((second, weight))
            links[second].append((first, weight))
    doubled = sum(degree)
    community = list(range(size))
    if not doubled:
        return community
    totals = degree[:]
    for _ in range(MAX_SWEEPS):
        moved = False
        for node in range(size):
            current = community[node]
            toward: dict[int, float] = {current: 0.0}
            for other, weight in links[node]:
                toward[community[other]] = toward.get(community[other], 0.0) + weight
            totals[current] -= degree[node]
            best = current
            best_gain = toward[current] - totals[current] * degree[node] / doubled
            for candidate in sorted(toward):
                gain = toward[candidate] - totals[candidate] * degree[node] / doubled
                if gain > best_gain + MIN_GAIN:
                    best, best_gain = candidate, gain
            totals[best] += degree[node]
            if best != current:
                community[node] = best
                moved = True
        if not moved:
            break
    return community


def _louvain(size: int, edges: dict[tuple[int, int], float]) -> list[int]:
    """The community of each node, aggregating levels until nothing merges."""
    membership = list(range(size))
    while True:
        moves = _local_moves(size, edges)
        renumbered: dict[int, int] = {}
        for community in moves:
            renumbered.setdefault(community, len(renumbered))
        membership = [renumbered[moves[node]] for node in membership]
        if len(renumbered) == size:
            return membership
        merged: dict[tuple[int, int], float] = {}
        for (first, second), weight in sorted(edges.items()):
            left, right = sorted((renumbered[moves[first]], renumbered[moves[second]]))
            merged[(left, right)] = merged.get((left, right), 0.0) + weight
        size, edges = len(renumbered), merged


def _distinctive(group: list[int], bags: list[dict[str, float]]) -> list[str]:
    """Terms of a cluster, most distinctive first: frequent inside, rare outside."""
    inside: Counter = Counter(term for position in group for term in bags[position])
    weight: Counter = Counter()
    for position in group:
        weight.update(bags[position])
    overall = Counter(term for bag in bags for term in bag)
    rest = max(1, len(bags) - len(group))

    def score(term: str) -> float:
        share = inside[term] / len(group)
        outside = (overall[term] - inside[term]) / rest
        return share * math.log((share + LABEL_SMOOTHING) / (outside + LABEL_SMOOTHING))

    ranked = sorted(inside, key=lambda term: (-score(term), -weight[term], term))
    covered = {_stem(part) for term in ranked if "-" in term for part in term.split("-")
               if inside[term] >= inside[_stem(part)]}
    return [term for term in ranked if term not in covered]


def _spelling(term: str, group: list[int], surfaces: list[dict[str, Counter]]) -> str:
    spellings: Counter = Counter()
    for position in group:
        spellings.update(surfaces[position].get(term, {}))
    return min(spellings, key=lambda surface: (-spellings[surface], surface))


def _cluster(group: list[int], keys: list[str], bags: list[dict[str, float]], surfaces: list[dict[str, Counter]],
             families: list[str], cocited_pairs: Counter, idea_pairs: Counter) -> dict[str, Any]:
    terms = [_spelling(term, group, surfaces) for term in _distinctive(group, bags)[:REPORTED_TERMS]]
    members = sorted(keys[position] for position in group)
    held = set(group)
    named = Counter(families[position] for position in group if families[position])
    family, count = min(named.items(), key=lambda item: (-item[1], item[0])) if named else (None, 0)
    share = count / len(group)
    return {
        "id": "c" + hashlib.sha1("\n".join(members).encode("utf-8")).hexdigest()[:12],
        "label": LABEL_SEPARATOR.join(terms[:LABEL_TERMS]),
        "terms": terms,
        "keys": members,
        "size": len(members),
        "signals": {
            "family": family if share > FAMILY_MAJORITY else None,
            "family_share": round(share, 3) if share > FAMILY_MAJORITY else 0.0,
            "cocited_pairs": sum(1 for pair in cocited_pairs if held.issuperset(pair)),
            "shared_idea_pairs": sum(1 for pair in idea_pairs if held.issuperset(pair)),
        },
    }
