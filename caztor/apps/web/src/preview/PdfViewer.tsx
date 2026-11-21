import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PdfSelection } from "../embed/bridge.ts";
import type { PassageFocus } from "../explain/focus.ts";
import { findPrinted } from "../explain/passages.ts";
import type { PdfDocument } from "./engine.ts";
import { anchorAt, canvasRatio, layoutPages, PAGE_GAP, percentOf, resolveScale, scrollTopFor, visiblePages, type Anchor, type Zoom } from "./layout.ts";
import "./PdfViewer.css";

interface PdfViewerProps {
  document: PdfDocument;
  zoom: Zoom;
  /** Where to open. Afterwards the viewer keeps its own position, across new versions of the document and zoom changes. */
  anchor: Anchor;
  /** Called on every scroll with the place at the top of the viewport. */
  onViewChange: (view: { anchor: Anchor; zoom: Zoom }) => void;
  /** Called when the page scale changes, with the zoom it amounts to in percent (this is how "fit width" becomes a number). */
  onScaleChange?: (percent: number) => void;
  /** Called with the text selected in the pages. When set, the pages carry a selectable text layer. */
  onTextSelected?: (selection: PdfSelection) => void;
  /** Passages to mark in soft yellow wherever a page shows them. When set, the pages carry a text layer. */
  highlights?: readonly string[];
  /** The explained passage to scroll to, once per nonce. */
  focus?: PassageFocus | null;
  /** Texts a double click in the source names, narrowest first: the first a page prints is brought into view and marked for a moment. */
  jump?: SourceJump | null;
}

/** What a double click in the source asks the PDF to show, once per nonce. */
export interface SourceJump {
  candidates: readonly string[];
  nonce: number;
}

/** How long the mark of a jump stays on the page. */
const JUMP_MARK_MS = 1600;

/** Whether `text` holds `passage`, as written or as LaTeX prints it. */
const holds = (text: string, passage: string): boolean => findPrinted(text, passage).length > 0;

/**
 * Marks the text pieces of one page that hold a passage, as written or as LaTeX prints it; clears the others. Each
 * marked piece names, in `data-explained`, the passages it belongs to, so a step can find one passage's pieces.
 */
function markPassages(layer: HTMLElement, passages: readonly string[]): void {
  const pieces = [...layer.querySelectorAll<HTMLElement>("span")].filter((span) => !span.classList.contains("markedContent"));
  for (const piece of pieces) {
    piece.classList.remove("pdf-viewer__explained");
    delete piece.dataset["explained"];
  }
  if (passages.length === 0 || pieces.length === 0) return;
  const starts: number[] = [];
  let joined = "";
  for (const piece of pieces) {
    starts.push(joined.length);
    joined += `${piece.textContent ?? ""} `;
  }
  passages.forEach((passage, which) => {
    for (const range of findPrinted(joined, passage)) {
      pieces.forEach((piece, at) => {
        const start = starts[at]!;
        const end = start + (piece.textContent ?? "").length;
        if (start >= range.to || end <= range.from) return;
        piece.classList.add("pdf-viewer__explained");
        piece.dataset["explained"] = `${piece.dataset["explained"] ?? ""} ${which} `;
      });
    }
  });
}

/** The text pieces of a page's text layer that print `passage`. */
function piecesPrinting(layer: Element, passage: string): HTMLElement[] {
  const pieces = [...layer.querySelectorAll<HTMLElement>("span")].filter((span) => !span.classList.contains("markedContent"));
  const starts: number[] = [];
  let joined = "";
  for (const piece of pieces) {
    starts.push(joined.length);
    joined += `${piece.textContent ?? ""} `;
  }
  const ranges = findPrinted(joined, passage);
  return pieces.filter((piece, at) => {
    const start = starts[at]!;
    const end = start + (piece.textContent ?? "").length;
    return ranges.some((range) => start < range.to && end > range.from);
  });
}

/** Used until the container has been measured (and in environments without layout). */
const FALLBACK_SIZE = { width: 800, height: 600 };

