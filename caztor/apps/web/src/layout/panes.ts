export const PANE_IDS = ["files", "editor", "preview", "chat"] as const;
export type PaneId = (typeof PANE_IDS)[number];

/** Sizes in percent of the workspace width, keyed by pane id. */
export type PaneLayout = Record<PaneId, number>;

export interface PaneSpec {
  id: PaneId;
  title: string;
  /** Percent of the width when no layout was saved. */
  defaultPercent: number;
  /** Smallest width in pixels the pane may be dragged to. */
  minWidth: number;
}

/** Fixed order, left to right. The panes cannot be reordered. */
export const PANES: readonly PaneSpec[] = [
  { id: "files", title: "Files", defaultPercent: 15, minWidth: 160 },
  { id: "editor", title: "LaTeX editor", defaultPercent: 35, minWidth: 280 },
  { id: "preview", title: "PDF preview", defaultPercent: 30, minWidth: 280 },
  { id: "chat", title: "Chat", defaultPercent: 20, minWidth: 300 },
];

export const DEFAULT_LAYOUT: PaneLayout = { files: 15, editor: 35, preview: 30, chat: 20 };

/** Allowed distance of the total from 100, for rounding in saved values. */
const TOTAL_TOLERANCE = 1;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * A saved layout is usable only when it has exactly the four panes, every size is a finite positive number and the
 * sizes fill the container. Pixel minimums are not checked here: they depend on the window, and the pane library
 * clamps a layout to them when it is applied.
 */
export function parseLayout(value: unknown): PaneLayout | null {
  if (!isRecord(value)) return null;
  const keys = Object.keys(value);
  if (keys.length !== PANES.length || !PANES.every((pane) => keys.includes(pane.id))) return null;
  const layout = {} as PaneLayout;
  let total = 0;
  for (const pane of PANES) {
    const size = value[pane.id];
    if (typeof size !== "number" || !Number.isFinite(size) || size <= 0) return null;
    layout[pane.id] = size;
    total += size;
  }
  return Math.abs(total - 100) <= TOTAL_TOLERANCE ? layout : null;
}
