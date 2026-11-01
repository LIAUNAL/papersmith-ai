"""Merge a proposal into the SOTA constellation: one atlas, two domains.

Reads the constellation ``check_atlas.py`` already passed
(``sota-pool/atlas.json``) and the proposal's own overlay
(``proposals/<revision>.sky.json``, written during the deliberation), and writes
one atlas: every SOTA system and link untouched and in its original order, plus
the proposal as one more system and its links into the constellation.

The merge is data, not a second picture. The proposal enters the sky its
references already live in, so "this idea extends that result" is a drawn edge
between two real nodes instead of a sentence in a document that can drift from
the graph it claims to describe. Reusing the constellation's own viewer is what
makes the relationship visible at all.

The merged file is what ``render_atlas.py --title ...`` draws, and it still has
to pass ``check_atlas.py``. This tool therefore refuses only what makes the
merge *incoherent* -- a system id already taken, a link with no planet to land
on -- and never restates the constellation's own bound, which already has one
authority.

Overlay shape::

    {"system": {"id": "proposal", "title": ..., "planets": [...]},
     "links": [{"from": <proposal planet id>, "to_system": ..., "to": ...,
                "rel": ...}]}

``from_system`` is deliberately absent from the overlay: every overlay link
starts at the proposal, so a field that can only ever hold one value is a way to
be wrong rather than a way to be expressive. The written link carries it.

Optional, for every revision written from this contract on (an older overlay
without them still merges)::

    "pillars": [{"id": "P1", "label": ..., "detail": ...,
                 "contribution": <a contribution planet id of this overlay>}],
    "hypotheses": [{"id": "H1", "statement": ..., "pillar": "P1",
                    "experiments": ["e1", ...]}]

The pillars are what the problem decomposes into; each hypothesis is the
testable prediction one pillar makes, and ``experiments`` names the protocol's
``[exp:<id>]`` entries that test it once the protocol exists. They stay in the
overlay -- the merged atlas never carries them, so ``check_atlas.py`` is
untouched -- and the manuscript summary graph reads them from there.
``pillars_and_hypotheses`` holds them to that shape; the merge refuses an
overlay that fails it.

Exit 0 on a written file, 1 when the overlay cannot be merged into a coherent
atlas, 2 on usage, unreadable input or invalid JSON. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _planets_of(system: object) -> list[dict]:
    if not isinstance(system, dict):
        return []
    planets = system.get("planets")
    return [p for p in planets if isinstance(p, dict)] if isinstance(planets, list) else []


def _known_planets(systems: list[dict]) -> set[str]:
    """Every drawable node, keyed ``system.planet`` the way the viewer keys it."""
    known: set[str] = set()
    for system in systems:
        sid = system.get("id")
        if not isinstance(sid, str):
            continue
        for planet in _planets_of(system):
            pid = planet.get("id")
            if isinstance(pid, str):
                known.add(f"{sid}.{pid}")
    return known


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def pillars_and_hypotheses(overlay: object) -> tuple[dict | None, str | None]:
    """``({"pillars": [...], "hypotheses": [...]}, None)`` or ``(None, refusal)``.

    Pure. Absent keys are empty lists: an overlay written before this
    contract is valid as it stands.
    """
    if not isinstance(overlay, dict):
        return None, "OVERLAY_NOT_AN_OBJECT"
    pillars = overlay.get("pillars", [])
    hypotheses = overlay.get("hypotheses", [])
    if not isinstance(pillars, list):
        return None, "OVERLAY_PILLARS_MALFORMED: pillars must be a list"
    if not isinstance(hypotheses, list):
        return None, "OVERLAY_HYPOTHESES_MALFORMED: hypotheses must be a list"
    contributions = {p.get("id") for p in _planets_of(overlay.get("system"))
                     if p.get("slot") == "contribution"}
    pillar_ids: set[str] = set()
    for index, pillar in enumerate(pillars):
        if not isinstance(pillar, dict) or not _text(pillar.get("id")) or not _text(pillar.get("label")):
            return None, f"PILLAR_MALFORMED: pillars[{index}] needs a non-empty id and label"
        if pillar["id"] in pillar_ids:
            return None, f"PILLAR_ID_DUPLICATED: {pillar['id']}"
        pillar_ids.add(pillar["id"])
        for key in ("detail", "contribution"):
            if key in pillar and not isinstance(pillar[key], str):
                return None, f"PILLAR_MALFORMED: pillars[{index}].{key} must be a string"
        if "contribution" in pillar and pillar["contribution"] not in contributions:
            return None, (f"PILLAR_CONTRIBUTION_UNKNOWN: {pillar['contribution']} is not a "
                          "contribution planet of this overlay")
    if hypotheses and not pillars:
        return None, "HYPOTHESES_WITHOUT_PILLARS: every hypothesis belongs to a pillar"
    hypothesis_ids: set[str] = set()
    for index, hypothesis in enumerate(hypotheses):
        if not isinstance(hypothesis, dict) or not all(
                _text(hypothesis.get(k)) for k in ("id", "statement", "pillar")):
            return None, (f"HYPOTHESIS_MALFORMED: hypotheses[{index}] needs a non-empty id, "
                          "statement and pillar")
        if hypothesis["id"] in hypothesis_ids:
            return None, f"HYPOTHESIS_ID_DUPLICATED: {hypothesis['id']}"
        hypothesis_ids.add(hypothesis["id"])
        if hypothesis["pillar"] not in pillar_ids:
            return None, f"HYPOTHESIS_PILLAR_UNKNOWN: {hypothesis['id']} names {hypothesis['pillar']}"
        experiments = hypothesis.get("experiments", [])
        if not isinstance(experiments, list) or not all(_text(e) for e in experiments):
            return None, (f"HYPOTHESIS_EXPERIMENTS_MALFORMED: {hypothesis['id']}.experiments must "
                          "be a list of experiment ids")
    return {"pillars": pillars, "hypotheses": hypotheses}, None


def merge(atlas: dict, overlay: object) -> tuple[dict | None, str | None]:
    """The merged atlas, or ``(None, refusal)``.

    Pure: the same two documents always yield the same one, with the SOTA
    side in the order it arrived. The caller decides what to do with the
    refusal; nothing is written here.
    """
    systems = atlas.get("systems")
    if not isinstance(systems, list) or not systems:
        return None, "ATLAS_SYSTEMS_NOT_A_NONEMPTY_LIST: run the checker first"
    links = atlas.get("links")
    if not isinstance(links, list):
        return None, "ATLAS_LINKS_NOT_A_LIST: run the checker first"
    if not isinstance(overlay, dict):
        return None, "OVERLAY_NOT_AN_OBJECT"

    system = overlay.get("system")
    if not isinstance(system, dict):
        return None, "OVERLAY_SYSTEM_MALFORMED"
    sid = system.get("id")
    if not isinstance(sid, str) or not sid.strip():
        return None, "OVERLAY_SYSTEM_MALFORMED"
    taken = {s.get("id") for s in systems if isinstance(s, dict)}
    if sid in taken:
        return None, f"SYSTEM_ID_TAKEN: {sid} is already a system in this constellation"

    overlay_links = overlay.get("links", [])
    if not isinstance(overlay_links, list):
        return None, "OVERLAY_LINKS_NOT_A_LIST"

    # The overlay's own floor and upper bound. This is the proposal's contract,
    # not
    # the constellation's: a paper states one novelty, a proposal argues three
    # to five concepts that carry it and name the issues it could resolve. That
    # is why the rule lives here and the slot's row stays 0..5 in the checker --
    # the constellation admits the slot, the proposal is held to its range.
    contributions = sum(1 for p in _planets_of(system) if p.get("slot") == "contribution")
    if not 3 <= contributions <= 5:
        return None, (f"OVERLAY_CONTRIBUTIONS_OUTSIDE_3_5: the proposal carries "
                      f"{contributions} contribution concept(s); the contract names 3 to 5")

    _found, refusal = pillars_and_hypotheses(overlay)
    if refusal is not None:
        return None, refusal

    merged_systems = [s for s in systems]
    merged_systems.append(system)
    known = _known_planets(merged_systems)

    written: list[dict] = [l for l in links if isinstance(l, dict)]
    for link in overlay_links:
        if not isinstance(link, dict):
            return None, "OVERLAY_LINK_MALFORMED"
        source = link.get("from")
        target_system = link.get("to_system")
        target = link.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            return None, "OVERLAY_LINK_MALFORMED"
        if f"{sid}.{source}" not in known:
            return None, f"LINK_SOURCE_UNKNOWN: {sid}.{source} is not a planet of this overlay"
        if not isinstance(target_system, str) or f"{target_system}.{target}" not in known:
            return None, (f"LINK_TARGET_UNKNOWN: {target_system}.{target} is not a planet "
                          "in the merged constellation")
        entry = {"from_system": sid, "from": source,
                 "to_system": target_system, "to": target}
        if "rel" in link:
            entry["rel"] = link["rel"]
        written.append(entry)

    merged = dict(atlas)
    merged["systems"] = merged_systems
    merged["links"] = written
    return merged, None


def _load(path: Path, label: str) -> tuple[object | None, str | None, int]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        return None, f"{label}_UNREADABLE: {error}", 2
    try:
        return json.loads(raw), None, 0
    except json.JSONDecodeError as error:
        return None, f"{label}_NOT_JSON: {error}", 2


def main(argv: list[str]) -> int:
    inputs: list[str] = []
    out_path: Path | None = None
    tokens = argv[1:]
    index = 0
    while index < len(tokens):
        if tokens[index] == "--out" and index + 1 < len(tokens):
            out_path = Path(tokens[index + 1])
            index += 2
        else:
            inputs.append(tokens[index])
            index += 1
    if len(inputs) != 2 or out_path is None:
        print("usage: merge_proposal_sky.py <sota atlas.json> <proposal sky.json> "
              "--out <merged atlas.json>", file=sys.stderr)
        return 2

    atlas, refusal, code = _load(Path(inputs[0]), "ATLAS")
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return code
    overlay, refusal, code = _load(Path(inputs[1]), "OVERLAY")
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return code

    merged, refusal = merge(atlas, overlay)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1

    try:
        out_path.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    except OSError as error:
        print(f"MERGED_UNWRITABLE: {error}", file=sys.stderr)
        return 2
    systems = len(merged["systems"])
    links = len(merged["links"])
    print(f"SKY_MERGED: {systems} systems, {links} links -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
