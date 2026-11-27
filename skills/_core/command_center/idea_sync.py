"""The ideas follow the latest proposal revision: sync ``.papersmith/model_spec.json``.

The latest published revision's sky overlay
(``proposals/research-concept-<slug>-rNN.sky.json``) is the identity of the
proposal's ideas; the specification is their enrichment. The overlay gives:

- the pillars: ``id``, ``name`` (the overlay's ``label``) and ``contribution``;
- the hypotheses: ``id``, ``statement``, their pillar (``pillars``, and
  ``pillar`` where the file already uses it) and ``experiments``;
- the problem tree, when the overlay carries a ``problem_tree`` of the
  specification's shape: the central text (and ``problem_statement``), each
  cause's ``id`` and ``text`` and each effect's ``id``, ``text`` and
  ``caused_by``.

Everything else an agent wrote on a surviving id (``title``, ``summary``,
``details``, ``status``, ``evidence``, ``badge``, ``color``...) is kept. An id
the latest revision no longer holds leaves the active list and is kept under
``novelty.retired.<kind>`` with ``last_revision``, the newest revision whose
overlay still held it (the previous ``source_revision`` when none did); an id
that comes back takes its enrichment back from there. ``novelty.source_revision``
records the revision synced (``r21``). A list the overlay does not carry, or
carries empty, is left as the specification has it.

:func:`sync_novelty` is the pure merge, :func:`current_novelty` the read-side
view every reader shares (``/api/model``, the Phase 4 steps, the SOTA citations),
and :func:`sync` the writer behind "Update board" (``board_refresh.py``) and the
CLI the proposal-deliberation publish step runs::

    python skills/_core/command_center/idea_sync.py --root . [--dry-run] [--json]

The write keeps the file's indent, key order and trailing newline, and is
idempotent: a second run reports every id unchanged and writes nothing. With no
specification, no published revision or no overlay it reports why and writes
nothing. Stdlib only, no package-relative imports, so it also loads by path.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SPEC_REL = ".papersmith/model_spec.json"
_HERE = Path(__file__).resolve().parent
_CITATIONS = _HERE.parent / "results" / "citations.py"
_MERGER = _HERE.parents[1] / "proposal-deliberation" / "scripts" / "merge_proposal_sky.py"
_NUMBER = re.compile(r"r(\d+)(?:\.[A-Za-z.]+)?$")

#: Report prefixes, one per kind of idea.
_PREFIX = {"pillars": "pillar", "hypotheses": "hypothesis", "causes": "cause", "effects": "effect"}
#: Positional ids, as ``citations.py`` gives an idea without one.
_POSITION = {"pillars": "P", "hypotheses": "H", "causes": "DC", "effects": "EF"}


def _load(name: str, path: Path):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def _citations():
    """``results/citations.py``: its ``_latest``, ``_json`` and ``_REVISION``."""
    return _load("papersmith_citations", _CITATIONS)


def _merger():
    """``merge_proposal_sky.py``: its ``pillars_and_hypotheses``."""
    return _load("papersmith_merge_proposal_sky", _MERGER)


# --------------------------------------------------------------------------
# revisions
# --------------------------------------------------------------------------
def revision_number(label: Any) -> int | None:
    """``21`` for ``r21`` or ``research-concept-x-r21.md``; ``None`` otherwise."""
    match = _NUMBER.search(str(label or "").strip())
    return int(match.group(1)) if match else None


def revision_label(path: Path | None) -> str:
    number = revision_number(path.name) if path is not None else None
    return f"r{number:02d}" if number is not None else ""


def latest_overlay(root: Path) -> tuple[Path | None, Any]:
    """The latest published revision and its parsed overlay (``None`` when absent)."""
    cit = _citations()
    proposal = cit._latest(root / "proposals", root, cit._REVISION)
    if proposal is None:
        return None, None
    return proposal, cit._json(proposal.with_suffix(".sky.json"), root)


def identity(sky: Any) -> tuple[dict[str, Any] | None, str | None]:
    """``({"pillars", "hypotheses", "problem_tree"}, None)`` from an overlay, or
    ``(None, refusal)``; ``problem_tree`` is ``None`` when the overlay has none."""
    try:
        merger = _merger()
    except Exception as error:  # noqa: BLE001 - a reader never raises over a missing skill
        return None, f"MERGER_UNAVAILABLE: {type(error).__name__}"
    found, refusal = merger.pillars_and_hypotheses(sky)
    if found is None:
        return None, refusal
    tree = sky.get("problem_tree") if isinstance(sky, dict) else None
    return {**found, "problem_tree": tree if isinstance(tree, dict) else None}, None


def _carries(found: dict[str, Any] | None) -> bool:
    return bool(found and (found["pillars"] or found["hypotheses"] or found["problem_tree"]))


# --------------------------------------------------------------------------
# the pure merge
# --------------------------------------------------------------------------
def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _key(entry: dict[str, Any], kind: str, position: int) -> str:
    value = entry.get("id")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value.strip() if _text(value) else f"{_POSITION[kind]}{position}"


def _entries(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _links(entry: dict[str, Any]) -> list[str]:
    if isinstance(entry.get("pillars"), list):
        return [p for p in entry["pillars"] if isinstance(p, str)]
    return [entry["pillar"]] if _text(entry.get("pillar")) else []


class _Merge:
    """One kind's merge: the surviving entries in the overlay's order."""

    def __init__(self, novelty: dict[str, Any], kind: str, old: list[dict[str, Any]],
                 report: dict[str, Any], revision: str, history: dict[str, dict[str, str]]) -> None:
        self.novelty, self.kind, self.report, self.revision = novelty, kind, report, revision
        self.history = history.get(kind, {})
        self.old = {}
        for position, entry in enumerate(old, 1):
            self.old.setdefault(_key(entry, kind, position), entry)
        retired = novelty.get("retired") if isinstance(novelty.get("retired"), dict) else {}
        self.retired = {_key(e, kind, n): e for n, e in enumerate(_entries(retired.get(kind)), 1)}
        self.kept: list[dict[str, Any]] = []

    def entry(self, ident: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """A working copy of the id's entry and its previous state (``None`` when new)."""
        if ident in self.old:
            return copy.deepcopy(self.old[ident]), self.old[ident]
        if ident in self.retired:
            restored = {k: copy.deepcopy(v) for k, v in self.retired.pop(ident).items() if k != "last_revision"}
            return restored, None
        return {"id": ident}, None

    def put(self, ident: str, entry: dict[str, Any], before: dict[str, Any] | None, fields: tuple[str, ...]) -> None:
        name = f"{_PREFIX[self.kind]}:{ident}"
        if before is None:
            self.report["added"].append(name)
        else:
            changed = [f for f in fields if self._value(before, f) != self._value(entry, f)]
            if changed:
                self.report["changed"].append({"id": name, "fields": changed})
            else:
                self.report["unchanged"].append(name)
        self.kept.append(entry)

    @staticmethod
    def _value(entry: dict[str, Any], field: str) -> Any:
        return _links(entry) if field == "pillars" else entry.get(field)

    def close(self, previous: str) -> list[dict[str, Any]]:
        """The active list; every old id the overlay dropped goes to ``retired``."""
        seen = {_key(e, self.kind, n) for n, e in enumerate(self.kept, 1)}
        for ident, entry in self.old.items():
            if ident in seen:
                continue
            gone = copy.deepcopy(entry)
            gone.setdefault("id", ident)
            gone["last_revision"] = self.history.get(ident) or previous or None
            self.retired[ident] = gone
            self.report["pruned"].append(f"{_PREFIX[self.kind]}:{ident}")
        retired = self.novelty.get("retired") if isinstance(self.novelty.get("retired"), dict) else {}
        retired = dict(retired)
        if self.retired:
            retired[self.kind] = list(self.retired.values())
        else:
            retired.pop(self.kind, None)
        if retired:
            self.novelty["retired"] = retired
        else:
            self.novelty.pop("retired", None)
        return self.kept


