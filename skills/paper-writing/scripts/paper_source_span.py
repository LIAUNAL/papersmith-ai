"""paper_source_span: a block's own resolved `(fact, lineage, title)`
bindings, turned into the bound section's own bytes (`transposition-fidelity`
spec, design.md Decision E).

This module never resolves lineage and never reads a revisions marker on its
own -- it CALLS `paper_graph.resolve_section_index`, the shipped per-
`(root, lineage)` chain `_verify_source_section_bindings` already reuses, and
adds only the byte slice. A second, independent resolution here is exactly
the defect this repository has already recorded under "fixed the instance,
never swept the class" (design.md, "Reconciling with the concurrent
change").

Public surface:

    resolve_bound_sections(corpus, qualified_block_id) -> tuple
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_declarations  # noqa: E402
import paper_graph  # noqa: E402


def resolve_bound_sections(corpus, qualified_block_id: str) -> tuple:
    """One entry per `(fact, lineage, title)` triple `qualified_block_id`'s
    own `BlockRecord.source_bindings` names, under a MEASURED,
    document-rooted root: `{"fact", "lineage", "title", "path",
    "byte_start", "byte_end", "text"}`. A block with no bindable measured
    fact returns `()` -- reported by the caller as `unmeasured`, never
    silently passed.

    Mirrors the same root/status guard `_verify_source_section_bindings`
    applies before ever calling `resolve_section_index` (an entry whose
    fact is not a key of `FACT_SOURCE_ROOT`, or whose root is reported
    `unmeasured`, is skipped rather than resolved) -- this function never
    invents a stricter or looser gate than the one `write`'s own corpus
    assembly already enforced for every binding it did resolve.

    `write`'s own gate (`_resolve_write_gate`, `enforce_bindings=True`)
    already raised `SECTION_NOT_IN_SOURCE`/`SECTION_TITLE_AMBIGUOUS` for
    every OTHER binding in the whole corpus before this function is ever
    called, so a title with any count other than exactly one here is
    skipped defensively rather than re-raised -- this module adds no
    refusal of its own (design.md, "Interfaces / Contracts"). A title
    resolves through `paper_graph.match_section_title`, the same lookup the
    gate used, so a `<title>#<n>` binding slices the occurrence it names.
    """
    record = corpus.blocks[qualified_block_id]
    resolved = []
    for fact_id, lineage, title in record.source_bindings:
        root = paper_declarations.FACT_SOURCE_ROOT.get(fact_id)
        if root is None:
            continue
        status = corpus.source_roots.get(root.name)
        if status is None or status["state"] == "unmeasured":
            continue

        revision_path, _counts, outline = paper_graph.resolve_section_index(
            corpus.source_roots, root, lineage,
        )
        matches = paper_graph.match_section_title(outline, title)
        if len(matches) != 1:
            continue

        (heading,) = matches
        body_bytes = revision_path.read_text(encoding="utf-8").encode("utf-8")
        text = body_bytes[heading["byte_start"]:heading["byte_end"]].decode("utf-8")
        resolved.append({
            "fact": fact_id,
            "lineage": lineage,
            "title": title,
            "path": str(revision_path),
            "byte_start": heading["byte_start"],
            "byte_end": heading["byte_end"],
            "text": text,
        })
    return tuple(resolved)
