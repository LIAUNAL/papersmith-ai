"""geometry: connected ink regions, bounding boxes, out-of-bounds,
overlap and canvas occupancy -- computed in pure Python, no numpy or
scipy (design.md, Decision 1: "the expensive step is connected-component
labelling, which numpy does not provide -- scipy.ndimage.label does, and
scipy is neither declared nor installed").

No `subprocess` here; this module never spawns a process and never reads
a repair-budget ledger.

One threshold, 8-connectivity, both recorded by every caller that builds
a finding (design.md, Decision 6): `INK_MAX_LEVEL = 200` on the 0-255
grayscale scale separates the two populations it must -- anti-aliasing
halo at a stroke's edge lands ~230-254 (outside ink), a deliberate light
TikZ fill such as `fill=black!25` renders at level ~=191 (inside ink).
8-connectivity, because 4-connectivity fragments an anti-aliased
diagonal stroke into many mutually-overlapping components, which would
report a false `overlap: fail` on a single clean arrow.
"""
from __future__ import annotations

INK_MAX_LEVEL = 200
CONNECTIVITY = 8


def _ink_runs(width: int, height: int, gray, ink_max: int = INK_MAX_LEVEL) -> list:
    """Per row, the half-open `[start, end)` column ranges of contiguous
    ink pixels. Index `[row]` holds that row's list of runs."""
    row_runs = []
    for y in range(height):
        runs = []
        offset = y * width
        x = 0
        while x < width:
            if gray[offset + x] <= ink_max:
                start = x
                while x < width and gray[offset + x] <= ink_max:
                    x += 1
                runs.append((start, x))
            else:
                x += 1
        row_runs.append(runs)
    return row_runs


def ink_regions(width: int, height: int, gray, *, ink_max: int = INK_MAX_LEVEL) -> list:
    """Connected ink regions as half-open pixel bounding boxes
    `(x0, y0, x1, y1)`, via run-length row union-find under
    8-connectivity: two runs on adjacent rows connect whenever their
    column ranges overlap OR touch diagonally (`a0 <= b1 and b0 <= a1`
    on half-open intervals includes the diagonal-touch case).

    A region wholly inside another region's box (the label inside a framed
    node) is dropped (`drop_contained`): it can never be a visible
    collision, and reporting it made every framed node a false overlap."""
    row_runs = _ink_runs(width, height, gray, ink_max)

    parent: list = []

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    row_ids = []
    for runs in row_runs:
        ids_for_row = []
        for _ in runs:
            idx = len(parent)
            parent.append(idx)
            ids_for_row.append(idx)
        row_ids.append(ids_for_row)

    for y in range(1, height):
        for i, (s, e) in enumerate(row_runs[y]):
            for j, (ps, pe) in enumerate(row_runs[y - 1]):
                if s <= pe and ps <= e:
                    union(row_ids[y][i], row_ids[y - 1][j])

    boxes: dict = {}
    for y, runs in enumerate(row_runs):
        for i, (s, e) in enumerate(runs):
            root = find(row_ids[y][i])
            box = boxes.get(root)
            if box is None:
                boxes[root] = [s, y, e, y + 1]
            else:
                box[0] = min(box[0], s)
                box[1] = min(box[1], y)
                box[2] = max(box[2], e)
                box[3] = max(box[3], y + 1)
    return drop_contained([tuple(box) for box in boxes.values()])


def drop_contained(boxes: list) -> list:
    """`boxes` without every box that lies wholly inside another one (edges
    may coincide). A framed node's border is one connected region and the
    text inside it is another; the text's box sits inside the frame's box,
    which is containment, not a collision, so it never reaches `overlaps`.
    Of two identical boxes one is kept. Order is preserved."""
    kept = []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        inside = False
        for j, (X0, Y0, X1, Y1) in enumerate(boxes):
            if i == j or not (X0 <= x0 and Y0 <= y0 and x1 <= X1 and y1 <= Y1):
                continue
            if (X0, Y0, X1, Y1) != (x0, y0, x1, y1) or j < i:
                inside = True
                break
        if not inside:
            kept.append((x0, y0, x1, y1))
    return kept


def out_of_bounds(width: int, height: int, gray, *, ink_max: int = INK_MAX_LEVEL) -> dict:
    """`figure-raster` spec, `Requirement: Out-of-Bounds Ink Is a
    Computed Verdict`: the outermost pixel band is exactly one pixel
    wide -- rows `y == 0` / `y == height - 1`, columns `x == 0` /
    `x == width - 1`. Ink one pixel further inward is never counted.
    This function computes the pure pixel fact; the border precondition
    (Decision 8: no verdict at all without a declared border) is
    `findings.py`'s to apply."""
    edges: dict = {}

    top = sum(1 for x in range(width) if gray[x] <= ink_max)
    bottom = sum(1 for x in range(width) if gray[(height - 1) * width + x] <= ink_max)
    left = sum(1 for y in range(height) if gray[y * width] <= ink_max)
    right = sum(1 for y in range(height) if gray[y * width + (width - 1)] <= ink_max)

    if top:
        edges["top"] = top
    if bottom:
        edges["bottom"] = bottom
    if left:
        edges["left"] = left
    if right:
        edges["right"] = right

    return {"verdict": "fail" if edges else "pass", "edges": edges}


def overlaps(boxes: list) -> list:
    """`figure-raster` spec, `Requirement: Ink-Region Overlap Is a
    Computed Verdict, Reported Unnamed`: STRICT half-open intersection.
    Two boxes sharing only a boundary edge, with zero interior
    penetration, are never reported as overlapping."""
    collisions = []
    for i in range(len(boxes)):
        ax0, ay0, ax1, ay1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            bx0, by0, bx1, by1 = boxes[j]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                collisions.append({"boxes": [list(boxes[i]), list(boxes[j])]})
    return collisions


def occupancy(width: int, height: int, gray, *, bands: int = 4, ink_max: int = INK_MAX_LEVEL) -> list:
    """`figure-raster` spec, `Requirement: Canvas Occupancy Is Evidence,
    Never a Verdict`: the non-background pixel fraction per horizontal
    band, as plain numbers -- this function never attaches a verdict."""
    fractions = []
    for i in range(bands):
        y0 = i * height // bands
        y1 = (i + 1) * height // bands
        total = (y1 - y0) * width
        if total == 0:
            fractions.append(0.0)
            continue
        ink = 0
        for y in range(y0, y1):
            offset = y * width
            for x in range(width):
                if gray[offset + x] <= ink_max:
                    ink += 1
        fractions.append(round(ink / total, 4))
    return fractions
