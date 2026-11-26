"""paper_frame: the canonical document frame of `paper/main.tex`.

`scaffold` writes an empty `main.tex` and `skeleton` opens block markers only,
so nothing wrote the frame everything downstream reads: `venue build` takes
"the canonical preamble minus the packages the class owns" and each section's
heading from the `\\section` line before its first block; `verify`'s
`back-matter-order` needs a reference list. This module writes it, once, and
is the one writer besides `scaffold` that adds bytes outside every block
(`odd/tasks/paper-frame-venue-front-matter.md`, S2):

    <PREAMBLE>                       (\\documentclass ... \\title/\\author/\\date defaults)
    \\begin{document}
    <title-and-keywords.title>       the title block sets \\title and \\author
    \\maketitle
    \\begin{abstract}
    <abstract.*>
    \\end{abstract}
    <title-and-keywords.keywords>    the rest of the title section
    \\section{<Title>}\\label{sec:<id>}   one per body section, OUTSIDE the blocks
    <that section's blocks>
    ...
    \\section*{Back matter}
    <back-matter declarations>       the AI-use declaration last
    \\bibliographystyle{unsrtnat}
    \\bibliography{refs}
    <back-matter appendices>
    \\end{document}
    <declarations / provenance regions, unchanged>

Sections follow the contracts' document order (`position`) and each section's
blocks the header's own block order, never `derive_order`: that is the order
blocks can be WRITTEN in, and it interleaves sections (the introduction's
block-2 waits on the methods' proposal). Titles come from each contract's
`# ` heading (a `(<kind> line)` suffix dropped), never a per-paper list. Only
blocks already in `main.tex` are placed; a section with none gets no heading.

`frame_paper` frames a FRAMELESS file only: one whose bytes outside every
block and region are blank. Blocks move whole and byte for byte, so no body
and no digest changes (`_prove_preserving`), and the write reuses
`paper_block.commit_candidate` (the `TEX_MOVED` compare-and-swap, the one-deep
pre-image, the atomic replace). A file with a non-comment `\\begin{document}`
outside the blocks already has its frame and is left alone.

Refusals, every one before a byte is written:

- `FRAME_OUTSIDE_TEXT`: text outside every block and region, but no frame;
  the engine cannot know where that text belongs.
- `FRAME_BLOCK_CARRIES_HEADING`: a body block carries its own `\\section`
  line; framing would print the heading twice. The block is rewritten first
  (moving the line out would change the block's bytes and digest).
- `FRAME_BLOCK_UNDECLARED`: a block the section contracts do not declare;
  there is no place to put it.

`heading_lines` is shared with `write` (`DRAFT_SECTION_HEADING`): a body
block never carries a `\\section{` or `\\section*{` line; only back-matter
blocks may, since the venue can give a declaration (or an appendix) a section
of its own (`sections/10-back-matter.md`, "Placement follows the venue").
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_contract  # noqa: E402
import paper_region  # noqa: E402
import paper_verify  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

TITLE_SECTION = "title-and-keywords"
ABSTRACT_SECTION = "abstract"
BACK_SECTION = "back-matter"
AI_USE_BLOCK = f"{BACK_SECTION}.bm-ai-use-declaration"

#: The canonical review layout (`SKILL.md`, "Format and Review Presentation
#: Mode"): one column, 1.5 spacing, English. `\\title`, `\\author` and
#: `\\date` are empty defaults the title block overrides, so `\\maketitle`
#: compiles before the title is written; `venue build` drops all three.
PREAMBLE = (
    "\\documentclass[11pt,onecolumn,a4paper]{article}\n"
    "\\usepackage[utf8]{inputenc}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage[english]{babel}\n"
    "\\usepackage[margin=2.5cm]{geometry}\n"
    "\\usepackage{setspace}\n"
    "\\usepackage{amsmath}\n"
    "\\usepackage{amssymb}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{booktabs}\n"
    "\\usepackage[numbers,sort&compress,square]{natbib}\n"
    "\\usepackage{xurl}\n"
    "\\usepackage[hidelinks]{hyperref}\n"
    "\\onehalfspacing\n"
    "\\title{}\n"
    "\\author{}\n"
    "\\date{}\n"
)
BACK_MATTER_HEADING = "\\section*{Back matter}"
BIBLIOGRAPHY = "\\bibliographystyle{unsrtnat}\n\\bibliography{refs}\n"

_TITLE_RE = re.compile(r"^# (?P<title>.+?)\s*$", re.MULTILINE)
_LINE_SUFFIX_RE = re.compile(r"\s*\([^()]*\bline\)$")
_HEADING_RE = re.compile(r"\\section\*?\s*[\[{]")
_BEGIN_DOCUMENT_RE = re.compile(rb"^[ \t]*\\begin\{document\}", re.MULTILINE)


def section_title(body: str, section_id: str) -> str:
    """The contract's first `# ` heading, its `(<kind> line)` suffix dropped;
    without one, the id in title case (the fallback `venue build` uses)."""
    found = _TITLE_RE.search(body)
    if found:
        return _LINE_SUFFIX_RE.sub("", found.group("title")).strip()
    return section_id.replace("-", " ").title()


def read_layout(sections_dir: Path) -> list:
    """Every `NN-*.md` contract as `{section, position, title, blocks}`, in
    document order (`position`, then file name); `blocks` are qualified ids in
    the header's own order."""
    layout = []
    for path in sorted(sections_dir.glob("[0-9][0-9]-*.md")):
        header, body = paper_contract.parse(path.read_bytes())
        layout.append({
            "section": header.section, "position": header.position, "file": path.name,
            "title": section_title(body.decode("utf-8", errors="replace"), header.section),
            "blocks": [f"{header.section}.{block['id']}" for block in header.blocks],
        })
    layout.sort(key=lambda item: (item["position"], item["file"]))
    return layout


