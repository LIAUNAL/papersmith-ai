"""Fail-closed validator for a plausibility constellation atlas.

Reads one ``sota-pool/atlas.json`` and refuses every malformed atlas.

With ``--pool sota-pool/candidates.json`` it also holds every quote to the
abstract it claims: each planet's ``evidence.origin`` must name a pool
candidate (its ``identifier``, ``source_url`` or ``url``), and its ``quote``
must be a verbatim substring of that candidate's ``abstract``. Whitespace
runs compare collapsed -- the resolver itself collapses arXiv's multi-line
summaries, and a line break is layout, not authorship -- and nothing else is
normalized: case, punctuation and words must match. A candidate without an
abstract can be quoted by nothing. Without ``--pool`` a green run certifies
shape alone; with it, a green run certifies that every quote is in the
stored abstract, which is still not that the abstract supports the planet.

Usage: check_atlas.py <atlas.json> [--pool <candidates.json>]

Exit codes: 0 well-formed, 1 at least one violation (all named), 2 usage
or unreadable input (nothing was judged).

Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAX_PLANETS = 20

# slot -> (orbit, min_count, max_count)
SLOTS = {
    "sun": (0, 1, 1),
    "branch": (1, 0, 2),
    "topic_app": (1, 1, 1),
    "topic_ai": (1, 1, 1),
    "problem": (1, 1, 1),
    "application": (1, 1, 1),
    "family": (2, 1, 1),
    "novelty": (1, 1, 1),
    "contribution": (1, 0, 5),
    "result": (3, 1, 3),
    "conclusion": (3, 1, 2),
}

RELS = {"about", "addresses", "extends", "contradicts", "supports",
        "yields", "shares-family-with"}

PROVENANCE = {"stated", "grouped"}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The candidate fields a planet's `evidence.origin` may name.
ORIGIN_KEYS = ("identifier", "source_url", "url")


class PoolError(Exception):
    """The pool could not be read as a list of candidates; nothing was judged."""


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def pool_abstracts(pool: object) -> dict[str, object]:
    """Map every origin a candidate answers to (its identifier and URLs) to
    its abstract. A top-level list or ``{"candidates": [...]}``. Raises
    `PoolError` on any other shape."""
    candidates = pool.get("candidates") if isinstance(pool, dict) else pool
    if not isinstance(candidates, list):
        raise PoolError("POOL_MALFORMED: expected a list of candidates or "
                        "{\"candidates\": [...]}")
    abstracts: dict[str, object] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise PoolError("POOL_MALFORMED: a candidate is not an object")
        for key in ORIGIN_KEYS:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                abstracts[value.strip()] = candidate.get("abstract")
    return abstracts


def _fidelity_failures(atlas: dict, abstracts: dict[str, object]) -> list[str]:
    """Every planet whose quote is not verbatim in the abstract it names."""
    found: list[str] = []
    for system in atlas.get("systems") or []:
        if not isinstance(system, dict):
            continue
        sid = system.get("id")
        for planet in system.get("planets") or []:
            if not isinstance(planet, dict) or not isinstance(planet.get("evidence"), dict):
                continue
            evidence = planet["evidence"]
            origin, quote = evidence.get("origin"), evidence.get("quote")
            if not isinstance(origin, str) or not isinstance(quote, str) or not quote.strip():
                continue  # already named by the shape check
            where = f"{sid}.{planet.get('id')}"
            if origin.strip() not in abstracts:
                found.append(f"{where}: EVIDENCE_ORIGIN_NOT_IN_POOL: {origin!r}")
                continue
            abstract = abstracts[origin.strip()]
            if not isinstance(abstract, str) or not abstract.strip():
                found.append(f"{where}: EVIDENCE_ABSTRACT_MISSING: {origin!r} has no "
                             "stored abstract to quote")
            elif _collapsed(quote) not in _collapsed(abstract):
                found.append(f"{where}: EVIDENCE_QUOTE_NOT_IN_ABSTRACT: {quote!r} is not "
                             f"verbatim in the abstract of {origin!r}")
    return found


def _failures(atlas: object, abstracts: dict[str, object] | None = None) -> list[str]:
    """Every violation, so one red run names all of them rather than the
    first — an atlas fixed one refusal at a time is a loop nobody budgeted.
    ``abstracts`` (from `pool_abstracts`) adds the quote-fidelity check."""
    found = _shape_failures(atlas)
    if abstracts is not None and isinstance(atlas, dict):
        found.extend(_fidelity_failures(atlas, abstracts))
    return found


def _shape_failures(atlas: object) -> list[str]:
    found: list[str] = []
    if not isinstance(atlas, dict):
        return ["ATLAS_NOT_AN_OBJECT"]
    systems = atlas.get("systems")
    links = atlas.get("links")
    if not isinstance(systems, list) or not systems:
        return ["SYSTEMS_NOT_A_NONEMPTY_LIST"]
    if not isinstance(links, list):
        found.append("LINKS_NOT_A_LIST")
        links = []

    known: dict[str, set[str]] = {}
    slots_of: dict[tuple[str, str], str] = {}
    for position, system in enumerate(systems):
        where = f"systems[{position}]"
        if not isinstance(system, dict):
            found.append(f"{where}: SYSTEM_NOT_AN_OBJECT")
            continue
        sid = system.get("id")
        if not isinstance(sid, str) or not sid:
            found.append(f"{where}: SYSTEM_ID_MISSING")
            continue
        if sid in known:
            found.append(f"DUPLICATE_SYSTEM_ID: {sid!r}")
            continue
        planets = system.get("planets")
        if not isinstance(planets, list):
            found.append(f"{sid}: PLANETS_NOT_A_LIST")
            known[sid] = set()
            continue
        if len(planets) > MAX_PLANETS:
            found.append(f"{sid}: PLANET_BUDGET_EXCEEDED: {len(planets)} planets, limit is {MAX_PLANETS}")
        seen: set[str] = set()
        counts: dict[str, int] = {}
        for index, planet in enumerate(planets):
            plabel = f"{sid}.planets[{index}]"
            if not isinstance(planet, dict):
                found.append(f"{plabel}: PLANET_NOT_AN_OBJECT")
                continue
            pid = planet.get("id")
            if not isinstance(pid, str) or not pid:
                found.append(f"{plabel}: PLANET_ID_MISSING")
                continue
            if pid in seen:
                found.append(f"{sid}: DUPLICATE_PLANET_ID: {pid!r}")
            seen.add(pid)
            slot = planet.get("slot")
            if slot not in SLOTS:
                found.append(f"{sid}.{pid}: SLOT_OUTSIDE_TABLE: {slot!r}")
            else:
                orbit, _, _ = SLOTS[slot]
                if planet.get("orbit") != orbit:
                    found.append(f"{sid}.{pid}: ORBIT_MISMATCH: slot {slot!r} rides orbit {orbit}")
                counts[slot] = counts.get(slot, 0) + 1
                slots_of[(sid, pid)] = slot
            if planet.get("provenance") not in PROVENANCE:
                found.append(f"{sid}.{pid}: PROVENANCE_UNLABELED")
            for key in ("label", "detail"):
                if not isinstance(planet.get(key), str) or not planet.get(key).strip():
                    found.append(f"{sid}.{pid}: {key.upper()}_EMPTY")
            evidence = planet.get("evidence")
            if not isinstance(evidence, dict):
                found.append(f"{sid}.{pid}: EVIDENCE_MISSING")
                continue
            origin = evidence.get("origin")
            quote = evidence.get("quote")
            retrieved = evidence.get("retrieved")
            if not isinstance(origin, str) or not origin.strip():
                found.append(f"{sid}.{pid}: EVIDENCE_ORIGIN_EMPTY")
            if not isinstance(quote, str) or not quote.strip():
                found.append(f"{sid}.{pid}: EVIDENCE_QUOTE_EMPTY")
            if not isinstance(retrieved, str) or not DATE.match(retrieved):
                found.append(f"{sid}.{pid}: EVIDENCE_RETRIEVED_UNDATED")
        for slot, (_, minimum, maximum) in SLOTS.items():
            have = counts.get(slot, 0)
            if not minimum <= have <= maximum:
                found.append(f"{sid}: SLOT_COUNT_OUTSIDE_ROW: {slot!r} has {have}, row allows {minimum}..{maximum}")
        known[sid] = seen

    pool_families = set()
    for system in systems:
        if not isinstance(system, dict):
            continue
        for planet in system.get("planets") or []:
            if isinstance(planet, dict) and planet.get("slot") == "family":
                label = planet.get("label")
                if isinstance(label, str) and label.strip():
                    pool_families.add(label.strip())
    if not 3 <= len(pool_families) <= 7:
        found.append(f"POOL_FAMILIES_OUTSIDE_3_7: {len(pool_families)} distinct families")

    for position, link in enumerate(links):
        where = f"links[{position}]"
        if not isinstance(link, dict):
            found.append(f"{where}: LINK_NOT_AN_OBJECT")
            continue
        endpoints = []
        for key in ("from_system", "from", "to_system", "to"):
            value = link.get(key)
            if not isinstance(value, str) or not value:
                found.append(f"{where}: LINK_ENDPOINT_MISSING: {key}")
                value = None
            endpoints.append(value)
        from_system, from_pid, to_system, to_pid = endpoints
        if from_system is not None and from_system not in known:
            found.append(f"{where}: LINK_SYSTEM_WITHOUT_SYSTEM: {from_system!r}")
        if to_system is not None and to_system not in known:
            found.append(f"{where}: LINK_SYSTEM_WITHOUT_SYSTEM: {to_system!r}")
        if from_system in known and from_pid is not None and from_pid not in known[from_system]:
            found.append(f"{where}: LINK_ENDPOINT_WITHOUT_PLANET: {from_system}.{from_pid}")
        if to_system in known and to_pid is not None and to_pid not in known[to_system]:
            found.append(f"{where}: LINK_ENDPOINT_WITHOUT_PLANET: {to_system}.{to_pid}")
        if (from_system, from_pid) == (to_system, to_pid) and from_system in known:
            found.append(f"{where}: SELF_LOOP")
        rel = link.get("rel")
        if rel not in RELS:
            found.append(f"{where}: REL_OUTSIDE_CLOSED_SET: {rel!r}")
        elif rel == "shares-family-with":
            ends = [(from_system, from_pid), (to_system, to_pid)]
            if all(e in slots_of for e in ends) and any(slots_of[e] != "family" for e in ends):
                found.append(f"{where}: SHARED_FAMILY_LINK_ON_NON_FAMILY")

    return found


def main(argv: list[str]) -> int:
    args = argv[1:]
    pool_path = None
    if "--pool" in args:
        at = args.index("--pool")
        if at + 1 < len(args):
            pool_path = Path(args[at + 1])
            args = args[:at] + args[at + 2:]
    if len(args) != 1 or args[0].startswith("--"):
        print("usage: check_atlas.py sota-pool/atlas.json [--pool sota-pool/candidates.json]",
              file=sys.stderr)
        return 2
    target = Path(args[0])
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        print(f"ATLAS_UNREADABLE: {error}", file=sys.stderr)
        return 2
    try:
        atlas = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"ATLAS_NOT_JSON: {error}", file=sys.stderr)
        return 2
    abstracts = None
    if pool_path is not None:
        try:
            abstracts = pool_abstracts(json.loads(pool_path.read_text(encoding="utf-8")))
        except OSError as error:
            print(f"POOL_UNREADABLE: {error}", file=sys.stderr)
            return 2
        except json.JSONDecodeError as error:
            print(f"POOL_NOT_JSON: {error}", file=sys.stderr)
            return 2
        except PoolError as error:
            print(str(error), file=sys.stderr)
            return 2
    violations = _failures(atlas, abstracts)
    if violations:
        for violation in violations:
            print(violation)
        return 1
    systems = len(atlas["systems"])
    planets = sum(len(system["planets"]) for system in atlas["systems"])
    print(f"ATLAS_WELL_FORMED: {systems} systems, {planets} planets, {len(atlas['links'])} links"
          + ("; every quote verbatim in its pool abstract" if abstracts is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
