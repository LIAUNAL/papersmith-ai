"""figure-review geometry: a region wholly inside another region's box (the
label inside a framed node) is containment, not an overlap (spec S1 of
`odd/tasks/figure-and-table-quality.md`). Regions that merely intersect are
still reported."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEOMETRY = REPO / "skills" / "figure-review" / "scripts" / "geometry.py"


def _geometry():
    spec = importlib.util.spec_from_file_location("figure_review_geometry_containment", GEOMETRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canvas(width: int, height: int):
    return width, height, [255] * (width * height)


def _paint(canvas, x0: int, y0: int, x1: int, y1: int) -> None:
    width, _, gray = canvas
    for y in range(y0, y1):
        for x in range(x0, x1):
            gray[y * width + x] = 0


def _frame(canvas, x0: int, y0: int, x1: int, y1: int) -> None:
    _paint(canvas, x0, y0, x1, y0 + 1)
    _paint(canvas, x0, y1 - 1, x1, y1)
    _paint(canvas, x0, y0, x0 + 1, y1)
    _paint(canvas, x1 - 1, y0, x1, y1)


class ContainmentTests(unittest.TestCase):

    def test_text_inside_a_framed_node_is_not_an_overlap(self) -> None:
        geometry = _geometry()
        canvas = _canvas(24, 14)
        _frame(canvas, 1, 1, 22, 13)        # the node's border
        _paint(canvas, 5, 5, 8, 9)          # a glyph inside it
        _paint(canvas, 11, 5, 15, 9)        # another glyph
        regions = geometry.ink_regions(*canvas)
        self.assertEqual(regions, [(1, 1, 22, 13)])
        self.assertEqual(geometry.overlaps(regions), [])

    def test_regions_that_only_intersect_still_overlap(self) -> None:
        """Two separate L-shaped strokes whose boxes interpenetrate, neither
        inside the other: the collision the check exists for."""
        geometry = _geometry()
        canvas = _canvas(24, 24)
        _paint(canvas, 2, 2, 14, 3)
        _paint(canvas, 2, 2, 3, 14)          # L one: box (2, 2, 14, 14)
        _paint(canvas, 8, 20, 21, 21)
        _paint(canvas, 20, 8, 21, 21)        # L two: box (8, 8, 21, 21)
        regions = geometry.ink_regions(*canvas)
        self.assertEqual(sorted(regions), [(2, 2, 14, 14), (8, 8, 21, 21)])
        self.assertEqual(len(geometry.overlaps(regions)), 1)

    def test_drop_contained_keeps_one_of_two_identical_boxes_and_the_order(self) -> None:
        geometry = _geometry()
        boxes = [(0, 0, 4, 4), (10, 0, 14, 4), (0, 0, 4, 4), (1, 1, 2, 2)]
        self.assertEqual(geometry.drop_contained(boxes), [(0, 0, 4, 4), (10, 0, 14, 4)])


if __name__ == "__main__":
    unittest.main()