def heading_lines(block_id: str, latex: str) -> list:
    """`[(line number, line)]` for every `\\section{`/`\\section*{` a block
    body carries outside a comment; always empty for a back-matter block."""
    if block_id.split(".", 1)[0] == BACK_SECTION:
        return []
    hits = []
    for number, line in enumerate(latex.splitlines(), start=1):
        code = re.split(r"(?<!\\)%", line, maxsplit=1)[0]
        if _HEADING_RE.search(code):
            hits.append((number, line.strip()))
    return hits


def has_frame(data: bytes) -> bool:
    """A non-comment `\\begin{document}` line outside every block."""
    return bool(_BEGIN_DOCUMENT_RE.search(paper_block.project(data)))


def _region_spans(data: bytes) -> list:
    spans = []
    for kind in paper_region.KINDS:
        found = paper_region.find_region(data, kind)
        if found is not None:
            spans.append((found["begin_start"], found["end_end"]))
    return sorted(spans)


def _region_bytes(data: bytes) -> list:
    """The declarations/provenance region pairs, byte for byte, in file order."""
    return [data[start:end] for start, end in _region_spans(data)]


def _with_newline(chunk: bytes) -> bytes:
    return chunk if chunk.endswith(b"\n") else chunk + b"\n"


def _check_outside(data: bytes, parsed) -> None:
    spans = sorted([(b["start"], e["end"]) for b, e in parsed.pairs.values()] + _region_spans(data))
    cursor, lines = 0, []
    for start, end in spans + [(len(data), len(data))]:
        for offset, line in enumerate(data[cursor:start].split(b"\n")):
            if line.strip():
                lines.append(data.count(b"\n", 0, cursor) + offset + 1)
        cursor = max(cursor, end)
    if lines:
        shown = ", ".join(f"line {number}" for number in lines[:5])
        raise Refused(
            "FRAME_OUTSIDE_TEXT",
            f"main.tex holds text outside every block ({shown}) but no \\begin{{document}}; the frame "
            "cannot tell where that text belongs. Move it into a block or remove it, then frame",
        )


