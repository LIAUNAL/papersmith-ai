import { describe, expect, it } from "vitest";
import {
  anchorAt,
  canvasRatio,
  clampPercent,
  CSS_UNITS,
  fitScale,
  layoutPages,
  PAGE_GAP,
  resolveScale,
  scrollTopFor,
  stepZoom,
  visiblePages,
  type PageSize,
} from "./layout.ts";

const letter: PageSize = { width: 612, height: 792 };
const pages = (count: number, size: PageSize = letter) => Array.from({ length: count }, () => size);

describe("layoutPages", () => {
  it("stacks pages with a gap and reports the total height and the widest page", () => {
    const layout = layoutPages([letter, { width: 400, height: 500 }, letter], 1, 10);
    expect(layout.boxes).toEqual([
      { top: 10, height: 792, width: 612 },
      { top: 812, height: 500, width: 400 },
      { top: 1322, height: 792, width: 612 },
    ]);
    expect(layout.height).toBe(2124);
    expect(layout.width).toBe(612);
  });

  it("scales every dimension but not the gap", () => {
    const layout = layoutPages(pages(2), 1.5, 10);
    expect(layout.boxes[0]).toEqual({ top: 10, height: 1188, width: 918 });
    expect(layout.boxes[1]?.top).toBe(10 + 1188 + 10);
  });

  it("is empty without pages", () => {
    expect(layoutPages([], 1, 10)).toEqual({ boxes: [], height: 10, width: 0 });
  });
});

describe("visiblePages", () => {
  const layout = layoutPages(pages(50), 1, 10);

  it("lists only the pages that intersect the viewport", () => {
    expect(visiblePages(layout, 0, 700, 0)).toEqual({ first: 0, last: 0 });
    expect(visiblePages(layout, 0, 900, 0)).toEqual({ first: 0, last: 1 });
    expect(visiblePages(layout, 802 * 3 + 10, 100, 0)).toEqual({ first: 3, last: 3 });
  });

  it("adds an overscan above and below, so the next pages are ready before they show", () => {
    expect(visiblePages(layout, 802 * 10 + 10, 700, 800)).toEqual({ first: 9, last: 11 });
  });

  it("keeps a 50-page document to a handful of rendered pages", () => {
    const range = visiblePages(layout, 802 * 25, 900, 900)!;
    expect(range.last - range.first + 1).toBeLessThanOrEqual(5);
    expect(range.first).toBeGreaterThan(20);
  });

  it("clamps to the document and handles an empty one", () => {
    expect(visiblePages(layout, 1_000_000, 700, 0)).toEqual({ first: 49, last: 49 });
    expect(visiblePages(layoutPages([], 1, 10), 0, 700, 0)).toBeNull();
  });
});

describe("anchors", () => {
  const layout = layoutPages(pages(5), 1, 10);

  it("describes a position as a page and the fraction of the page above the viewport top", () => {
    expect(anchorAt(layout, 0)).toEqual({ page: 0, offset: 0 });
    expect(anchorAt(layout, 10 + 396)).toEqual({ page: 0, offset: 0.5 });
    expect(anchorAt(layout, 812 + 198)).toEqual({ page: 1, offset: 0.25 });
  });

  it("anchors a position in the gap to the top of the next page", () => {
    expect(anchorAt(layout, 805)).toEqual({ page: 1, offset: 0 });
  });

  it("anchors a position below the last page to the end of the last page", () => {
    expect(anchorAt(layout, 99_999)).toEqual({ page: 4, offset: 1 });
  });

  it("converts back to the same scroll position at the same zoom", () => {
    for (const scrollTop of [0, 5, 123, 812, 1500, 3000]) {
      expect(scrollTopFor(layout, anchorAt(layout, scrollTop))).toBeCloseTo(scrollTop < 10 ? 10 : scrollTop, 6);
    }
  });

  it("keeps the same place in the document when the zoom changes", () => {
    const anchor = anchorAt(layout, 812 + 198);
    const zoomed = layoutPages(pages(5), 2, 10);
    expect(scrollTopFor(zoomed, anchor)).toBe(10 + 1584 + 10 + 0.25 * 1584);
  });

  it("falls back to the top for an anchor outside the document", () => {
    expect(scrollTopFor(layout, { page: 40, offset: 0.3 })).toBe(scrollTopFor(layout, { page: 4, offset: 0.3 }));
    expect(scrollTopFor(layoutPages([], 1, 10), { page: 2, offset: 0.5 })).toBe(0);
  });
});

describe("zoom", () => {
  it("converts a percentage to a render scale where 100 percent is the CSS size of the page", () => {
    expect(resolveScale({ mode: "percent", percent: 100 }, 800, [letter])).toBeCloseTo(CSS_UNITS, 10);
    expect(resolveScale({ mode: "percent", percent: 150 }, 800, [letter])).toBeCloseTo(1.5 * CSS_UNITS, 10);
  });

  it("fits the widest page to the width, minus the side padding", () => {
    expect(fitScale(1000, [letter, { width: 800, height: 600 }], 20)).toBeCloseTo(960 / 800, 10);
    expect(resolveScale({ mode: "fit" }, 1000, [letter, { width: 800, height: 600 }])).toBeCloseTo((1000 - 2 * PAGE_GAP) / 800, 10);
  });

  it("keeps fit sane for a container that has no width yet and for an empty document", () => {
    expect(fitScale(0, [letter], 20)).toBeGreaterThan(0);
    expect(fitScale(800, [], 20)).toBeGreaterThan(0);
  });

  it("steps through fixed levels and stops at the ends", () => {
    expect(stepZoom(100, "in")).toBe(125);
    expect(stepZoom(100, "out")).toBe(75);
    expect(stepZoom(137, "in")).toBe(150);
    expect(stepZoom(137, "out")).toBe(125);
    expect(stepZoom(400, "in")).toBe(400);
    expect(stepZoom(50, "out")).toBe(50);
  });

  it("clamps a percentage to the supported range and rounds it", () => {
    expect(clampPercent(10)).toBe(50);
    expect(clampPercent(900)).toBe(400);
    expect(clampPercent(149.6)).toBe(150);
    expect(clampPercent(Number.NaN)).toBe(100);
  });
});

describe("canvasRatio", () => {
  it("uses the device ratio up to 2", () => {
    expect(canvasRatio(800, 1000, 1)).toBe(1);
    expect(canvasRatio(800, 1000, 1.5)).toBe(1.5);
    expect(canvasRatio(800, 1000, 3)).toBe(2);
    expect(canvasRatio(800, 1000, 0)).toBe(1);
  });

  it("lowers the ratio so a very large page stays under the pixel budget", () => {
    const ratio = canvasRatio(4000, 5000, 2);
    expect(ratio).toBeLessThan(1);
    expect(4000 * ratio * 5000 * ratio).toBeLessThanOrEqual(16_000_000 + 1);
  });
});
