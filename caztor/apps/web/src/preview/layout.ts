/** A page size in PDF points. */
export interface PageSize {
  width: number;
  height: number;
}

/** Where a page sits in the scrolling column, in CSS pixels. */
export interface PageBox {
  top: number;
  height: number;
  width: number;
}

export interface PageLayout {
  boxes: PageBox[];
  /** Total height of the column, including the gaps. */
  height: number;
  /** Width of the widest page. */
  width: number;
}

/** A place in the document that survives a change of zoom or a new version of the document. */
export interface Anchor {
  /** Zero-based page index. */
  page: number;
  /** How far into the page the viewport top is, from 0 (top) to 1 (bottom). */
  offset: number;
}

export type Zoom = { mode: "fit" } | { mode: "percent"; percent: number };

/** Gap between pages, and the side margin used by fit-to-width, in CSS pixels. */
export const PAGE_GAP = 12;

/** PDF points to CSS pixels: 100 percent shows a page at the size it has at 96 dpi. */
export const CSS_UNITS = 96 / 72;

export const MIN_PERCENT = 50;
export const MAX_PERCENT = 400;
export const ZOOM_LEVELS: readonly number[] = [50, 75, 100, 125, 150, 200, 300, 400];
export const DEFAULT_ZOOM: Zoom = { mode: "fit" };

/** Stacks the pages in one column at `scale` (CSS pixels per point). */
export function layoutPages(sizes: readonly PageSize[], scale: number, gap: number = PAGE_GAP): PageLayout {
  const boxes: PageBox[] = [];
  let top = gap;
  let width = 0;
  for (const size of sizes) {
    const box = { top, height: size.height * scale, width: size.width * scale };
    boxes.push(box);
    top += box.height + gap;
    width = Math.max(width, box.width);
  }
  return { boxes, height: top, width };
}

/**
 * The pages worth rendering for a viewport: those that intersect it, widened by `overscan` pixels on both sides.
 * Null for a document without pages. A position beyond the end selects the last page.
 */
export function visiblePages(layout: PageLayout, scrollTop: number, viewportHeight: number, overscan: number): { first: number; last: number } | null {
  const count = layout.boxes.length;
  if (count === 0) return null;
  const from = scrollTop - overscan;
  const to = scrollTop + viewportHeight + overscan;
  let first = -1;
  let last = -1;
  layout.boxes.forEach((box, index) => {
    if (box.top + box.height < from || box.top > to) return;
    if (first === -1) first = index;
    last = index;
  });
  return first === -1 ? { first: count - 1, last: count - 1 } : { first, last };
}

/** The place in the document at the top of the viewport. */
export function anchorAt(layout: PageLayout, scrollTop: number): Anchor {
  const count = layout.boxes.length;
  for (let index = 0; index < count; index += 1) {
    const box = layout.boxes[index];
    if (box === undefined || scrollTop >= box.top + box.height) continue;
    return { page: index, offset: scrollTop <= box.top ? 0 : (scrollTop - box.top) / box.height };
  }
  return { page: Math.max(count - 1, 0), offset: count === 0 ? 0 : 1 };
}

/** The scroll position that puts `anchor` at the top of the viewport. An anchor beyond the document is moved to its last page. */
export function scrollTopFor(layout: PageLayout, anchor: Anchor): number {
  if (layout.boxes.length === 0) return 0;
  const box = layout.boxes[Math.min(Math.max(anchor.page, 0), layout.boxes.length - 1)];
  return box === undefined ? 0 : box.top + Math.min(Math.max(anchor.offset, 0), 1) * box.height;
}

/** The scale at which the widest page fills the width, leaving `padding` on each side. */
export function fitScale(containerWidth: number, sizes: readonly PageSize[], padding: number): number {
  const widest = Math.max(0, ...sizes.map((size) => size.width));
  if (widest === 0) return CSS_UNITS;
  const available = containerWidth - 2 * padding;
  return available > 0 ? available / widest : CSS_UNITS;
}

export function clampPercent(percent: number): number {
  if (!Number.isFinite(percent)) return 100;
  return Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, Math.round(percent)));
}

/** The next fixed zoom level above or below `percent`. */
export function stepZoom(percent: number, direction: "in" | "out"): number {
  const levels = ZOOM_LEVELS;
  const next = direction === "in" ? levels.find((level) => level > percent) : [...levels].reverse().find((level) => level < percent);
  return next ?? (direction === "in" ? MAX_PERCENT : MIN_PERCENT);
}

/** CSS pixels per point for a zoom setting. */
export function resolveScale(zoom: Zoom, containerWidth: number, sizes: readonly PageSize[]): number {
  return zoom.mode === "fit" ? fitScale(containerWidth, sizes, PAGE_GAP) : (clampPercent(zoom.percent) / 100) * CSS_UNITS;
}

/** The percentage shown for a scale. */
export function percentOf(scale: number): number {
  return Math.round((scale / CSS_UNITS) * 100);
}

/** The most pixels one page canvas may hold, and the sharpest ratio worth drawing. */
const MAX_CANVAS_PIXELS = 16_000_000;
const MAX_PIXEL_RATIO = 2;

/** Canvas pixels per CSS pixel for a page of `width` x `height` CSS pixels: sharp on dense screens, bounded in memory. */
export function canvasRatio(width: number, height: number, devicePixelRatio: number): number {
  const wanted = Math.min(Math.max(devicePixelRatio || 1, 1), MAX_PIXEL_RATIO);
  const area = width * height;
  return area <= 0 ? wanted : Math.min(wanted, Math.sqrt(MAX_CANVAS_PIXELS / area));
}
