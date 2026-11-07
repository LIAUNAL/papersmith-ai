"""The manuscript layer of the SOTA atlas: which pool systems the paper cites.

``sota-pool/atlas.json`` is phase-2 evidence written by the ``sota-grapher``
agent during ``/plausibility``; this module never modifies it. It derives a
separate file, ``sota-pool/atlas.manuscript.json``, that marks every atlas
system as cited or not by the manuscript and lists the cited papers the pool
does not hold.

The join, in one direction only:

* a planet's ``evidence.origin`` names a pool candidate (its ``identifier``,
  ``source_url`` or ``url``, exactly as ``check_atlas.py`` requires);
* an evidence record (``paper/.paper-writing/evidence/<block>.jsonl``) names
  the source it quotes by ``identifier`` + ``resolver``;
* a cite key without such a record falls back to its ``paper/refs.bib``
  entry: its ``doi``, its ``eprint``, an ``arXiv:<id>`` named in its
  ``journal``/``note``/``howpublished``, and its ``url``;
* both sides are compared through ``paper_bib.source_identity`` (DOI and
  arXiv normalization), plus the raw lower-cased strings; evidence
  identifiers are tried first;
* a cite key with no identifier at all (no evidence identifier, none in its
  bib entry) joins by its normalized bib ``title`` when exactly one system
  carries that title (its own or a linked pool candidate's); an ambiguous or
  unknown title stays an extra system;
* a cite key counts as cited when ``paper/main.tex`` cites it
  (``paper_bib.cited_keys``); without ``main.tex``, when ``paper/refs.bib``
  holds it (``paper_bib.entry_keys``).

Public functions (stable shapes; ``manuscript_graph`` and others reuse them):

``cited_systems(root) -> dict``
    Pure read. ``{"cite_source": "main.tex" | "refs.bib" | "none",
    "systems": [{"id", "title", "cited", "cite_keys", "matches", "blocks",
    "claims"}],
    "extra_systems": [{"cite_key", "identifier", "resolver", "title",
    "blocks", "claims"}], "cited_keys": [...]}``. ``claims`` items are ``{"block", "cite_key",
    "claim", "verdict"}``, latest record per (block, cite key, claim), sorted.
    ``matches`` items are ``{"cite_key", "via"}``, ``via`` naming the join
    that held: ``evidence``, ``bib`` (a bib identifier) or ``title``.
    Raises on unreadable inputs (callers that must not fail use ``refresh``).
``build_layer(root) -> dict``
    The document written to disk: ``cited_systems`` plus ``schema``,
    ``summary`` and ``generated_from`` (SHA-256 of each input, so staleness
    is detectable). Deterministic: no timestamp.
``write_layer(root) -> dict``
    Writes the layer atomically; ``{"ok", "status", "path", "summary"}``.
    ``status`` is ``written`` or ``absent`` (no ``atlas.json``: nothing
    written).
``refresh(root) -> dict | None``
    The trigger used after ``bib build``, ``verify`` and a dashboard compile:
    ``None`` when the workspace has no atlas, otherwise the ``write_layer``
    result, or ``{"ok": False, "status": "error", "warning": ...}``. Never
    raises.
``read_layer(root) -> dict``
    For ``GET /api/atlas/manuscript``: ``{"status": "ok" | "absent" |
    "invalid", "stale", "layer"}``.

Run standalone from a workspace root::

    python -m skills._core.command_center.atlas_manuscript [--root .] [--json]

Stdlib only, plus the workspace's own ``paper_bib``/``paper_evidence`` loaded
from ``skills/paper-writing/scripts``. No relative imports, so
``paper_cli.py`` can load this file by path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "papersmith.atlas-manuscript/v1"
LAYER_REL = "sota-pool/atlas.manuscript.json"
INPUT_MAX_BYTES = 8 * 1024 * 1024

_HERE = Path(__file__).resolve()
_PAPER_SCRIPTS = _HERE.parents[2] / "paper-writing" / "scripts"
_IMPLEMENTATION = _HERE.parents[1] / "implementation"

_BIB_FIELDS = ("title", "doi", "eprint", "archiveprefix", "journal", "note", "howpublished", "url", "year", "author", "booktitle", "publisher")


def _paper_modules():
    """``paper_bib`` and ``paper_evidence`` from the workspace's own skill."""
    for path in (_PAPER_SCRIPTS, _IMPLEMENTATION):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import paper_bib  # noqa: PLC0415
    import paper_evidence  # noqa: PLC0415
    return paper_bib, paper_evidence


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def _read(path: Path) -> bytes | None:
    if not path.is_file():
        return None
    if path.stat().st_size > INPUT_MAX_BYTES:
        raise ValueError(f"{path.name} exceeds {INPUT_MAX_BYTES} bytes")
    return path.read_bytes()