/** One page: the canvas is drawn off-screen and swapped in when ready, so a redraw never shows a blank page. */
function PageCanvas({ document: pdf, index, scale, cssWidth, cssHeight }: { document: PdfDocument; index: number; scale: number; cssWidth: number; cssHeight: number }) {
  const holder = useRef<HTMLDivElement>(null);
  const ratio = canvasRatio(cssWidth, cssHeight, window.devicePixelRatio);

  useEffect(() => {
    const target = holder.current;
    if (target === null) return;
    const canvas = window.document.createElement("canvas");
    canvas.className = "pdf-viewer__canvas";
    const task = pdf.render(index, canvas, scale * ratio);
    let live = true;
    task.done.then(
      () => {
        if (live) target.replaceChildren(canvas);
      },
      () => {
        // Cancelled by a newer drawing, or the page could not be drawn: the previous bitmap stays.
      },
    );
    return () => {
      live = false;
      task.cancel();
    };
  }, [pdf, index, scale, ratio]);

  return <div ref={holder} className="pdf-viewer__bitmap" />;
}

/** The selectable text of one page, laid over its bitmap, with the explained passages marked. */
function PageText({ document: pdf, index, scale, passages }: { document: PdfDocument; index: number; scale: number; passages: readonly string[] }) {
  const holder = useRef<HTMLDivElement>(null);
  const [drawn, setDrawn] = useState(0);
  useEffect(() => {
    const target = holder.current;
    if (target === null || pdf.renderText === undefined) return;
    const task = pdf.renderText(index, target, scale);
    let live = true;
    task.done.then(
      () => live && setDrawn((count) => count + 1),
      () => {},
    );
    return () => {
      live = false;
      task.cancel();
    };
  }, [pdf, index, scale]);
  const wanted = passages.join("\n");
  useEffect(() => {
    if (holder.current !== null) markPassages(holder.current, wanted === "" ? [] : wanted.split("\n"));
  }, [drawn, wanted]);
  return <div ref={holder} className="textLayer pdf-viewer__text" />;
}