def _empty_report(revision: str, previous: str) -> dict[str, Any]:
    return {"revision": revision, "previous_revision": previous or None,
            "added": [], "pruned": [], "changed": [], "unchanged": [], "kept": []}


def sync_novelty(novelty: Any, found: dict[str, Any], revision: str = "",
                 history: dict[str, dict[str, str]] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The specification's ``novelty`` synced to ``found`` (an :func:`identity`)
    and the change report. Pure: ``novelty`` is not modified. ``history`` maps a
    kind to ``{id: last revision that held it}``; ``revision`` (``r21``) is
    recorded as ``source_revision`` when given."""
    novelty = copy.deepcopy(novelty) if isinstance(novelty, dict) else {}
    previous = novelty.get("source_revision") if _text(novelty.get("source_revision")) else ""
    report = _empty_report(revision, previous)
    history = history or {}

    if found["pillars"]:
        merge = _Merge(novelty, "pillars", _entries(novelty.get("pillars")), report, revision, history)
        for pillar in found["pillars"]:
            entry, before = merge.entry(pillar["id"])
            entry["id"], entry["name"] = pillar["id"], pillar["label"]
            if "contribution" in pillar:
                entry["contribution"] = pillar["contribution"]
            if not _text(entry.get("summary")) and _text(pillar.get("detail")):
                entry["summary"] = pillar["detail"]
            merge.put(pillar["id"], entry, before, ("name", "contribution"))
        novelty["pillars"] = merge.close(previous)
    else:
        report["kept"].append("pillars")

    if found["hypotheses"]:
        merge = _Merge(novelty, "hypotheses", _entries(novelty.get("hypotheses")), report, revision, history)
        for hypothesis in found["hypotheses"]:
            entry, before = merge.entry(hypothesis["id"])
            entry["id"], entry["statement"] = hypothesis["id"], hypothesis["statement"]
            entry["pillars"] = [hypothesis["pillar"]]
            if "pillar" in entry:
                entry["pillar"] = hypothesis["pillar"]
            if "experiments" in hypothesis:
                entry["experiments"] = list(hypothesis["experiments"])
            merge.put(hypothesis["id"], entry, before, ("statement", "pillars", "experiments"))
        novelty["hypotheses"] = merge.close(previous)
    else:
        report["kept"].append("hypotheses")

    tree = found.get("problem_tree")
    if isinstance(tree, dict):
        _sync_tree(novelty, tree, report, revision, previous, history)
    else:
        report["kept"].append("problem_tree")

    if revision:
        novelty["source_revision"] = revision
    return novelty, report


def _sync_tree(novelty: dict[str, Any], tree: dict[str, Any], report: dict[str, Any], revision: str,
               previous: str, history: dict[str, dict[str, str]]) -> None:
    mine = novelty.get("problem_tree") if isinstance(novelty.get("problem_tree"), dict) else {}
    mine = dict(mine)
    central = tree.get("central") if isinstance(tree.get("central"), dict) else {}
    if _text(central.get("text")):
        old = mine.get("central") if isinstance(mine.get("central"), dict) else None
        new = {**(old or {}), "text": central["text"]}
        if old is None:
            report["added"].append("problem:central")
        elif old.get("text") != new["text"]:
            report["changed"].append({"id": "problem:central", "fields": ["text"]})
        else:
            report["unchanged"].append("problem:central")
        mine["central"] = new
        novelty["problem_statement"] = central["text"]
    for kind, fields in (("causes", ("text",)), ("effects", ("text", "caused_by"))):
        wanted = [e for e in _entries(tree.get(kind)) if _text(e.get("id")) and _text(e.get("text"))]
        if not wanted:
            continue
        merge = _Merge(novelty, kind, _entries(mine.get(kind)), report, revision, history)
        for item in wanted:
            entry, before = merge.entry(item["id"])
            entry["id"] = item["id"]
            for field in fields:
                if field in item:
                    entry[field] = copy.deepcopy(item[field])
            merge.put(item["id"], entry, before, fields)
        mine[kind] = merge.close(previous)
    novelty["problem_tree"] = mine


def current_novelty(novelty: Any, sky: Any) -> Any:
    """What every reader shows: the latest overlay's identity over the
    specification's enrichment. ``novelty`` unchanged when the overlay is
    absent, refused or carries none of the three lists."""
    found, _refusal = identity(sky) if isinstance(sky, dict) else (None, None)
    if not _carries(found):
        return novelty
    return sync_novelty(novelty, found)[0]


# --------------------------------------------------------------------------
# freshness
# --------------------------------------------------------------------------
def freshness(spec: Any, latest: str) -> dict[str, Any]:
    """``stale`` when the specification was synced from a revision older than
    ``latest`` (or never synced while one exists); ``contribution_type_stale``
    when a recorded ``contribution_type`` predates the newer of the two.

    The type's basis is ``contribution_type_revision``; a type without one is
    stale only when the specification was synced (``source_revision``)."""
    spec = spec if isinstance(spec, dict) else {}
    novelty = spec.get("novelty") if isinstance(spec.get("novelty"), dict) else {}
    source = novelty.get("source_revision") if _text(novelty.get("source_revision")) else ""
    latest_n, source_n = revision_number(latest), revision_number(source)
    stale = latest_n is not None and (source_n is None or source_n < latest_n)
    reference = max(n for n in (latest_n, source_n, -1) if n is not None)
    type_stale = False
    if isinstance(spec.get("contribution_type"), dict):
        basis = revision_number(spec.get("contribution_type_revision"))
        type_stale = (source_n is not None) if basis is None else basis < reference
    return {"stale": stale, "source_revision": source or None, "latest_revision": latest or None,
            "contribution_type_revision": spec.get("contribution_type_revision") or None,
            "contribution_type_stale": type_stale}


# --------------------------------------------------------------------------
# the writer
# --------------------------------------------------------------------------
def _history(root: Path, latest: Path) -> dict[str, dict[str, str]]:
    """``{kind: {id: newest older revision whose overlay held it}}``."""
    cit = _citations()
    folder = root / "proposals"
    ranked = []
    try:
        for path in folder.iterdir():
            match = cit._REVISION.match(path.name)
            if match and path != latest and path.is_file():
                ranked.append((int(match.group(1)), path))
    except OSError:
        return {}
    history: dict[str, dict[str, str]] = {}
    for _number, path in sorted(ranked, reverse=True):
        found, _refusal = identity(cit._json(path.with_suffix(".sky.json"), root))
        if not found:
            continue
        tree = found["problem_tree"] or {}
        for kind, items in (("pillars", found["pillars"]), ("hypotheses", found["hypotheses"]),
                            ("causes", _entries(tree.get("causes"))), ("effects", _entries(tree.get("effects")))):
            for item in items:
                if _text(item.get("id")):
                    history.setdefault(kind, {}).setdefault(item["id"], revision_label(path))
    return history


def _dumps(value: Any, original: str) -> str:
    """``value`` serialized the way ``original`` was: indent, escapes, final newline."""
    match = re.search(r"\n([ \t]+)[^\s]", original)
    indent: int | str | None = None
    if match:
        indent = "\t" if match.group(1).startswith("\t") else len(match.group(1))
    ensure_ascii = original.isascii() and "\\u" in original
    separators = None if indent is not None else ((", ", ": ") if ": " in original else (",", ":"))
    text = json.dumps(value, indent=indent, ensure_ascii=ensure_ascii, separators=separators)
    return text + "\n" if original.endswith("\n") else text


def _write(path: Path, text: str) -> None:
    handle, tmp = tempfile.mkstemp(prefix=".model_spec.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _result(state: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"ok": state != "failed", "state": state, "detail": detail, "spec": SPEC_REL,
            "written": False, **extra}


def describe(report: dict[str, Any]) -> str:
    counts = ", ".join(f"{len(report[k])} {k}" for k in ("added", "pruned", "changed", "unchanged"))
    return f"{report.get('revision') or '?'}: {counts}"


def sync(root: Path | str, *, dry_run: bool = False) -> dict[str, Any]:
    """Sync the specification to the latest revision; the change report.

    ``state`` is ``synced`` (written, or would be with ``dry_run``),
    ``unchanged`` (already current: nothing written), ``skipped`` (no
    specification, revision or overlay) or ``failed`` (unreadable
    specification or refused overlay). Never writes on ``skipped``, ``failed``
    or ``dry_run``."""
    root = Path(root).expanduser().resolve()
    path = root / SPEC_REL
    if not path.is_file():
        return _result("skipped", f"{SPEC_REL} not found; nothing to sync")
    try:
        original = path.read_text(encoding="utf-8")
        spec = json.loads(original)
    except (OSError, ValueError) as error:
        return _result("failed", f"{SPEC_REL} unreadable: {type(error).__name__}")
    if not isinstance(spec, dict):
        return _result("failed", f"{SPEC_REL} is not a JSON object")
    proposal, sky = latest_overlay(root)
    if proposal is None:
        return _result("skipped", "no published proposal revision in proposals/")
    revision = revision_label(proposal)
    sky_rel = proposal.with_suffix(".sky.json").relative_to(root).as_posix()
    if not isinstance(sky, dict):
        return _result("skipped", f"{sky_rel} not found or not JSON", revision=revision)
    found, refusal = identity(sky)
    if found is None:
        return _result("failed", f"{sky_rel} refused: {refusal}", revision=revision)
    if not _carries(found):
        return _result("skipped", f"{sky_rel} names no pillars, hypotheses or problem tree",
                       revision=revision)

    novelty, report = sync_novelty(spec.get("novelty"), found, revision, _history(root, proposal))
    synced = dict(spec)
    synced["novelty"] = novelty
    text = _dumps(synced, original)
    fresh = freshness(synced, revision)
    extra = {**report, "overlay": sky_rel, "dry_run": dry_run,
             "contribution_type_stale": fresh["contribution_type_stale"]}
    if text == original:
        return _result("unchanged", f"{describe(report)}; already current", **extra)
    if not dry_run:
        _write(path, text)
        extra["written"] = True
    return _result("synced", describe(report) + ("; dry run, nothing written" if dry_run else ""), **extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync .papersmith/model_spec.json to the latest proposal revision.")
    parser.add_argument("--root", default=".", help="workspace root (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="report the changes, write nothing")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    result = sync(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        print(f"IDEAS_{result['state'].upper()}: {result['detail']}")
        for key in ("added", "pruned", "unchanged"):
            if result.get(key):
                print(f"  {key}: {', '.join(result[key])}")
        for item in result.get("changed") or []:
            print(f"  changed: {item['id']} ({', '.join(item['fields'])})")
        if result.get("contribution_type_stale"):
            print("  contribution_type: stale; re-classify it with the paper-reviewer and record "
                  "contribution_type_revision")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
