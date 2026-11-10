"""svg_audit: the mechanical audit every figure SVG passes.

Spec S1 of `odd/tasks/spark-to-paper-enhancements.md`: figure quality without
external VLMs or paid image APIs — the audit is 100% Python stdlib and reads
only the SVG the producer wrote. It sits alongside the TeX+PDF auditor
`diagram_audit.py` (which needs a compile); an SVG is audited as authored.

Checks, each `pass` | `fail` | `unmeasured` (with a reason), mirroring
`diagram_audit.py`'s contract:

    font_range    the text sizes form a usable hierarchy: at most
                  MAX_HIERARCHY_LEVELS distinct sizes, and no size below
                  MIN_HIERARCHY_STEP x the largest (a caption at 1/3 of the
                  title is unreadable in print)
    text_overlap  no two positioned text spans intersect; spans inside
                  transforms or with multi-value x/y lists are excluded from
                  the measurable set (they are reported, never guessed)
    contrast      every text fill against the effective background reaches
                  MIN_CONTRAST (WCAG-style ratio); a gradient or `none`
                  fill is unmeasured, never a pass
    viewbox_fit   every positioned element stays inside the viewBox (a
                  diagram cut off at the page edge fails, like `margins`)

The overall verdict is `fail` when any check fails, `pass` when every check
passes, and `unmeasured` otherwise (a check that could not run is never a
pass).

Text extents are estimates: width = characters x font-size x
AVERAGE_GLYPH_EM (a core-14-like average advance) and height = font-size.
They are deliberately conservative for collisions (they only ever widen a
span) and are evidence in the report, not a print promise.

Public API:

    MIN_CONTRAST: float = 4.5
    audit_svg_text(svg_text) -> dict          (the report)
    audit_svg(path) -> dict
    failure_messages(report) -> list[str]
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

#: WCAG-style contrast ratio every text/background pair must reach.
MIN_CONTRAST = 4.5
#: Most distinct font sizes a legible hierarchy uses.
MAX_HIERARCHY_LEVELS = 4
#: Smallest size allowed relative to the largest (readability floor).
MIN_HIERARCHY_STEP = 0.4
#: Average glyph advance as a fraction of the font size (core-14-like).
AVERAGE_GLYPH_EM = 0.55
#: Penetration (user units) that counts as a collision.
COLLISION_TOLERANCE = 1.0
#: Content outside the viewBox beyond this is cut off when printed.
CLIP_TOLERANCE = 0.5
#: SVGNAMESPACE, without the boilerplate.
SVG_NS = "{http://www.w3.org/2000/svg}"

_LENGTH_RE = re.compile(r"^\s*(-?[\d.]+)\s*(px|pt|%)?\s*$")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "orange": (255, 165, 0),
    "purple": (128, 0, 128), "cyan": (0, 255, 255), "magenta": (255, 0, 255),
}


def _check(verdict: str, reason: str | None = None, **evidence) -> dict:
    return {"verdict": verdict, "reason": reason, **evidence}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_elements(root) -> list:
    """Every element that carries rendered text (`text`, `tspan`, `textArea`)."""
    found = []
    for element in root.iter():
        if _local(element.tag) in ("text", "tspan", "textArea"):
            found.append(element)
    return found


def _float_attr(element, name: str) -> float | None:
    raw = element.get(name)
    if raw is None:
        return None
    match = _LENGTH_RE.match(raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "%":  # percentages are relative to an unknown viewport box
        return None
    if unit == "pt":
        value *= 1.25  # CSS px equivalence, close enough for hierarchy checks
    return value


def _font_size(element, inherited: float | None) -> float | None:
    own = _float_attr(element, "font-size")
    if own is None:
        match = re.search(r"font-size\s*:\s*([\d.]+)\s*(px|pt)?", element.get("style", ""))
        if match:
            own = float(match.group(1)) * (1.25 if match.group(2) == "pt" else 1.0)
    return own if own is not None else inherited


def _fill(element) -> str | None:
    raw = element.get("fill")
    if raw is None:
        match = re.search(r"(?:^|;)\s*fill\s*:\s*([^;]+)", element.get("style", ""))
        raw = match.group(1).strip() if match else None
    return raw


def _parse_color(raw: str | None) -> tuple[int, int, int] | None:
    if not raw:
        return None
    value = raw.strip().lower()
    if _HEX_RE.match(value):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]
    match = re.match(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", value)
    if match:
        return tuple(int(part) for part in match.groups())
    return None  # gradients, currentColor, none: never guessed


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: float) -> float:
        value /= 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _background_color(root) -> tuple[int, int, int] | None:
    """The painted canvas: a root-level `rect` covering the viewBox, else white."""
    view = _viewbox(root)
    for element in root.iter():
        if _local(element.tag) != "rect":
            continue
        fill = _parse_color(_fill(element))
        if fill is None:
            continue
        x = _float_attr(element, "x") or 0.0
        y = _float_attr(element, "y") or 0.0
        w = _float_attr(element, "width") or 0.0
        h = _float_attr(element, "height") or 0.0
        if view and w >= view[2] * 0.95 and h >= view[3] * 0.95 and x <= view[0] and y <= view[1]:
            return fill
    return (255, 255, 255)  # SVG renders on white unless painted


def _viewbox(root) -> tuple[float, float, float, float] | None:
    raw = root.get("viewBox") or root.get("viewbox")
    if not raw:
        return None
    parts = [part for part in re.split(r"[,\s]+", raw.strip()) if part]
    if len(parts) != 4:
        return None
    try:
        return tuple(float(part) for part in parts)
    except ValueError:
        return None


def _span_box(element, size: float) -> tuple[float, float, float, float] | None:
    """(x, y, x2, y2) estimate, or None when the span is not measurable."""
    x, y = _float_attr(element, "x"), _float_attr(element, "y")
    if x is None or y is None:
        return None
    for multi in ("x", "y"):
        raw = element.get(multi)
        if raw and len(re.split(r"[,\s]+", raw.strip())) > 1:
            return None  # glyph-positioned text: extents not approximated
    text = "".join(element.itertext()).strip()
    width = max(len(text), 1) * size * AVERAGE_GLYPH_EM
    return (x, y - size, x + width, y + size * 0.3)


def _intersects(a, b, tol: float) -> bool:
    return (a[0] < b[2] - tol and b[0] < a[2] - tol
            and a[1] < b[3] - tol and b[1] < a[3] - tol)


def _hierarchy_check(texts: list[tuple[float, object]]) -> dict:
    sizes = sorted({round(size, 2) for size, _ in texts if size}, reverse=True)
    if not sizes:
        return _check("unmeasured", "NO_TEXT_SIZE", sizes=[])
    reasons = []
    if len(sizes) > MAX_HIERARCHY_LEVELS:
        reasons.append(f"HIERARCHY_TOO_DEEP({len(sizes)}>{MAX_HIERARCHY_LEVELS})")
    if sizes[-1] < sizes[0] * MIN_HIERARCHY_STEP:
        reasons.append(f"HIERARCHY_JUMP({sizes[-1]}<{MIN_HIERARCHY_STEP}x{sizes[0]})")
    return (_check("fail", "; ".join(reasons), sizes=sizes) if reasons
            else _check("pass", sizes=sizes))


def _overlap_check(spans: list[tuple[tuple[float, float, float, float], object]],
                   excluded: int) -> dict:
    collisions = []
    for i, (box_a, el_a) in enumerate(spans):
        for box_b, el_b in spans[i + 1:]:
            if _intersects(box_a, box_b, COLLISION_TOLERANCE):
                collisions.append({
                    "a": _label(el_a, box_a), "b": _label(el_b, box_b),
                })
    if collisions:
        return _check("fail", "TEXT_OVERLAP", collisions=collisions, excluded=excluded)
    if not spans:
        return _check("unmeasured", "NO_POSITIONED_TEXT" if not excluded
                      else "TEXT_INSIDE_TRANSFORMS", excluded=excluded)
    return _check("pass", pairs=len(spans) * (len(spans) - 1) // 2, excluded=excluded)


def _label(element, box) -> str:
    text = "".join(element.itertext()).strip()
    size = _font_size(element, None) or 0
    return f"{_local(element.tag)}@{box[0]:.0f},{box[1] + size:.0f}:{text[:24]}"


def _contrast_check(texts_with_fill, background) -> dict:
    if background is None:
        return _check("unmeasured", "NO_BACKGROUND")
    failures = []
    unmeasured = []
    for size, element in texts_with_fill:
        color = _parse_color(_fill(element))
        if color is None:
            unmeasured.append(_label(element, (0, 0, 0, 0)))
            continue
        ratio = _contrast_ratio(color, background)
        if ratio < MIN_CONTRAST:
            failures.append({"text": _label(element, (0, 0, 0, 0)),
                             "ratio": round(ratio, 2)})
    if failures:
        return _check("fail", "LOW_CONTRAST", failures=failures, unmeasured=len(unmeasured))
    if unmeasured:
        return _check("unmeasured", "UNMEASURABLE_FILL", unmeasured=len(unmeasured))
    if not texts_with_fill:
        return _check("unmeasured", "NO_TEXT")
    return _check("pass", threshold=MIN_CONTRAST, unmeasured=0)


def _viewbox_fit_check(root, positioned) -> dict:
    view = _viewbox(root)
    if not view:
        return _check("unmeasured", "NO_VIEWBOX")
    outside = []
    vx, vy, vw, vh = view
    for box in positioned:
        if box[0] < vx - CLIP_TOLERANCE or box[1] < vy - CLIP_TOLERANCE \
                or box[2] > vx + vw + CLIP_TOLERANCE or box[3] > vy + vh + CLIP_TOLERANCE:
            outside.append(box)
    if outside:
        return _check("fail", "CONTENT_OUTSIDE_VIEWBOX", count=len(outside))
    return _check("pass", viewbox=list(view))


def audit_svg_text(svg_text: str) -> dict:
    """Audit one SVG's text; never spawns a process, 100% stdlib."""
    checks: dict = {}
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as error:
        return {"verdict": "unmeasured", "reason": f"XML_PARSE_ERROR:{error}",
                "failures": [], "checks": {}}

    texts = []
    inherited = None
    for element in root.iter():
        if _local(element.tag) in ("text", "tspan", "textArea"):
            inherited = _font_size(element, inherited)
            texts.append((inherited, element))

    measurable = [(size, el) for size, el in texts if size]
    checks["font_range"] = _hierarchy_check(measurable)

    # Transform-free, positioned spans only: anything else is reported as
    # excluded evidence, never guessed.
    spans, excluded = [], 0
    for size, element in texts:
        if element.get("transform") is not None or size is None:
            excluded += 1
            continue
        box = _span_box(element, size)
        if box is None:
            excluded += 1
        else:
            spans.append((box, element))
    checks["text_overlap"] = _overlap_check(spans, excluded)
    checks["viewbox_fit"] = _viewbox_fit_check(
        root, [box for box, _ in spans])

    background = _background_color(root)
    checks["contrast"] = _contrast_check(texts, background)

    verdicts = [check["verdict"] for check in checks.values()]
    if "fail" in verdicts:
        verdict = "fail"
    elif all(value == "pass" for value in verdicts):
        verdict = "pass"
    else:
        verdict = "unmeasured"
    return {
        "verdict": verdict,
        "failures": [name for name, check in checks.items() if check["verdict"] == "fail"],
        "checks": checks,
    }


def audit_svg(path: Path) -> dict:
    """Audit the SVG file at `path` (read-only; the file is never rewritten)."""
    return audit_svg_text(Path(path).read_text(encoding="utf-8"))


def failure_messages(report: dict) -> list[str]:
    """One human-readable line per failed check (diagram_audit.failure_messages style)."""
    lines = []
    for name, check in (report.get("checks") or {}).items():
        if check.get("verdict") != "fail":
            continue
        reason = check.get("reason") or name
        lines.append(f"{name}: {reason}")
        for collision in check.get("collisions", []) or []:
            lines.append(f"  {collision['a']}  <->  {collision['b']}")
        for failure in check.get("failures", []) or []:
            if "ratio" in failure:
                lines.append(f"  {failure['text']}  contrast {failure['ratio']} < {MIN_CONTRAST}")
    return lines


def report_json(report: dict) -> str:
    """The report as stable JSON (CLI output)."""
    return json.dumps(report, indent=2, sort_keys=True)


assert math.isclose(_contrast_ratio((0, 0, 0), (255, 255, 255)), 21.0, rel_tol=1e-6)
