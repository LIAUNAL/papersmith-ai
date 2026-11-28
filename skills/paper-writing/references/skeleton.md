## Opening the empty skeleton: `skeleton`

Before any block can be written, every section/block id the manuscript will
carry must exist, empty, in `paper/main.tex` — `skeleton` builds exactly
that, and only that: it opens each non-excluded id through the existing
`open_block` writer alone, in `derive_order` order, and writes no content.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py skeleton \
    --related-work yes --dataset-in materials --frame
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `skeleton --related-work yes\|no --dataset-in materials\|experimental-setup [--frame] [--sections <dir>] [--paper <dir>]` | Opens every `sections/*.md` block id the two answers imply, empty, skipping ids already opened. With `--frame`, then writes the canonical document frame around the blocks (below); on a paper that already has blocks, `--frame` alone (no answers) only frames | `SKELETON_ANSWER_REQUIRED`, `SKELETON_ALREADY_DECIDED`, `DATASET_PLACEMENT_CONFLICT`; with `--frame`, `FRAME_OUTSIDE_TEXT`, `FRAME_BLOCK_CARRIES_HEADING`, `FRAME_BLOCK_UNDECLARED` |

**Two structural decisions, asked exactly once.** Whether the manuscript
carries a dedicated Related Work section, and whether the dataset is
described in Materials and Methods or in Experimental Setup, are answered
by `--related-work`/`--dataset-in` the first time any block is opened.
Neither flag given refuses `SKELETON_ANSWER_REQUIRED`, naming which is
missing.

**Every later call infers both decisions from disk, never from a stored
flag and never from an agent's own memory.** Once any corpus block is
already opened, `skeleton` re-derives both answers straight from the
opened block ids themselves (`paper_declarations.infer_skeleton_decisions`)
and compares them against whatever was given: a contradiction refuses
`SKELETON_ALREADY_DECIDED`, naming both what disk already records and what
was requested. Opening both `mm-dataset` and `es-dataset` at once is a
genuine conflict the inference cannot resolve one way — it refuses
`DATASET_PLACEMENT_CONFLICT` rather than silently picking a winner.
Already-opened ids are skipped, so a repeated `skeleton` call with the same
answers is idempotent.

**The document frame: `skeleton --frame`.** Without the flag `skeleton`
writes through `open_block` alone and the file holds markers only, which no
venue build can typeset. `--frame` writes, once, the frame every later stage
reads (`paper_frame.py`): the canonical review preamble (`article`, one
column, English, `natbib`; empty `\title`/`\author`/`\date` defaults the
title block overrides), `\begin{document}`, the title block, `\maketitle`,
the abstract blocks inside `\begin{abstract}`, the keywords block, then one
`\section{<Title>}\label{sec:<id>}` line per body section OUTSIDE the
blocks, right before that section's first block, `\section*{Back matter}`
before the declarations (the AI-use declaration last),
`\bibliographystyle{unsrtnat}` and `\bibliography{refs}`, the appendices,
and `\end{document}`; the `declarations`/`provenance` regions follow
unchanged. Sections follow the contracts' `position` and each section's
blocks the header's own block order, never `order`'s writing order, which
interleaves sections. Each title is the contract's `# ` heading (a
`(<kind> line)` suffix dropped). Only blocks already in `main.tex` are placed:
a section with none (Related Work under `--related-work no`) gets no heading.

An existing paper whose blocks were opened without a frame obtains it the
same way, `skeleton --frame`: every block moves whole, its body and digest
unchanged (proven in memory before the write, which keeps the one-deep
pre-image). A file that already has a `\begin{document}` outside the blocks
is left alone. The frame refuses, writing nothing:
`FRAME_OUTSIDE_TEXT` when the frameless file holds text outside every block
and region (it cannot know where that text goes), `FRAME_BLOCK_CARRIES_HEADING`
when a body block carries its own `\section` line — the refusal names every
such block; rewrite each without the heading (moving the line out would
change the block's bytes and digest), then frame — and
`FRAME_BLOCK_UNDECLARED` for a block no contract declares. Blocks opened after
the frame need `open --after <id>`; `--at-end` would land after
`\end{document}`.
