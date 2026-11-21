"""paper_couplings: the missing producer for `paper/couplings.json`.

`verify` (`paper_coupling_evidence.py`, `paper_verify.py`) has always been
able to READ this file. Until `the-skill-stops-trusting-memory`, item 4,
nothing in this skill could WRITE it: the operator's only path to a
runnable `verify` was hand-editing an untracked JSON file with no schema
check anywhere, and SKILL.md's own Decision Gate ("declare the couplings
before running `verify` again") named an action no verb performed. A verb
that can never run is the defect; a clearer refusal message alone is not a
fix (`the-skill-stops-trusting-memory` task text) -- this module is the
producer instead.

Deliberately NOT a region inside `main.tex`: `couplings.json` is untracked,
sibling to `refs.bib`, exactly like `paper_bib.build_refs_bib` writes
`refs.bib` whole rather than through the block/region machinery
`paper_block.py`/`paper_region.py` own. This module reuses that same
"rebuild whole, atomically, never append in place" shape.

Unlike `refs.bib` (`paper_bib.py`'s own Decision 4: "no function or CLI
flag anywhere in this skill accepts caller-composed entry text"),
`couplings.json` is legitimately hand-authored content: contribution
names, chain words, artefact cell names and future-work directions are the
operator's own judgment about the paper's structure, not something a
connector resolves. This module's job is validating the SHAPE the real
consumers (`paper_coupling_evidence._read_declaration_record`,
`paper_verify.py`'s seven checks) actually read, before a byte is written
-- never composing the content itself.

Public surface:

    validate_couplings_shape(record) -> None  (raises COUPLINGS_RECORD_MALFORMED)
    write_couplings(paper_dir, record) -> dict
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_coupling_evidence  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402


def _require_list_of_str(value, field: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise Refused("COUPLINGS_RECORD_MALFORMED", f"{field!r} must be a JSON array of strings")


def _require_dict(value, field: str) -> dict:
    if not isinstance(value, dict):
        raise Refused("COUPLINGS_RECORD_MALFORMED", f"{field!r} must be a JSON object")
    return value


def validate_couplings_shape(record: dict) -> None:
    """Refuses `COUPLINGS_RECORD_MALFORMED` (work-state) unless `record`
    carries at least the shape every real reader needs:

    - a top-level JSON object
    - `blocks`: a non-empty JSON object (`paper_coupling_evidence.
      _read_declaration_record`'s own minimum gate against `DECLARATION_
      RECORD_ABSENT`, checked here too so a malformed record is diagnosed
      at WRITE time rather than surfacing as "nothing declared" later)
    - `facts.contributions` / `facts.limitations`, when present: arrays of
      strings (`paper_verify.check_contribution_list`/`check_future_work`)
    - `chain.links`, when present: an array of objects, each carrying a
      string `word` (`paper_verify.check_chain`)
    - `artefacts.setup_cells` / `artefacts.results_artefacts`, when
      present: arrays of strings (`paper_verify.check_artefacts`)
    - `future_work.directions`, when present: an array of objects, each
      carrying string `id`/`limitation`/`cite_key`
      (`paper_verify.check_future_work`)

    Every other field a caller adds is passed through unchecked -- this is
    a floor, not a schema lock; `paper_verify.py`'s own checks already
    degrade gracefully (`unmeasured`, `BLOCK_NOT_DECLARED`) for a field
    that is simply absent.
    """
    if not isinstance(record, dict):
        raise Refused("COUPLINGS_RECORD_MALFORMED", "the couplings record must be a JSON object")

    blocks = record.get("blocks")
    if not isinstance(blocks, dict) or not blocks:
        raise Refused(
            "COUPLINGS_RECORD_MALFORMED",
            "'blocks' must be a non-empty JSON object naming every block this record declares",
        )

    if "facts" in record:
        facts = _require_dict(record["facts"], "facts")
        if "contributions" in facts:
            _require_list_of_str(facts["contributions"], "facts.contributions")
        if "limitations" in facts:
            _require_list_of_str(facts["limitations"], "facts.limitations")

    if "chain" in record:
        chain = _require_dict(record["chain"], "chain")
        if "links" in chain:
            links = chain["links"]
            if not isinstance(links, list):
                raise Refused("COUPLINGS_RECORD_MALFORMED", "'chain.links' must be a JSON array")
            for link in links:
                link_obj = _require_dict(link, "chain.links[*]")
                if not isinstance(link_obj.get("word"), str):
                    raise Refused(
                        "COUPLINGS_RECORD_MALFORMED", "each 'chain.links[*]' needs a string 'word'"
                    )

    if "artefacts" in record:
        artefacts = _require_dict(record["artefacts"], "artefacts")
        if "setup_cells" in artefacts:
            _require_list_of_str(artefacts["setup_cells"], "artefacts.setup_cells")
        if "results_artefacts" in artefacts:
            _require_list_of_str(artefacts["results_artefacts"], "artefacts.results_artefacts")

    if "future_work" in record:
        future_work = _require_dict(record["future_work"], "future_work")
        if "directions" in future_work:
            directions = future_work["directions"]
            if not isinstance(directions, list):
                raise Refused(
                    "COUPLINGS_RECORD_MALFORMED", "'future_work.directions' must be a JSON array"
                )
            for direction in directions:
                direction_obj = _require_dict(direction, "future_work.directions[*]")
                for key in ("id", "limitation", "cite_key"):
                    if not isinstance(direction_obj.get(key), str):
                        raise Refused(
                            "COUPLINGS_RECORD_MALFORMED",
                            f"each 'future_work.directions[*]' needs a string {key!r}",
                        )
    if "citation_policy" in record:
        # #182: the opt-in cite-once policy `verify` reads (CITED_MORE_THAN_ONCE).
        policy = _require_dict(record["citation_policy"], "citation_policy")
        if "cite_once" in policy and not isinstance(policy["cite_once"], bool):
            raise Refused("COUPLINGS_RECORD_MALFORMED", "'citation_policy.cite_once' must be true or false")


def _atomic_replace(path: Path, data: bytes) -> None:
    """Same shape `paper_block.py`/`paper_contract.py`/`paper_declarations.
    py` each already use for their own atomic writes: a same-directory temp
    file + `os.replace`, so a process interrupted mid-write never leaves
    `path` torn."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def write_couplings(paper_dir: Path, record: dict) -> dict:
    """Validates `record` (`validate_couplings_shape`) then writes it WHOLE
    to `paper/couplings.json`, atomically -- never appended, never merged
    with what was there before, matching `paper_bib.build_refs_bib`'s own
    "rebuild whole" shape for the sibling untracked file it owns.
    """
    validate_couplings_shape(record)
    path = paper_dir / paper_coupling_evidence.COUPLINGS_RECORD_NAME
    data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_replace(path, data)
    return {"path": str(path), "blocks": sorted(record["blocks"])}
