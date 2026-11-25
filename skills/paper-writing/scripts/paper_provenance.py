"""paper_provenance: the `provenance` region — per written block, the
contract digest and declaration generation it stood on at write time.

Written once, at `substitute --contract` time, and never reconstructed
afterward. `plan` (Slice C2) reads it, names drift, and rewrites nothing.

Deliberately does NOT import `paper_block.py`: `paper_block.substitute`
imports THIS module (to write a provenance record after its own 9-step
write succeeds), so the reverse import would be circular. Every function
here takes an already-resolved `tex_path: Path` rather than a `paper_dir`,
one level lower than `paper_declarations.py`'s own disk-path resolution.

Public surface:

    record_write(tex_path, block_id, contract_path, *, clock=...) -> dict
        (raises PROVENANCE_HAND_EDITED; the contract's own readability is
        the CALLER's job — `paper_block.substitute` checks
        `CONTRACT_UNREADABLE` before calling this, per design.md's ordering
        requirement: the check happens before any main.tex byte is
        written, and never reorders any pre-existing `substitute` refusal)
    read_provenance(main_tex_bytes) -> dict|None
    declarations_generation(main_tex_bytes) -> int
    drift(main_tex_bytes, block_id, contract_path) -> bool|None
        (None means `unprovenanced` — never treated as current or drifted)
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_region  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402


def _atomic_replace(path: Path, data: bytes) -> None:
    """Same shape `paper_block.py`'s, `paper_contract.py`'s and
    `paper_declarations.py`'s own `_atomic_replace` use: a same-directory
    temp file + `os.replace`, so a process interrupted mid-write never
    leaves `path` torn."""
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


def declarations_generation(main_tex_bytes: bytes) -> int:
    """The `declarations` region's current `generation`, or 0 if the region
    is absent — absence is generation 0, never an error (design.md,
    `Products`)."""
    record = paper_region.read_region(main_tex_bytes, "declarations")
    if record is None:
        return 0
    return record["body"].get("generation", 0)


def read_provenance(main_tex_bytes: bytes) -> dict | None:
    """The raw `paper_region.read_region` result for the `provenance`
    region, or `None` if absent."""
    return paper_region.read_region(main_tex_bytes, "provenance")


def _verify_not_hand_edited(record: dict | None) -> None:
    if record is None:
        return
    actual = paper_region.current_digest(record["body_bytes"])
    if actual != record["digest"]:
        raise Refused(
            "PROVENANCE_HAND_EDITED",
            f"expected sha256={record['digest']}, found sha256={actual}",
        )


def record_write(
    tex_path: Path, block_id: str, contract_path: Path, *, clock=paper_region.default_clock,
) -> dict:
    """Persist a provenance record for `block_id`: the sha256 of
    `contract_path`'s bytes AS READ AT THIS MOMENT, and the `declarations`
    region's current generation. This baseline is persisted verbatim and
    never recomputed later (design.md, `A Provenance Record Is Written Only
    at substitute Time`).

    Called by `paper_block.substitute` AFTER its own 9-step block write has
    already succeeded — `tex_path` is read fresh here, so this sees that
    write's own bytes. Refuses `PROVENANCE_HAND_EDITED` (work-state) when
    the region's on-disk body no longer matches its own recorded digest;
    writes nothing in that case. There is no `--adopt` path for this
    region either, for the same reason `declarations` has none: a
    provenance record is authority the machine reads back, and adopting a
    hand edit would launder an unreviewed change into "what was recorded".
    """
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    pre = tex_path.read_bytes()
    record = read_provenance(pre)
    _verify_not_hand_edited(record)
    generation = declarations_generation(pre)

    body = record["body"] if record is not None else {"records": []}
    new_records = [entry for entry in body["records"] if entry["block"] != block_id]
    new_records.append({
        "block": block_id,
        "contract": str(contract_path),
        "contract_sha256": contract_sha256,
        "generation": generation,
        "written": clock(),
    })
    new_body = {"records": new_records}

    region_bytes, _digest = paper_region.build_region_bytes("provenance", new_body)
    existing_span = (
        {"begin_start": record["begin_start"], "end_end": record["end_end"]}
        if record is not None
        else None
    )
    candidate = paper_region.replace_or_append(pre, "provenance", region_bytes, existing_span)
    _atomic_replace(tex_path, candidate)

    return {
        "block": block_id,
        "contract": str(contract_path),
        "contract_sha256": contract_sha256,
        "generation": generation,
    }


def locate_contract(recorded: str | Path, sections_dir: Path | None) -> Path | None:
    """The contract file a provenance record names, in THIS workspace.

    `record_write` persists the path `substitute --contract` was given,
    which is absolute on the machine that wrote the block. A workspace that
    was cloned, moved or copied keeps that record, so the contract is looked
    up by its file name in the workspace's own `sections_dir` first, where
    every section contract lives; the recorded path is used only when
    `sections_dir` holds no file of that name. Returns `None` when the
    contract is found in neither place; a caller must then treat the block
    as not current, never read the missing path.
    """
    path = Path(recorded)
    if sections_dir is not None:
        local = Path(sections_dir) / path.name
        if local.is_file():
            return local
    return path if path.is_file() else None


def drift(main_tex_bytes: bytes, block_id: str, contract_path: Path) -> bool | None:
    """Whether `block_id`'s persisted contract digest still matches
    `contract_path`'s current bytes.

    Returns `None` when `block_id` has no provenance record at all —
    `unprovenanced`, a distinct, named state, never reported or treated as
    current (design.md, `A Block Written Without --contract Is
    unprovenanced`). Otherwise compares the CURRENT digest of
    `contract_path` against the PERSISTED write-time baseline — never
    against another freshly computed digest, which would make drift
    structurally undetectable (design.md, Mutation 3).
    """
    record = read_provenance(main_tex_bytes)
    if record is None:
        return None
    entry = next((r for r in record["body"]["records"] if r["block"] == block_id), None)
    if entry is None:
        return None
    current_digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    return current_digest != entry["contract_sha256"]