/** The pages of a PDF in one scrolling column. Only the pages near the viewport are drawn. */
export function PdfViewer({ document: pdf, zoom, anchor, onViewChange, onScaleChange, onTextSelected, highlights, focus, jump }: PdfViewerProps) {
  const withText = onTextSelected !== undefined || highlights !== undefined || jump !== undefined;
  const scroller = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(FALLBACK_SIZE);
  const [scrollTop, setScrollTop] = useState(0);
  const place = useRef(anchor);
  const report = useRef(onViewChange);
  report.current = onViewChange;

  const scale = resolveScale(zoom, size.width, pdf.pageSizes);
  const layout = useMemo(() => layoutPages(pdf.pageSizes, scale), [pdf, scale]);
  const scaleReport = useRef(onScaleChange);
  scaleReport.current = onScaleChange;
  useEffect(() => scaleReport.current?.(percentOf(scale)), [scale]);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (element === null) return;
    const measure = () => {
      const width = element.clientWidth || FALLBACK_SIZE.width;
      const height = element.clientHeight || FALLBACK_SIZE.height;
      setSize((current) => (current.width === width && current.height === height ? current : { width, height }));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A new document or a new scale changes the heights: put the same place in the document back at the top.
  useLayoutEffect(() => {
    const element = scroller.current;
    if (element === null) return;
    element.scrollTop = scrollTopFor(layout, place.current);
    setScrollTop(element.scrollTop);
  }, [layout]);

  function onScroll(): void {
    const element = scroller.current;
    if (element === null) return;
    setScrollTop(element.scrollTop);
    place.current = anchorAt(layout, element.scrollTop);
    report.current({ anchor: place.current, zoom });
  }

  function onMouseUp(): void {
    if (onTextSelected === undefined) return;
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? "";
    if (selection === null || text === "" || selection.anchorNode === null) return;
    const node = selection.anchorNode;
    const element = node instanceof Element ? node : node.parentElement;
    const page = element?.closest("[data-page]");
    if (page === null || page === undefined || scroller.current?.contains(page) !== true) return;
    onTextSelected({ text, page: Number(page.getAttribute("data-page")) });
  }

  // A step to an explained passage: find its page from the pages' text (drawn or not), scroll there, then centre the
  // marked pieces once that page's text layer is in.
  const texts = useRef<{ of: PdfDocument; pages: Map<number, Promise<string>> } | null>(null);
  const layoutNow = useRef(layout);
  layoutNow.current = layout;
  useEffect(() => {
    const element = scroller.current;
    if (focus === null || focus === undefined || element === null || pdf.pageText === undefined) return;
    if (texts.current?.of !== pdf) texts.current = { of: pdf, pages: new Map() };
    const cache = texts.current.pages;
    const which = (highlights ?? []).indexOf(focus.passage);
    const clearCurrent = () => {
      for (const old of element.querySelectorAll(".pdf-viewer__explained--current")) old.classList.remove("pdf-viewer__explained--current");
    };
    // A step leaves no stronger mark behind, also when the PDF does not print its passage.
    clearCurrent();
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    void (async () => {
      for (let index = 0; index < pdf.pageSizes.length && live; index += 1) {
        if (!cache.has(index)) cache.set(index, pdf.pageText!(index).catch(() => ""));
        if (!holds(await cache.get(index)!, focus.passage)) continue;
        if (!live) return;
        const box = layoutNow.current.boxes[index];
        if (box !== undefined) element.scrollTop = Math.max(0, box.top - PAGE_GAP);
        let tries = 0;
        const centre = () => {
          if (!live) return;
          const page = element.querySelector(`[data-page="${index + 1}"]`);
          const pieces = [...(page?.querySelectorAll<HTMLElement>(".pdf-viewer__explained") ?? [])].filter((piece) => which < 0 || (piece.dataset["explained"] ?? "").includes(` ${which} `));
          clearCurrent();
          if (pieces.length > 0) {
            for (const piece of pieces) piece.classList.add("pdf-viewer__explained--current");
            const first = pieces[0]!;
            element.scrollTop += first.getBoundingClientRect().top - element.getBoundingClientRect().top - element.clientHeight / 3;
          } else if ((tries += 1) < 80) timer = setTimeout(centre, 100);
        };
        timer = setTimeout(centre, 50);
        return;
      }
    })();
    return () => {
      live = false;
      if (timer !== undefined) clearTimeout(timer);
    };
    // Only a new step moves the view; new highlights alone do not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce, pdf]);

  // A double click in the source: the narrowest candidate a page prints, on the first page that prints it.
  useEffect(() => {
    const element = scroller.current;
    if (jump === null || jump === undefined || element === null || pdf.pageText === undefined) return;
    if (texts.current?.of !== pdf) texts.current = { of: pdf, pages: new Map() };
    const cache = texts.current.pages;
    const clear = () => {
      for (const old of element.querySelectorAll(".pdf-viewer__jump")) old.classList.remove("pdf-viewer__jump");
    };
    clear();
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    void (async () => {
      for (const candidate of jump.candidates) {
        for (let index = 0; index < pdf.pageSizes.length && live; index += 1) {
          if (!cache.has(index)) cache.set(index, pdf.pageText!(index).catch(() => ""));
          if (!holds(await cache.get(index)!, candidate)) continue;
          if (!live) return;
          const box = layoutNow.current.boxes[index];
          if (box !== undefined) element.scrollTop = Math.max(0, box.top - PAGE_GAP);
          let tries = 0;
          const mark = () => {
            if (!live) return;
            const layer = element.querySelector(`[data-page="${index + 1}"] .pdf-viewer__text`);
            const pieces = layer === null ? [] : piecesPrinting(layer, candidate);
            if (pieces.length === 0) {
              if ((tries += 1) < 80) timer = setTimeout(mark, 100);
              return;
            }
            for (const piece of pieces) piece.classList.add("pdf-viewer__jump");
            element.scrollTop += pieces[0]!.getBoundingClientRect().top - element.getBoundingClientRect().top - element.clientHeight / 3;
            timer = setTimeout(clear, JUMP_MARK_MS);
          };
          timer = setTimeout(mark, 50);
          return;
        }
      }
    })();
    return () => {
      live = false;
      if (timer !== undefined) clearTimeout(timer);
      clear();
    };
    // Only a new double click moves the view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jump?.nonce, pdf]);

  const range = visiblePages(layout, scrollTop, size.height, size.height);
  const columnWidth = Math.max(layout.width + 2 * PAGE_GAP, size.width);

  return (
    <div ref={scroller} className="pdf-viewer" onScroll={onScroll} onMouseUp={onMouseUp} tabIndex={0} role="region" aria-label="PDF pages">
      <div className="pdf-viewer__column" style={{ height: `${layout.height}px`, width: `${columnWidth}px` }}>
        {layout.boxes.map((box, index) => (
          <div
            key={index}
            className="pdf-viewer__page"
            data-page={index + 1}
            style={{ top: `${box.top}px`, left: `${(columnWidth - box.width) / 2}px`, width: `${box.width}px`, height: `${box.height}px` }}
          >
            {range !== null && index >= range.first && index <= range.last ? (
              <>
                <PageCanvas document={pdf} index={index} scale={scale} cssWidth={box.width} cssHeight={box.height} />
                {withText ? <PageText document={pdf} index={index} scale={scale} passages={highlights ?? []} /> : null}
              </>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
