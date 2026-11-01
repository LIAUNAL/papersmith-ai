"""findings: assembles the full `visual` dict from
`skills/_core/figure/figure_dimensions.py`'s roster, populating every
dimension from what `geometry.py` actually computed, plus the border
precondition (design.md, Decision 8) and the provenance every finding
must carry.

No `subprocess` here; this module never spawns a process and never
reads a repair-budget ledger.

The border precondition, read locally. `figure-review` reads `<id>.tex`
beside `<id>.pdf` with its own minimal `\\documentclass[...]` regex --
deliberately NOT importing `paper_tikz` (`skills/paper-writing/scripts/
paper_tikz.py`'s `_DOCUMENTCLASS_RE`/`STANDALONE_HEADER`), because that
would couple this skill to `paper-writing`'s import graph in the
direction design.md forbids ("Never an edge: figure-review --X-->
paper-writing"). The duplicated regex is a LaTeX fact, not a
paper-writing one, and is a handful of lines.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geometry  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "figure"))
import figure_dimensions  # noqa: E402

#: A locally-owned duplicate of paper_tikz's `_DOCUMENTCLASS_RE` shape --
#: a LaTeX fact this skill reads independently, never imported.
_DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[(?P<options>[^\]]*)\])?\{(?P<cls>[^}]*)\}")
_BORDER_RE = re.compile(r"\bborder\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*pt")


def border_pt_from_tex(tex_path: Path) -> float | None:
    """The declared `border=<N>pt` value from `<id>.tex`'s own
    `\\documentclass[...]{standalone}` header, or `None` when no border
    is declared, the file cannot be read, or the header is unparseable
    (design.md, Decision 8: "no border declared, or the header is
    unparseable -> out-of-bounds is unmeasured, reason
    NO_DECLARED_BORDER, and declaredBorderPt is recorded as null")."""
    try:
        text = Path(tex_path).read_text(encoding="utf-8")
    except OSError:
        return None
    match = _DOCUMENTCLASS_RE.search(text)
    if match is None:
        return None
    options = match.group("options") or ""
    border_match = _BORDER_RE.search(options)
    if border_match is None:
        return None
    return float(border_match.group(1))


def _point_box(box, pt_per_px: float | None) -> list | None:
    if pt_per_px is None:
        return None
    return [round(value * pt_per_px, 2) for value in box]


def build_visual(
    *, width: int, height: int, gray, tool: str, dpi, dpi_source: str,
    color_model: str, declared_border_pt: float | None, boxes: list | None = None,
    vector: dict | None = None,
) -> dict:
    """Assemble the full `visual` dict: every roster dimension present
    exactly once (`visual-finding-boundary`, `Requirement: Every
    Dimension Is Always Present, Never Absent or Null`), Tier 1 verdicts
    and evidence computed from `gray`, Tier 2 silences left at the
    roster's default reason.

    `boxes` lets a caller supply already-known ink regions directly
    (used by tests exercising the exact overlap boundary on a raster
    where painting two adjacent boxes merges them into one connected
    region); when omitted, regions are detected from `gray` via
    `geometry.ink_regions`.

    `vector` carries the PDF-read verdicts (`typeset.measure_pdf`:
    `min-printed-font`, `background`, `whitespace`, `in-figure-title`);
    when omitted they stay `unmeasured` with the roster's
    `PDF_NOT_MEASURED`, the way the raster dimensions do without a raster.
    """
    dimensions = {
        name: {"verdict": "unmeasured", "reason": figure_dimensions.DEFAULT_REASONS[name]}
        for name in figure_dimensions.SILENT_DIMENSIONS
    }
    for name in ("min-printed-font", "background", "whitespace", "in-figure-title"):
        dimensions[name] = (vector or {}).get(name) or {
            "verdict": "unmeasured", "reason": figure_dimensions.DEFAULT_REASONS[name],
        }

    oob = geometry.out_of_bounds(width, height, gray)
    if declared_border_pt is None:
        dimensions["out-of-bounds"] = {
            "verdict": "unmeasured", "reason": "NO_DECLARED_BORDER", "edges": {},
        }
    else:
        dimensions["out-of-bounds"] = {
            "verdict": oob["verdict"], "reason": None, "edges": oob["edges"],
        }

    ink_boxes = list(boxes) if boxes is not None else geometry.ink_regions(width, height, gray)
    collisions = geometry.overlaps(ink_boxes)
    pt_per_px = 72.0 / dpi if dpi else None
    formatted_collisions = [
        {
            "pixel": [list(pair[0]), list(pair[1])],
            "point": [_point_box(pair[0], pt_per_px), _point_box(pair[1], pt_per_px)],
        }
        for pair in (collision["boxes"] for collision in collisions)
    ]
    dimensions["overlap"] = {
        "verdict": "fail" if formatted_collisions else "pass",
        "reason": None,
        "collisions": formatted_collisions,
    }

    dimensions["canvas-occupancy"] = {
        "verdict": None, "reason": None,
        "bands": geometry.occupancy(width, height, gray),
    }

    provenance = {
        "tool": tool, "dpi": dpi, "dpiSource": dpi_source,
        "colorModel": color_model, "inkMaxLevel": geometry.INK_MAX_LEVEL,
        "connectivity": geometry.CONNECTIVITY, "pixelWidth": width,
        "pixelHeight": height, "ptPerPx": pt_per_px,
        "declaredBorderPt": declared_border_pt,
    }
    return {"provenance": provenance, "dimensions": dimensions}


def measure_figure(
    png_path: Path, raster_provenance: dict, *, tex_path: Path | None = None,
    vector: dict | None = None,
) -> dict:
    """The end-to-end entry point `review_cli.py measure` calls:
    `png_read` -> `geometry` -> this module's assembly, using the
    already-written `raster-provenance.json` for `tool`/`dpi`/
    `dpiSource`/`colorModel` (`raster.py`'s own header peek already reads
    the real colour model, never the requested `-gray` flag)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import png_read

    width, height, gray = png_read.read_gray(png_path)
    declared_border_pt = border_pt_from_tex(tex_path) if tex_path is not None else None
    return build_visual(
        width=width, height=height, gray=gray,
        tool=raster_provenance.get("tool"),
        dpi=raster_provenance.get("dpi"),
        dpi_source=raster_provenance.get("dpiSource"),
        color_model=raster_provenance.get("colorModel"),
        declared_border_pt=declared_border_pt,
        vector=vector,
    )
