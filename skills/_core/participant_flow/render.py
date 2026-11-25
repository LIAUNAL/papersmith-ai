"""Deterministic SVG of a valid participant flow (stdlib only).

Single stages run down a centre column with their exclusions in a side box,
the way the CONSORT, STROBE and STARD diagrams draw them; split stages draw
one column per branch with their reason groups inside the box. Stage bands
run down the left edge. Black on white, 11 px text at the smallest, every
operator string escaped. The caller checks the flow first: this module never
draws a flow ``model.check`` refuses.
"""

from __future__ import annotations

import html
import re
import textwrap

from .model import TEMPLATES, branch_labels, stage_chain

WIDTH = 880
CONTENT_LEFT, CONTENT_RIGHT = 56, 868
MAIN_X, MAIN_W = 150, 320
SIDE_X, SIDE_W = 520, 348
LINE, PAD, GAP, COLUMN_GAP = 15, 9, 30, 16
CHAR_W = 6.3  # average advance of an 11 px sans-serif glyph, generous for print
_HOLD = "\x07"  # not whitespace to textwrap; the checker refuses control characters in operator text


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _wrap(text: str, width: float, indent: int = 0) -> list[str]:
    """Wrap on spaces, never inside a ``(n = 12)`` count (held together by a placeholder)."""
    chars = max(12, int((width - 2 * PAD) / CHAR_W) - indent)
    held = re.sub(r"\(n = (\d+)\)", lambda m: f"(n{_HOLD}={_HOLD}{m.group(1)})", text)
    rows = textwrap.wrap(held, chars, break_long_words=True, break_on_hyphens=False) or [""]
    return [row.replace(_HOLD, " ") for row in rows]


class _Box:
    def __init__(self, x: float, y: float, w: float, lines: list[tuple[str, bool, int]]):
        self.x, self.y, self.w = x, y, w
        self.rows: list[tuple[str, bool, int]] = []
        for text, bold, indent in lines:
            for i, row in enumerate(_wrap(text, w, indent)):
                self.rows.append((row, bold, indent + (2 if i else 0)))
        self.h = LINE * len(self.rows) + 2 * PAD

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    def svg(self) -> str:
        out = [f'<rect x="{self.x:g}" y="{self.y:g}" width="{self.w:g}" height="{self.h:g}" '
               'fill="#ffffff" stroke="#000000" stroke-width="1"/>']
        for i, (row, bold, indent) in enumerate(self.rows):
            weight = ' font-weight="bold"' if bold else ""
            out.append(f'<text x="{self.x + PAD + indent * CHAR_W:g}" y="{self.y + PAD + 11 + LINE * i:g}" '
                       f'font-size="11"{weight}>{_esc(row)}</text>')
        return "".join(out)


def _arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    return (f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="#000000" '
            'stroke-width="1" marker-end="url(#arrow)"/>')


def _line(x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="#000000" stroke-width="1"/>'


def _group_lines(stage: dict, entry: dict) -> list[tuple[str, bool, int]]:
    lines: list[tuple[str, bool, int]] = []
    for group in stage.get("groups", []):
        value = entry[group["id"]]
        if group["effect"] == "partition":
            lines.append((f"{group['label']}:", False, 0))
            lines += [(f"{label} (n = {value[cid]})", False, 2) for cid, label in group["categories"]]
            continue
        total = sum(item["n"] for item in value)
        lines.append((f"{group['label']} (n = {total})", False, 0))
        lines += [(f"- {item['reason'].strip()} (n = {item['n']})", False, 2) for item in value]
        if group["effect"] == "note" and stage.get("remainder"):
            lines.insert(len(lines) - len(value) - 1, (f"{stage['remainder']} (n = {entry['n'] - total})", False, 0))
    return lines


def render_svg(flow: dict) -> str:
    tpl = TEMPLATES[flow["template"]]
    labels = branch_labels(tpl, flow)
    parts: list[str] = []
    bands: list[list] = []  # [name, top, bottom]
    y = 20.0
    previous: list[_Box] = []
    for stage in stage_chain(flow):
        body, top = stage["body"], y
        if not stage.get("split"):
            side_lines = _group_lines(stage, body)
            if side_lines:
                side = _Box(SIDE_X, y, SIDE_W, side_lines)
                parts.append(side.svg())
                parts.append(_arrow(MAIN_X + MAIN_W / 2, y + side.h / 2, SIDE_X, y + side.h / 2))
                y += side.h + GAP / 2
            box = _Box(MAIN_X, y, MAIN_W, [(f"{stage['label']} (n = {body['n']})", True, 0)])
            if previous:
                parts.append(_arrow(box.cx, previous[0].y + previous[0].h, box.cx, box.y))
            boxes = [box]
        else:
            names = list(labels)
            width = (CONTENT_RIGHT - CONTENT_LEFT - COLUMN_GAP * (len(names) - 1)) / len(names)
            basis = body.get("basis")
            boxes = []
            for i, name in enumerate(names):
                entry = body["branches"][name]
                title = stage["label"].format(branch=labels[name])
                if basis and basis != stage["basis_options"][0]:
                    title += f" (counted from {basis.replace('_', ' ')})"
                lines = [(f"{title} (n = {entry['n']})", True, 0)] + _group_lines(stage, entry)
                boxes.append(_Box(CONTENT_LEFT + i * (width + COLUMN_GAP), y + (GAP / 2 if len(previous) == 1 else 0),
                                  width, lines))
            height = max(box.h for box in boxes)
            for box in boxes:
                box.h = height
            if len(previous) == 1:
                bar = y
                parts.append(_line(previous[0].cx, previous[0].y + previous[0].h, previous[0].cx, bar))
                parts.append(_line(boxes[0].cx, bar, boxes[-1].cx, bar))
                parts += [_arrow(box.cx, bar, box.cx, box.y) for box in boxes]
            else:
                parts += [_arrow(box.cx, above.y + above.h, box.cx, box.y) for above, box in zip(previous, boxes)]
        parts += [box.svg() for box in boxes]
        bottom = max(box.y + box.h for box in boxes)
        if bands and bands[-1][0] == stage["band"]:
            bands[-1][2] = bottom
        else:
            bands.append([stage["band"], top, bottom])
        previous, y = boxes, bottom + GAP
    height = y - GAP + 20
    for name, top, bottom in bands:
        mid = (top + bottom) / 2
        parts.append(f'<rect x="12" y="{top:g}" width="30" height="{bottom - top:g}" fill="#e6e6e6" '
                     f'stroke="#000000" stroke-width="1"/><text x="27" y="{mid:g}" font-size="11" '
                     f'font-weight="bold" text-anchor="middle" dominant-baseline="middle" '
                     f'transform="rotate(-90 27 {mid:g})">{_esc(name)}</text>')
    title = f"Participant flow ({tpl['guideline']})"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height:g}" '
            f'viewBox="0 0 {WIDTH} {height:g}" font-family="Helvetica, Arial, sans-serif">'
            f'<title>{_esc(title)}</title>'
            '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z" fill="#000000"/></marker></defs>'
            f'<rect width="{WIDTH}" height="{height:g}" fill="#ffffff"/>{"".join(parts)}</svg>\n')
