---
name: pixelrag
description: "Trigger: a paper is already ingested (`/paper-ingestion`) and its figures must become evidence a later session can read and cite, not opaque image files (`/pixelrag <ingested paper folder>`). Keyless and local: calls no model and no network. `facts` reports what can be computed about an extracted figure (path, sha256, pixel size, page, the caption and figure number the ingested Markdown gives it, the text ingestion extracted around it); the session's own agent looks at the image and writes what is visible (axes, units, trends, panels, never speculation); `record` validates that description against the facts and stores it beside the image as `<image>.pixelrag.json` with its provenance, optionally as a marked block under the image in the Markdown; `status` lists figures whose description is current, missing or stale. Never edits an image, never invents a number the image does not show."
---

# pixelrag

`paper-ingestion` writes a paper's figures as image files the Markdown
references, and stops there: a figure enters the pipeline as a filename and
nothing downstream can read, cite or reason about what it shows. This skill
turns each extracted figure into a description usable as evidence.

## Keyless and local

`paper-ingestion` is deliberately local and keyless, and this skill keeps that
constraint (decision L8 of #13): no API key, no network, no model call from the
CLI. The description is written by the session's own agent, which can look at
an image; the CLI is what makes that description evidence. It computes the
deterministic facts, refuses a description that contradicts them or that
speculates, binds the description to the exact image bytes by sha256, and
stores it with its provenance. A description recorded by pixelrag is always an
agent's reading of the picture, never the authors' text, and every place it is
stored says so.

## When to use it

After `/paper-ingestion` has produced `guidance/<topic>/<paper>/` (the PDF, its
`.md`, its `.json` page map and the figure images). It runs as a separate pass
over an already-ingested paper, never during ingestion: ingestion stays a
transactional, model-free conversion, and a figure can be described (or
described again) at any later time without re-ingesting.

## Usage

```
python skills/pixelrag/scripts/pixelrag_cli.py status --paper guidance/<topic>/<paper>
python skills/pixelrag/scripts/pixelrag_cli.py facts  --figure guidance/<topic>/<paper>/<image>
python skills/pixelrag/scripts/pixelrag_cli.py record --figure guidance/<topic>/<paper>/<image> \
    --sha256 <sha256 from facts> --description "<text>" | --description @<file> [--markdown]
```

Standard library only. Every call prints exactly one JSON object on stdout.

## The agent workflow

1. `status --paper <folder>` lists every figure the Markdown references, each
   `current`, `missing` or `stale` (its image changed since the description
   was recorded), and whether its Markdown block is `current`, `stale` or
   `absent`.
2. For each `missing` or `stale` figure, run `facts --figure <image>`. Read the
   caption, the figure number and the nearby text it reports.
3. Look at the image itself (read the file). Write a description that states
   only what is visible: the kind of chart, each axis with its label and
   units, the scale and range, the series and legend, the panels and their
   letters, the trends and where they change, values printed in the figure.
   No speculation, no interpretation of what the result means, no claim the
   image does not show. Refer to the figure only by the number its caption
   gives, or not at all.
4. `record --figure <image> --sha256 <the sha256 facts reported> --description
   <text>` (or `@file`). Add `--markdown` to also write the block into the
   ingested Markdown. Re-running with the same description is a no-op.

## Facts

`facts` reports: `path` (relative to the working directory), `sha256`,
`bytes`, `format`, `width` and `height` in pixels (read from the PNG, JPEG or
GIF header; `null` when the header is not one it reads), `markdown`, `page`
(from the `<!-- page N -->` markers), `caption`, `label` and `number` (the
`Figure N` / `Fig. N` paragraph right after or before the image reference,
else the image's alt text; `null` when there is none), `nearby_text`
(`before`/`after`: the closest body paragraphs on the same page, clipped to
600 characters), and `text_layer` (`available`, the page's `route` and
`engine` from the `.json` map, and a `note`). `in_image_text` is always
`null`: pixelrag runs no OCR, so text drawn inside the image is read by the
agent looking at it, and the output says so.

## Storage, and why

- **Beside the image, always:** `<image>.pixelrag.json` holds `{image, sha256,
  facts, description, recorded_at, tool: "pixelrag"}`. This is the source of
  truth. It travels with the image, it is bound to the exact bytes it
  describes (so a re-extracted image reads as `stale` instead of silently
  inheriting a description of a different picture), and it leaves the
  ingested Markdown byte-for-byte as ingestion wrote it.
- **In the Markdown, on request (`--markdown`):** a block delimited by
  `<!-- pixelrag:begin <image> sha256=<16 hex> -->` and
  `<!-- pixelrag:end <image> -->`, right under the image reference, quoted and
  labelled as the agent's description. It exists so a reader of the `.md`
  (and `pdf_fragment.py --search`) meets the description where the figure is.
  Writing it is idempotent: the same description changes nothing, a new one
  replaces the block in place. Because the `.json` page map indexes the
  Markdown by character offset, `record` shifts every offset after the block
  so `pdf_fragment.py` keeps answering with the right text. It is opt-in
  because it edits a file another skill wrote.

## Refusals

Exit code 2, `{"ok": false, "error": CODE, "message": ...}`; nothing is written.

| Code | When |
| --- | --- |
| `FIGURE_NOT_FOUND` | `--figure` is not a file |
| `NOT_AN_IMAGE` | the file is not `.png`, `.jpg`, `.jpeg`, `.gif` or `.webp` |
| `NOT_INGESTED` | no ingested Markdown in the image's folder references it (or `--paper` holds no `<folder>.md`) |
| `PAPER_NOT_FOUND` | `--paper` is not a folder |
| `IMAGE_CHANGED` | the image's sha256 is not the one `--sha256` names: it changed since `facts`; look again |
| `DESCRIPTION_EMPTY` | the description is blank |
| `DESCRIPTION_TOO_SHORT` | under 40 characters |
| `DESCRIPTION_TOO_LONG` | over 4000 characters |
| `DESCRIPTION_MARKUP` | it contains `<!--`, `-->` or `![`, which would corrupt the Markdown's page and figure markers |
| `DESCRIPTION_SPECULATIVE` | it hedges or interprets (`probably`, `likely`, `might`, `suggests`, `seems`, ...) |
| `FIGURE_NUMBER_MISMATCH` | it names a figure number other than the one the caption gives |
| `DESCRIPTION_UNREADABLE` | `--description @file` cannot be read |
| `USAGE` | a missing or unknown argument |
| `PYTHON_VERSION_UNSUPPORTED` | the interpreter is older than 3.11 |

## What it never does

It never edits or re-encodes an image, never calls a model or the network,
never writes a description itself, and never touches a paper that is not
ingested.
