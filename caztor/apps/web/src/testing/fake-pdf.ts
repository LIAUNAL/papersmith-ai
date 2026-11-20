import type { PdfDocument, PdfEngine, RenderTask } from "../preview/engine.ts";
import type { PageSize } from "../preview/layout.ts";

export interface FakeDocument extends PdfDocument {
  /** Which version of the document this is, written onto every canvas it draws. */
  readonly label: string;
  /** Pages drawn so far, in order, as `index@scale`. */
  readonly drawn: string[];
  destroyed: boolean;
  /** Holds every drawing until `releaseDrawings` is called, to look at the screen while a reload is in progress. */
  hold: boolean;
  releaseDrawings(): void;
}

/** A document of `count` pages that "draws" by labelling the canvas. Drawings finish on the next microtask unless held. */
export function fakeDocument(label: string, count: number, size: PageSize = { width: 600, height: 800 }): FakeDocument {
  const waiting: Array<() => void> = [];
  const doc: FakeDocument = {
    label,
    drawn: [],
    destroyed: false,
    hold: false,
    pageSizes: Array.from({ length: count }, () => size),
    releaseDrawings() {
      doc.hold = false;
      waiting.splice(0).forEach((release) => release());
    },
    render(index, canvas, scale): RenderTask {
      let cancelled = false;
      const done = (async () => {
        if (doc.hold) await new Promise<void>((resolve) => waiting.push(resolve));
        else await Promise.resolve();
        if (cancelled) throw new Error("cancelled");
        canvas.dataset["label"] = label;
        canvas.dataset["page"] = String(index);
        doc.drawn.push(`${index}@${scale.toFixed(3)}`);
      })();
      done.catch(() => {});
      return { done, cancel: () => void (cancelled = true) };
    },
    destroy: () => void (doc.destroyed = true),
  };
  return doc;
}

/** An engine that returns the prepared documents in order, one per `open`, and records the bytes it was given. */
export function fakeEngine(...documents: FakeDocument[]): PdfEngine & { opened: Uint8Array[]; fail: Error | null } {
  const queue = [...documents];
  const engine = {
    opened: [] as Uint8Array[],
    fail: null as Error | null,
    async open(bytes: Uint8Array): Promise<PdfDocument> {
      engine.opened.push(bytes);
      if (engine.fail !== null) throw engine.fail;
      const next = queue.shift();
      if (next === undefined) throw new Error("no document prepared");
      return next;
    },
  };
  return engine;
}