def build_frame(data: bytes, layout: list) -> bytes:
    """Pure: the framed candidate for the frameless `data`. Never touches disk."""
    parsed = paper_block.parse(data)
    declared = {block_id for section in layout for block_id in section["blocks"]}
    undeclared = sorted(set(parsed.pairs) - declared)
    if undeclared:
        raise Refused(
            "FRAME_BLOCK_UNDECLARED",
            f"no section contract declares {undeclared}; the frame has no place for them",
        )
    regions = {block_id: _with_newline(data[begin["start"]:end["end"]])
               for block_id, (begin, end) in parsed.pairs.items()}
    carrying = []
    for block_id, (begin, end) in parsed.pairs.items():
        hits = heading_lines(block_id, data[begin["end"]:end["start"]].decode("utf-8"))
        if hits:
            carrying.append(f"{block_id} (line {hits[0][0]} of its body: {hits[0][1][:60]!r})")
    if carrying:
        raise Refused(
            "FRAME_BLOCK_CARRIES_HEADING",
            f"these body blocks carry their own section heading: {'; '.join(sorted(carrying))}. The "
            "frame writes every body heading outside the blocks; rewrite each block without it, then frame",
        )
    _check_outside(data, parsed)

    by_section = {item["section"]: [b for b in item["blocks"] if b in regions] for item in layout}
    out = [PREAMBLE.encode("utf-8"), b"\\begin{document}\n"]
    title_blocks = by_section.get(TITLE_SECTION, [])
    out += [regions[b] for b in title_blocks[:1]]
    out.append(b"\\maketitle\n")
    abstract = by_section.get(ABSTRACT_SECTION, [])
    if abstract:
        out += [b"\\begin{abstract}\n", *(regions[b] for b in abstract), b"\\end{abstract}\n"]
    out += [regions[b] for b in title_blocks[1:]]
    for item in layout:
        if item["section"] in (TITLE_SECTION, ABSTRACT_SECTION, BACK_SECTION):
            continue
        blocks = by_section[item["section"]]
        if blocks:
            heading = f"\n\\section{{{item['title']}}}\\label{{sec:{item['section']}}}\n"
            out += [heading.encode("utf-8"), *(regions[b] for b in blocks)]
    back = by_section.get(BACK_SECTION, [])
    appendices = [b for b in back if b in paper_verify.APPENDIX_BLOCKS]
    declarations = ([b for b in back if b not in appendices and b != AI_USE_BLOCK]
                    + [b for b in back if b == AI_USE_BLOCK])
    if declarations:
        out += [f"\n{BACK_MATTER_HEADING}\n".encode("utf-8"), *(regions[b] for b in declarations)]
    out += [b"\n", BIBLIOGRAPHY.encode("utf-8"), *(regions[b] for b in appendices), b"\\end{document}\n"]
    out += [_with_newline(region) for region in _region_bytes(data)]
    return b"".join(out)


def _blocks(data: bytes) -> dict:
    return {block_id: (begin["digest"], data[begin["end"]:end["start"]])
            for block_id, (begin, end) in paper_block.parse(data).pairs.items()}


def _prove_preserving(pre: bytes, candidate: bytes) -> None:
    """Every block keeps its body and recorded digest, and every region pair
    its bytes; `SUBSTITUTION_NOT_LOCAL` otherwise (a defect, never ordinary
    use)."""
    if _blocks(pre) != _blocks(candidate) or _region_bytes(pre) != _region_bytes(candidate):
        raise Refused("SUBSTITUTION_NOT_LOCAL", "the frame would change a block's or a region's bytes")


def frame_paper(paper_dir: Path, sections_dir: Path) -> dict:
    """Write the canonical frame around `<paper_dir>/main.tex`'s blocks, or
    report it already present (nothing written)."""
    tex_path = paper_block.resolve_main_tex(paper_dir)
    pre = tex_path.read_bytes()
    if has_frame(pre):
        return {"framed": False, "frame": "present"}
    layout = read_layout(sections_dir)
    candidate = build_frame(pre, layout)
    _prove_preserving(pre, candidate)
    paper_block.commit_candidate(paper_dir, tex_path, pre, candidate)
    headings = [line.decode("utf-8") for line in paper_block.project(candidate).splitlines()
                if line.startswith(b"\\section")]
    return {"framed": True, "frame": "written", "headings": headings,
            "blocks": len(paper_block.parse(candidate).pairs)}
