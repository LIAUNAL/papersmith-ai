"""Step 5, topics: three candidate topics with their evidence; the user picks or combines.

:func:`propose` is deterministic for the same brief and the same answers of
the sources. Candidates come, in this order, from the user's keywords (and
domain), the bridge between those keywords and the topic the author's works
cover most (profile), the chosen bank's related items (only when that bank is
compatible and was reachable; never when the choice is ``none``), the user's
methods, the profile's other topics and further keyword pairs. Each topic then
gets its OpenAlex volume of the last :data:`RECENT_YEARS` years
(``/works?search=&filter=from_publication_date:``) with a gap signal, when
OpenAlex answers. Every evidence item names its source: ``operator``,
``profile``, ``bank:<server>``, ``openalex`` or ``guide``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import bank as _bank
from . import brief as _brief
from . import profile as _profile

RECENT_YEARS = 4
#: Fewer recent works than this reads as a possible gap; more than CROWDED as a crowded area.
FEW_WORKS = 50
CROWDED_WORKS = 5000
DEFAULT_N = 3


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _evidence(source: str, detail: str, count: int | None = None, url: str | None = None) -> dict[str, Any]:
    return {"source": source, "detail": detail, "count": count, "url": url}


def _candidates(b: dict[str, Any], bank_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    interests, experience, prof = b["interests"], b["experience"], b["profile"]
    kws: list[str] = list(interests.get("keywords") or [])
    domain = interests.get("domain")
    methods: list[str] = list(experience.get("methods") or [])
    ptopics = [t for t in (prof.get("topics") or []) if isinstance(t, dict) and t.get("name")] \
        if prof.get("source") == "openalex" else []
    found: list[dict[str, Any]] = []

    def add(title: str, rationale: str, keywords: list[str], evidence: list[dict[str, Any]]) -> None:
        found.append({"title": title, "rationale": rationale, "keywords": _brief.words(keywords),
                      "evidence": evidence})

    if kws:
        evidence = [_evidence("operator", f"your keywords: {', '.join(kws)}" +
                              (f"; domain: {domain}" if domain else ""))]
        if interests.get("admired_paper"):
            evidence.append(_evidence("operator", f"a paper you admire: {interests['admired_paper']}"))
        if bank_result is not None and bank_result.get("available") and not bank_result.get("hits"):
            evidence.append(_evidence(f"bank:{bank_result.get('server')}",
                                      "the bank holds no related item for these keywords", 0))
        add(_join(kws[:2]) + (f" in {domain}" if domain else ""),
            "Built from the keywords" + (" and the application domain" if domain else "") + " you gave.",
            kws[:3], evidence)
    if kws and ptopics:
        top = ptopics[0]
        # the first keyword the topic's name does not already say
        lead = next((k for k in kws if k.casefold() not in top["name"].casefold()), kws[0])
        add(f"{lead} applied to {top['name']}",
            "Bridges your interests with the topic your published work covers most.",
            [lead, top["name"]],
            [_evidence("profile", f"{top['count']} of your works are on {top['name']} (OpenAlex)", top["count"]),
             _evidence("operator", f"your keyword: {lead}")])
    if bank_result is not None and bank_result.get("hits"):
        server = bank_result.get("server")
        hits = bank_result["hits"]
        topic = (bank_result.get("topics") or [{}])[0]
        anchor = topic.get("name") or hits[0]["title"]
        lead = kws[0] if kws else (ptopics[0]["name"] if ptopics else "")
        add(f"{lead} building on {anchor}" if lead else f"Building on {anchor}",
            "Grounded in the bank's related items (the lab's background, not state of the art).",
            [lead, anchor] if lead else [anchor],
            [_evidence(f"bank:{server}", f"{len(hits)} related items; the closest: \"{hits[0]['title']}\"",
                       len(hits))])
    if methods and kws:
        add(f"{methods[0]} for {kws[-1]}", "Puts a method you already master to work on your interest.",
            [methods[0], kws[-1]],
            [_evidence("operator", f"a method you use: {methods[0]}; your keyword: {kws[-1]}")])
    for top in ptopics[1:3] if kws else ptopics[:3]:
        add(f"New directions in {top['name']}", "Extends a topic your published work already covers.",
            [top["name"]],
            [_evidence("profile", f"{top['count']} of your works are on {top['name']} (OpenAlex)", top["count"])])
    for i in range(len(kws)):
        for j in range(i + 1, len(kws)):
            if (i, j) != (0, 1):
                add(_join([kws[i], kws[j]]) + (f" in {domain}" if domain else ""),
                    "Another pairing of the keywords you gave.", [kws[i], kws[j]],
                    [_evidence("operator", f"your keywords: {kws[i]}, {kws[j]}")])
    return found


def _gap(count: int, since: int) -> str:
    if count < FEW_WORKS:
        return f"{count} works since {since} in OpenAlex: few recent works, a possible gap"
    if count > CROWDED_WORKS:
        return f"{count} works since {since} in OpenAlex: a crowded area, narrow the angle"
    return f"{count} works since {since} in OpenAlex: an active area"


def _volume(topic: dict[str, Any], since: int, fetch: Callable[[str], Any] | None) -> dict[str, Any]:
    params = {"search": " ".join(topic["keywords"]), "filter": f"from_publication_date:{since}-01-01",
              "per-page": 1}
    payload = _profile.openalex_get("/works", params, fetch=fetch)
    count = payload["meta"]["count"]
    if not isinstance(count, int):
        raise ValueError("OpenAlex answered without a count")
    return _evidence("openalex", _gap(count, since), count, _profile.openalex_url("/works", params))


def propose(root: Path | str, n: int = DEFAULT_N, *, fetch: Callable[[str], Any] | None = None,
            today: date | None = None) -> list[dict[str, Any]]:
    """Propose ``n`` topics (fewer when the answers give too little), record
    them in the brief (clearing the previous pick) and return them."""
    b = _brief.load(root)
    n = max(1, min(int(n), 6))
    bank = b["bank"]
    bank_result = None
    if bank.get("choice") in ("banco-lia", "other") and bank.get("compatible") and bank.get("available"):
        kws = b["interests"].get("keywords") or []
        ptopics = b["profile"].get("topics") or []
        query = " ".join(kws[:5]) or (ptopics[0].get("name") if ptopics else "")
        if query:
            bank_result = _bank.search(root, query)
    seen: set[str] = set()
    chosen: list[dict[str, Any]] = []
    for candidate in _candidates(b, bank_result):
        key = candidate["title"].casefold()
        if key not in seen:
            seen.add(key)
            chosen.append(candidate)
        if len(chosen) == n:
            break
    since = (today or date.today()).year - RECENT_YEARS
    reachable = True
    topics: list[dict[str, Any]] = []
    for index, candidate in enumerate(chosen, start=1):
        topic = {"id": f"t{index}", **candidate}
        if reachable:
            try:
                topic["evidence"] = [*topic["evidence"], _volume(topic, since, fetch)]
            except Exception:  # noqa: BLE001 - offline: the topic keeps its other evidence
                reachable = False
        topics.append(topic)
    _brief.record(root, "topics", topics)
    if b["chosen"].get("topic_ids"):
        _brief.record(root, "chosen", {"topic_ids": [], "note": None})
    return topics


def choose(root: Path | str, topic_ids: Any, note: str | None = None) -> dict[str, Any]:
    """Record the topics the user picked (one, or several to combine) by id
    (``t1``) or number (``1``); returns the brief's ``chosen``."""
    b = _brief.load(root)
    known = [t.get("id") for t in b["topics"] if isinstance(t, dict)]
    picked: list[str] = []
    for entry in _brief.words(topic_ids):
        ident = f"t{entry}" if entry.isdigit() else entry.lower()
        if ident not in known:
            raise _brief.IdeaError("TOPIC_UNKNOWN", f"no topic {entry!r}; proposed: {', '.join(known) or 'none'}")
        if ident not in picked:
            picked.append(ident)
    if not picked:
        raise _brief.IdeaError("TOPIC_MISSING", "pick at least one topic (e.g. t1, or t1,t3 to combine)")
    return _brief.record(root, "chosen", {"topic_ids": picked, "note": note})["chosen"]


__all__ = ["CROWDED_WORKS", "FEW_WORKS", "RECENT_YEARS", "choose", "propose"]
