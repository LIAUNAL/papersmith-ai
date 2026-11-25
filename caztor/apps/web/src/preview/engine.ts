import type { PageSize } from "./layout.ts";

/** A drawing in progress. `done` rejects when it was cancelled or failed. */
export interface RenderTask {
  done: Promise<void>;
  cancel(): void;
}

/** A loaded PDF. The pages are drawn on demand, so a long document costs nothing until it is scrolled to. */
export interface PdfDocument {
  /** Size of every page in points, in page order. */
  readonly pageSizes: readonly PageSize[];
  /** Draws page `index` (zero-based) onto `canvas` so that one point covers `scale` canvas pixels. */
  render(index: number, canvas: HTMLCanvasElement, scale: number): RenderTask;
  /** Lays the selectable text of page `index` into `container`, one point per `scale` CSS pixels. Optional: without it no text can be selected. */
  renderText?(index: number, container: HTMLElement, scale: number): RenderTask;
  /** The text of page `index`, its pieces joined by spaces as the text layer lays them. Optional. */
  pageText?(index: number): Promise<string>;
  /** Frees the document. Nothing may be drawn afterwards. */
  destroy(): void;
}

/** The PDF library behind a seam, so the preview's behavior is tested without it. */
export interface PdfEngine {
  open(bytes: Uint8Array): Promise<PdfDocument>;
}
