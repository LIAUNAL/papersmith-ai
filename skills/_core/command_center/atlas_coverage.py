"""Which references the paper cites that the SOTA constellation does not draw.

Two sources cite references, and each can get ahead of the constellation
(``sota-pool/atlas.json``, drawn by the sota-grapher from the pool):

- the proposal and the protocol cite pool references in
  ``.papersmith/citations.json``; a journal pass can add a pool reference that
  is cited before any system draws it;
- the manuscript cites ``paper/refs.bib`` entries; one the constellation does
  not draw becomes a placeholder system of the "Manuscript Citations" family
  (``atlas_manuscript.sync_constellation_citations``), built from its BibTeX
  entry with no abstract, so it has no real problem, novelty or results.

``coverage`` lists both, so the flow can resolve the abstracts, add the
references to the pool and have the sota-grapher draw them. Read-only.
Run as ``python -m skills._core.command_center.atlas_coverage --root <ws>``
(``smith atlas coverage``): JSON, exit 0 when complete, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import atlas_manuscript, atlas_reference, phase_steps

CITATIONS_REL = Path(".papersmith") / "citations.json"


def _cited_ids(root: Path) -> list[str]:
    data = atlas_reference._json(root / CITATIONS_REL)
    ideas = data.get("ideas") if isinstance(data, dict) else None
    seen: dict[str, str] = {}
    for entries in (ideas.values() if isinstance(ideas, dict) else []):
        for entry in entries if isinstance(entries, list) else []:
            ident = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(ident, str) and ident.strip():
                seen.setdefault(ident.strip().lower(), ident.strip())
    return sorted(seen.values(), key=str.lower)


def coverage(root: Path | str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    normalize = phase_steps._citations().normalize
    candidates = atlas_manuscript._candidate_list(atlas_reference._json(root / atlas_reference.POOL_REL))
    pool_keys: set[str] = set()
    for candidate in candidates:
        pool_keys |= atlas_reference._keys(normalize, candidate.get("identifier"), candidate.get("source_url"),
                                           candidate.get("url"))
    atlas = atlas_reference._json(root / atlas_reference.ATLAS_REL)
    real = [s for s in (atlas.get("systems") if isinstance(atlas, dict) else None) or [] if isinstance(s, dict)]
    drawn: set[str] = set()
    for system in real:
        drawn |= atlas_reference.system_keys(normalize, system, candidates)
    cited = _cited_ids(root)
    undrawn = [ident for ident in cited if normalize(ident) not in drawn]
    layer = atlas_manuscript.read_layer(root).get("layer") or {}
    placeholders = []
    for extra in layer.get("extra_systems") or []:
        if not isinstance(extra, dict):
            continue
        ident = extra.get("identifier") if isinstance(extra.get("identifier"), str) else ""
        key = normalize(ident) if ident else None
        placeholders.append({"cite_key": str(extra.get("cite_key") or ""), "identifier": ident,
                             "title": str(extra.get("title") or ""), "in_pool": bool(key and key in pool_keys)})
    return {"atlas": bool(real),
            "proposal": {"cited": len(cited), "undrawn": undrawn},
            "manuscript": {"cited": len((layer.get("summary") or {}).get("cited_keys") or [])
                           if isinstance((layer.get("summary") or {}).get("cited_keys"), list)
                           else int((layer.get("summary") or {}).get("cited_keys") or 0),
                           "placeholders": placeholders},
            "complete": bool(real) and not undrawn and not placeholders}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true", help="print JSON (the default)")
    args = parser.parse_args(argv)
    found = coverage(args.root)
    print(json.dumps(found, indent=2, ensure_ascii=False))
    return 0 if found["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