def _sha(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _evidence_digest(paper_dir: Path) -> str | None:
    store = paper_dir / ".paper-writing" / "evidence"
    if not store.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(store.glob("*.jsonl")):
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _digests(root: Path, paper: Path) -> dict[str, str | None]:
    pool = root / "sota-pool"
    return {
        "atlas.json": _sha(_read(pool / "atlas.json")),
        "candidates.json": _sha(_read(pool / "candidates.json")),
        "evidence": _evidence_digest(paper),
        "main.tex": _sha(_read(paper / "main.tex")),
        "refs.bib": _sha(_read(paper / "refs.bib")),
    }


def _bib_fields(refs: bytes | None) -> dict[str, dict[str, str]]:
    """``{cite_key: {field: value}}`` for ``_BIB_FIELDS``, read by the shared
    ``paper_bib.parse_bib`` and each value on one line."""
    parsed = _paper_modules()[0].parse_bib((refs or b"").decode("utf-8", errors="replace"))
    return {key: {name: " ".join(value.split()) for name, value in entry.items() if name in _BIB_FIELDS}
            for key, entry in parsed.items()}


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------
def _keys(paper_bib: Any, value: Any, resolver: Any = None) -> set[str]:
    """Every comparable key a source string answers to."""
    if not isinstance(value, str) or not value.strip():
        return set()
    text = value.strip()
    keys = {"raw:" + text.lower()}
    resolvers: list[str] = []
    if isinstance(resolver, str) and resolver:
        resolvers.append(resolver)
    lowered = text.lower()
    if paper_bib._ARXIV_PREFIX_RE.match(text):
        resolvers.append("arxiv")
    if lowered.startswith("10.") or any(lowered.startswith(p) for p in paper_bib._DOI_PREFIXES):
        resolvers.append("crossref")
    for name in resolvers:
        identity = paper_bib.source_identity(text, name)
        if identity is not None:
            keys.add(f"{identity[0]}:{identity[1]}")
    return keys


def _bib_identifiers(entry: dict[str, str]) -> list[tuple[str, str]]:
    """``(identifier, resolver)`` pairs a bib entry names, DOI first."""
    return _paper_modules()[0].bib_identifiers(entry)


def _bib_keys(paper_bib: Any, entry: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    for identifier, resolver in _bib_identifiers(entry):
        keys |= _keys(paper_bib, identifier, resolver)
    keys |= _keys(paper_bib, entry.get("url"))  # doi.org / arxiv.org URLs, or the raw URL
    return keys


def _title_key(value: Any) -> str:
    """``paper_bib.title_key``, the normalization ``resolve --references`` matches by."""
    return _paper_modules()[0].title_key(value)


def _candidate_list(pool: Any) -> list[dict]:
    candidates = pool.get("candidates") if isinstance(pool, dict) else pool
    return [c for c in candidates if isinstance(c, dict)] if isinstance(candidates, list) else []


def _system_origins(system: dict) -> set[str]:
    origins: set[str] = set()
    for planet in system.get("planets") or []:
        evidence = planet.get("evidence") if isinstance(planet, dict) else None
        origin = evidence.get("origin") if isinstance(evidence, dict) else None
        if isinstance(origin, str) and origin.strip():
            origins.add(origin.strip())
    return origins


def _system_candidates(origins: set[str], candidates: list[dict]) -> list[dict]:
    """The pool candidates a system's planets name."""
    return [c for c in candidates
            if {str(c.get(k)).strip() for k in ("identifier", "source_url", "url")
                if isinstance(c.get(k), str)} & origins]


def _system_titles(system: dict, candidates: list[dict]) -> set[str]:
    titles = {_title_key(system.get("title"))}
    titles |= {_title_key(c.get("title"))
               for c in _system_candidates(_system_origins(system), candidates)}
    return titles - {""}


def _system_keys(paper_bib: Any, system: dict, candidates: list[dict]) -> set[str]:
    origins = _system_origins(system)
    keys: set[str] = set()
    for origin in origins:
        keys |= _keys(paper_bib, origin)
    for candidate in _system_candidates(origins, candidates):
        keys |= _keys(paper_bib, candidate.get("identifier"), candidate.get("resolver"))
        keys |= _keys(paper_bib, candidate.get("source_url"))
        keys |= _keys(paper_bib, candidate.get("url"))
    return keys


def _claims(records: list[dict]) -> list[dict]:
    latest: dict[tuple, dict] = {}
    for record in records:  # oldest first: the last one wins
        key = (record.get("block_id"), record.get("cite_key"), record.get("claim"))
        latest[key] = {"block": str(record.get("block_id") or ""),
                       "cite_key": str(record.get("cite_key") or ""),
                       "claim": str(record.get("claim") or ""),
                       "verdict": str(record.get("verdict") or "")}
    return sorted(latest.values(), key=lambda c: (c["block"], c["cite_key"], c["claim"]))


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def _paper_dir(root: Path, paper_dir: Path | str | None) -> Path:
    return root / "paper" if paper_dir is None else Path(paper_dir).expanduser().resolve()


def cited_systems(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    """The citation join; see the module docstring for the return shape.
    ``paper_dir`` defaults to ``<root>/paper``."""
    paper_bib, paper_evidence = _paper_modules()
    root = Path(root).expanduser().resolve()
    pool, paper = root / "sota-pool", _paper_dir(root, paper_dir)
    atlas_raw = _read(pool / "atlas.json")
    atlas = json.loads(atlas_raw.decode("utf-8")) if atlas_raw is not None else {"systems": []}
    systems = [s for s in atlas.get("systems") or [] if isinstance(s, dict)]
    pool_raw = _read(pool / "candidates.json")
    candidates = _candidate_list(json.loads(pool_raw.decode("utf-8"))) if pool_raw else []

    tex, refs = _read(paper / "main.tex"), _read(paper / "refs.bib")
    if tex is not None:
        cited, source = paper_bib.cited_keys(tex), "main.tex"
    elif refs is not None:
        cited, source = paper_bib.entry_keys(refs), "refs.bib"
    else:
        cited, source = set(), "none"
    bib = _bib_fields(refs)
    records = [r for r in (paper_evidence.read_all_records(paper) if paper.is_dir() else [])
               if isinstance(r, dict) and r.get("cite_key") in cited]
    by_key: dict[str, list[dict]] = {}
    for record in records:
        by_key.setdefault(record["cite_key"], []).append(record)
    evidence_ids: dict[str, set[str]] = {}
    bib_ids: dict[str, set[str]] = {}
    for key in cited:
        ids: set[str] = set()
        for record in by_key.get(key, []):
            ids |= _keys(paper_bib, record.get("identifier"), record.get("resolver"))
        evidence_ids[key] = ids
        bib_ids[key] = _bib_keys(paper_bib, bib.get(key, {}))

    # A key with no identifier at all joins by title, only when one system holds it.
    system_titles = [_system_titles(s, candidates) for s in systems]
    title_owner: dict[str, int] = {}
    for key in cited:
        title = _title_key(bib.get(key, {}).get("title"))
        if evidence_ids[key] or bib_ids[key] or not title:
            continue
        owners = [i for i, titles in enumerate(system_titles) if title in titles]
        if len(owners) == 1:
            title_owner[key] = owners[0]

    matched: set[str] = set()
    out_systems = []
    for index, system in enumerate(systems):
        keys = _system_keys(paper_bib, system, candidates)
        matches = []
        for key in sorted(cited):
            if evidence_ids[key] & keys:
                matches.append({"cite_key": key, "via": "evidence"})
            elif bib_ids[key] & keys:
                matches.append({"cite_key": key, "via": "bib"})
            elif title_owner.get(key) == index:
                matches.append({"cite_key": key, "via": "title"})
        cite_keys = [m["cite_key"] for m in matches]
        matched.update(cite_keys)
        sys_records = [r for k in cite_keys for r in by_key.get(k, [])]
        out_systems.append({
            "id": str(system.get("id") or ""), "title": str(system.get("title") or ""),
            "cited": bool(cite_keys), "cite_keys": cite_keys, "matches": matches,
            "blocks": sorted({str(r.get("block_id") or "") for r in sys_records}),
            "claims": _claims(sys_records),
        })

    extra = []
    for key in sorted(cited - matched):
        key_records = by_key.get(key, [])
        last = key_records[-1] if key_records else {}
        named = _bib_identifiers(bib.get(key, {}))
        identifier = last.get("identifier") or (named[0][0] if named else None)
        resolver = last.get("resolver") or (named[0][1] if named else None)
        extra.append({
            "cite_key": key, "identifier": identifier, "resolver": resolver,
            "title": bib.get(key, {}).get("title"),
            "blocks": sorted({str(r.get("block_id") or "") for r in key_records}),
            "claims": _claims(key_records),
        })
    return {"cite_source": source, "systems": out_systems, "extra_systems": extra,
            "cited_keys": sorted(cited)}


def build_layer(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    joined = cited_systems(root, paper_dir=paper_dir)
    systems = joined["systems"]
    summary = {
        "systems_total": len(systems),
        "cited_systems": sum(1 for s in systems if s["cited"]),
        "uncited_systems": [s["id"] for s in systems if not s["cited"]],
        "extra_cited": len(joined["extra_systems"]),
        "cited_keys": len(joined["cited_keys"]),
    }
    return {"schema": SCHEMA, "generated_from": _digests(root, _paper_dir(root, paper_dir)),
            "cite_source": joined["cite_source"], "summary": summary,
            "systems": systems, "extra_systems": joined["extra_systems"]}


def write_layer(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    pool = root / "sota-pool"
    if not (pool / "atlas.json").is_file():
        return {"ok": False, "status": "absent", "path": LAYER_REL,
                "detail": "sota-pool/atlas.json not found: run the plausibility skill first"}
    target = (root / LAYER_REL).resolve()
    target.relative_to(root)  # ValueError when sota-pool escapes the workspace
    layer = build_layer(root, paper_dir=paper_dir)
    text = json.dumps(layer, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".atlas.manuscript.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {"ok": True, "status": "written", "path": LAYER_REL, "summary": layer["summary"]}


def _load_render_atlas():
    for candidate in (
        _HERE.parents[1] / "plausibility" / "scripts" / "render_atlas.py",
        _HERE.parents[2] / "plausibility" / "scripts" / "render_atlas.py",
    ):
        if candidate.is_file():
            import importlib.util  # noqa: PLC0415
            spec = importlib.util.spec_from_file_location("render_atlas", candidate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def build_constellation_with_citations(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    """Merge the SOTA pool atlas with all cited references in the manuscript.

    In-pool systems cited by the manuscript are marked with cited=True and their
    citing blocks. Extra cited references outside the pool are added as valid
    solar systems in the 'Manuscript Citations' family, complete with planets
    for citing blocks, literature topics, claims, and BibTeX identifiers.
    """
    root = Path(root).expanduser().resolve()
    pool = root / "sota-pool"
    atlas_path = pool / "atlas.json"
    if not atlas_path.is_file():
        raise FileNotFoundError(f"atlas.json not found in {pool}")

    base_atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    layer_data = build_layer(root, paper_dir=paper_dir)
    paper = _paper_dir(root, paper_dir)
    refs_bytes = _read(paper / "refs.bib")
    bib_map = _bib_fields(refs_bytes)

    cited_by_id = {s["id"]: s for s in layer_data.get("systems", []) if s.get("cited")}

    out_systems = []
    existing_ids = set()
    for sys_entry in base_atlas.get("systems", []):
        entry = dict(sys_entry)
        sid = entry.get("id", "")
        existing_ids.add(sid)
        if sid in cited_by_id:
            info = cited_by_id[sid]
            entry["cited"] = True
            entry["citing_blocks"] = info.get("blocks", [])
            entry["claims"] = info.get("claims", [])
            planets = []
            blocks_label = ", ".join(info.get("blocks", [])) or "manuscript"
            for p in entry.get("planets", []):
                p_copy = dict(p)
                if p_copy.get("slot") == "sun":
                    cur_detail = p_copy.get("detail", "")
                    if "[📚 Cited in:" not in cur_detail:
                        p_copy["detail"] = f"{cur_detail} [📚 Cited in: {blocks_label}]"
                planets.append(p_copy)
            entry["planets"] = planets
        out_systems.append(entry)

    extra_systems = layer_data.get("extra_systems", [])
    new_links = list(base_atlas.get("links", []))
    prev_extra_id = None

    for extra in extra_systems:
        ckey = extra.get("cite_key", "")
        if not ckey or ckey in existing_ids:
            continue
        existing_ids.add(ckey)

        b_entry = bib_map.get(ckey, {})
        title = extra.get("title") or b_entry.get("title") or ckey
        raw_year = b_entry.get("year", "2024")
        try:
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", str(raw_year))
            year = int(year_match.group(1)) if year_match else 2024
        except Exception:
            year = 2024

        identifier = extra.get("identifier") or b_entry.get("doi") or f"cite:{ckey}"
        source_url = b_entry.get("url") or (f"https://doi.org/{b_entry['doi']}" if b_entry.get("doi") else "")
        blocks = extra.get("blocks", [])
        claims = extra.get("claims", [])
        blocks_text = ", ".join(blocks) if blocks else "manuscript"

        planets = [
            {
                "id": "sun", "slot": "sun", "orbit": 0, "provenance": "stated",
                "label": f"{ckey} ({year})",
                "detail": f"{title} [📚 Cited in: {blocks_text}]",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "fam", "slot": "family", "orbit": 2, "provenance": "grouped",
                "label": "Manuscript Citations",
                "detail": f"Cited in manuscript: {blocks_text}",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "app", "slot": "topic_app", "orbit": 1, "provenance": "stated",
                "label": f"Cited in: {blocks_text}",
                "detail": f"Sections citing {ckey}: {blocks_text}",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "ai", "slot": "topic_ai", "orbit": 1, "provenance": "stated",
                "label": "Referenced Literature",
                "detail": f"Cited literature: {ckey} ({year})",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "prob", "slot": "problem", "orbit": 1, "provenance": "stated",
                "label": "Theoretical Context",
                "detail": f"Contextual foundation for manuscript: {title}",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "nov", "slot": "novelty", "orbit": 1, "provenance": "stated",
                "label": "Literature Foundation",
                "detail": f"Prior work cited in {blocks_text}",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "res", "slot": "result", "orbit": 3, "provenance": "stated",
                "label": f"Claims: {len(claims)}" if claims else "Cited in manuscript",
                "detail": " · ".join(c.get("claim", "") for c in claims) if claims else title,
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            },
            {
                "id": "concl", "slot": "conclusion", "orbit": 3, "provenance": "stated",
                "label": f"Key: {ckey}",
                "detail": f"BibTeX key: {ckey} (Year: {year})",
                "evidence": {"origin": identifier, "quote": title[:120], "retrieved": "2026-11-02"}
            }
        ]

        for pid in ("fam", "app", "ai", "prob", "nov", "res", "concl"):
            new_links.append({
                "from_system": ckey, "from": "sun",
                "to_system": ckey, "to": pid,
                "rel": "supports"
            })

        if prev_extra_id:
            new_links.append({
                "from_system": prev_extra_id, "from": "fam",
                "to_system": ckey, "to": "fam",
                "rel": "shares-family-with"
            })
        prev_extra_id = ckey

        out_systems.append({
            "id": ckey,
            "title": title,
            "year": year,
            "identifier": identifier,
            "source_url": source_url,
            "cited": True,
            "citing_blocks": blocks,
            "claims": claims,
            "planets": planets
        })

    return {
        "pool": base_atlas.get("pool", "sota-pool/candidates.json"),
        "retrieved": base_atlas.get("retrieved", "2026-11-02"),
        "systems": out_systems,
        "links": new_links,
    }


def sync_constellation_citations(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    """Synchronize the 3D constellation HTML with all manuscript citations."""
    root = Path(root).expanduser().resolve()
    pool = root / "sota-pool"
    if not (pool / "atlas.json").is_file():
        return {"ok": False, "status": "absent", "detail": "sota-pool/atlas.json not found"}

    try:
        layer_res = write_layer(root, paper_dir=paper_dir)
        constellation = build_constellation_with_citations(root, paper_dir=paper_dir)

        with_manuscript_path = pool / "atlas.with-manuscript.json"
        with_manuscript_path.write_text(
            json.dumps(constellation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8"
        )

        render_atlas = _load_render_atlas()
        if render_atlas is not None:
            html = render_atlas.render(
                constellation,
                title="SOTA constellation",
                heading="SOTA constellation — with manuscript citations"
            )
            (pool / "atlas.html").write_text(html, encoding="utf-8")

        summary = dict(layer_res.get("summary", {})) if isinstance(layer_res, dict) else {}
        summary["systems_total"] = len(constellation["systems"])
        summary["cited_systems"] = sum(1 for s in constellation["systems"] if s.get("cited"))
        summary["html_path"] = "sota-pool/atlas.html"

        return {
            "ok": True,
            "status": "synchronized",
            "path": "sota-pool/atlas.html",
            "systems_total": summary["systems_total"],
            "cited_systems": summary["cited_systems"],
            "extra_cited": summary.get("extra_cited", 0),
            "summary": summary,
        }
    except Exception as exc:
        return {"ok": False, "status": "error", "detail": str(exc)[:300]}


def refresh(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any] | None:
    """Rebuild after a manuscript event; ``None`` when there is no atlas."""
    try:
        root = Path(root).expanduser().resolve()
        if not (root / "sota-pool" / "atlas.json").is_file():
            return None
        res = write_layer(root, paper_dir=paper_dir)
        sync_res = sync_constellation_citations(root, paper_dir=paper_dir)
        return {**res, "constellation_sync": sync_res}
    except Exception as exc:  # noqa: BLE001 - a trigger never fails its command
        return {"ok": False, "status": "error", "path": LAYER_REL,
                "warning": f"atlas manuscript layer not rebuilt: {type(exc).__name__}: {exc}"[:300]}


def read_layer(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    path = root / LAYER_REL
    if not path.is_file():
        return {"status": "absent", "stale": None, "layer": None}
    try:
        layer = json.loads(_read(path).decode("utf-8"))
        if not isinstance(layer, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "stale": None, "layer": None, "detail": str(exc)[:300]}
    try:
        stale = layer.get("generated_from") != _digests(root, _paper_dir(root, paper_dir))
    except (OSError, ValueError):
        stale = None
    return {"status": "ok", "stale": stale, "layer": layer}


def describe(result: dict[str, Any]) -> str:
    if result.get("ok"):
        s = result["summary"]
        return (f"atlas manuscript layer: {s['cited_systems']}/{s['systems_total']} systems cited, "
                f"{s['extra_cited']} cited papers outside the pool -> {result['path']}")
    return f"atlas manuscript layer not written ({result.get('status')}): " \
           f"{result.get('detail') or result.get('warning')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skills._core.command_center.atlas_manuscript",
        description="Write sota-pool/atlas.manuscript.json: atlas systems cited by the manuscript.")
    parser.add_argument("--root", default=".", help="workspace root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--sync", action="store_true", help="synchronize the 3D constellation HTML with all citations")
    args = parser.parse_args(argv)
    try:
        if args.sync:
            result = sync_constellation_citations(args.root)
        else:
            result = write_layer(args.root)
    except Exception as exc:  # noqa: BLE001 - reported, exit 1
        result = {"ok": False, "status": "error", "path": LAYER_REL,
                  "detail": f"{type(exc).__name__}: {exc}"[:300]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(describe(result))
    if not result["ok"]:
        print(describe(result), file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
