import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeDocument, type FakeDocument } from "../testing/fake-pdf.ts";
import { CSS_UNITS, layoutPages, PAGE_GAP, scrollTopFor } from "./layout.ts";
import { PdfViewer } from "./PdfViewer.tsx";

const VIEWPORT = { width: 900, height: 700 };

beforeEach(() => {
  // jsdom does no layout, so the scroller reports a fixed size.
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(VIEWPORT.height);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(VIEWPORT.width);
});
afterEach(() => vi.restoreAllMocks());

const flush = () => act(async () => void (await new Promise((resolve) => setTimeout(resolve, 0))));
const scroller = (container: HTMLElement) => container.querySelector<HTMLElement>(".pdf-viewer")!;
const canvases = (container: HTMLElement) => [...container.querySelectorAll<HTMLCanvasElement>("canvas")];
const percent = (value: number) => ({ mode: "percent" as const, percent: value });
const top = { page: 0, offset: 0 };

describe("PdfViewer layout", () => {
  it("reserves the full height of the document so the scroll bar is right before any page is drawn", async () => {
    const doc = fakeDocument("a", 10);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const expected = layoutPages(doc.pageSizes, CSS_UNITS).height;
    expect(container.querySelector<HTMLElement>(".pdf-viewer__column")?.style.height).toBe(`${expected}px`);
    expect(container.querySelectorAll(".pdf-viewer__page")).toHaveLength(10);
  });

  it("sizes pages from the zoom, and from the width when the zoom is fit", async () => {
    const doc = fakeDocument("a", 2);
    const { container, rerender } = render(<PdfViewer document={doc} zoom={percent(150)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const page = () => container.querySelector<HTMLElement>(".pdf-viewer__page")!;
    expect(page().style.width).toBe(`${600 * 1.5 * CSS_UNITS}px`);
    rerender(<PdfViewer document={doc} zoom={{ mode: "fit" }} anchor={top} onViewChange={() => {}} />);
    await flush();
    expect(page().style.width).toBe(`${VIEWPORT.width - 24}px`);
  });
});

describe("PdfViewer lazy rendering", () => {
  it("draws only the pages near the viewport of a 50-page document", async () => {
    const doc = fakeDocument("a", 50);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    expect(doc.drawn.length).toBeGreaterThan(0);
    expect(doc.drawn.length).toBeLessThanOrEqual(4);
    expect(canvases(container).length).toBeLessThanOrEqual(4);
    expect(canvases(container)[0]?.dataset["page"]).toBe("0");
  });

  it("draws the next pages when scrolled to them, and does not draw a page twice", async () => {
    const doc = fakeDocument("a", 50);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    const before = doc.drawn.length;
    fireEvent.scroll(scroller(container), { target: { scrollTop: scrollTopFor(layout, { page: 30, offset: 0 }) } });
    await flush();
    expect(doc.drawn.some((entry) => entry.startsWith("30@"))).toBe(true);
    expect(doc.drawn.length - before).toBeLessThanOrEqual(4);
    const thirty = doc.drawn.filter((entry) => entry.startsWith("30@")).length;
    fireEvent.scroll(scroller(container), { target: { scrollTop: scrollTopFor(layout, { page: 30, offset: 0.1 }) } });
    await flush();
    expect(doc.drawn.filter((entry) => entry.startsWith("30@")).length).toBe(thirty);
  });

  it("drops the canvases of pages that left the window, so memory stays bounded", async () => {
    const doc = fakeDocument("a", 50);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    fireEvent.scroll(scroller(container), { target: { scrollTop: scrollTopFor(layout, { page: 40, offset: 0 }) } });
    await flush();
    expect(canvases(container).some((canvas) => canvas.dataset["page"] === "0")).toBe(false);
    expect(canvases(container).length).toBeLessThanOrEqual(4);
  });
});

describe("PdfViewer position", () => {
  it("opens at the given anchor", async () => {
    const doc = fakeDocument("a", 10);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={{ page: 3, offset: 0.5 }} onViewChange={() => {}} />);
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    expect(scroller(container).scrollTop).toBeCloseTo(scrollTopFor(layout, { page: 3, offset: 0.5 }), 3);
    expect(doc.drawn.some((entry) => entry.startsWith("3@"))).toBe(true);
  });

  it("reports the anchor and the zoom after the user scrolls", async () => {
    const doc = fakeDocument("a", 10);
    const seen: unknown[] = [];
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={(view) => seen.push(view)} />);
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    fireEvent.scroll(scroller(container), { target: { scrollTop: scrollTopFor(layout, { page: 2, offset: 0.25 }) } });
    const last = seen.at(-1) as { anchor: { page: number; offset: number }; zoom: unknown };
    expect(last.anchor.page).toBe(2);
    expect(last.anchor.offset).toBeCloseTo(0.25, 6);
    expect(last.zoom).toEqual(percent(100));
  });

  it("keeps the scroll position and the zoom when a new version of the document arrives", async () => {
    const first = fakeDocument("v1", 10);
    const { container, rerender } = render(<PdfViewer document={first} zoom={percent(150)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const layout = layoutPages(first.pageSizes, 1.5 * CSS_UNITS);
    const wanted = scrollTopFor(layout, { page: 2, offset: 0.4 });
    fireEvent.scroll(scroller(container), { target: { scrollTop: wanted } });
    await flush();

    const second = fakeDocument("v2", 10);
    rerender(<PdfViewer document={second} zoom={percent(150)} anchor={top} onViewChange={() => {}} />);
    await flush();
    expect(scroller(container).scrollTop).toBeCloseTo(wanted, 3);
    expect(second.drawn.every((entry) => entry.endsWith(`@${(1.5 * CSS_UNITS).toFixed(3)}`))).toBe(true);
    expect(canvases(container).some((canvas) => canvas.dataset["label"] === "v2" && canvas.dataset["page"] === "2")).toBe(true);
  });

  it("keeps the same place in the document when the zoom changes", async () => {
    const doc = fakeDocument("a", 10);
    const { container, rerender } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const before = layoutPages(doc.pageSizes, CSS_UNITS);
    fireEvent.scroll(scroller(container), { target: { scrollTop: scrollTopFor(before, { page: 4, offset: 0.5 }) } });
    await flush();
    rerender(<PdfViewer document={doc} zoom={percent(200)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const after = layoutPages(doc.pageSizes, 2 * CSS_UNITS);
    expect(scroller(container).scrollTop).toBeCloseTo(scrollTopFor(after, { page: 4, offset: 0.5 }), 3);
  });
});

describe("PdfViewer reload without flicker", () => {
  it("keeps showing the old pages until the new ones are drawn, then swaps them", async () => {
    const first = fakeDocument("v1", 3);
    const { container, rerender } = render(<PdfViewer document={first} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const labels = () => canvases(container).map((canvas) => canvas.dataset["label"]);
    expect(labels()).toEqual(["v1", "v1"]);

    const second = fakeDocument("v2", 3);
    second.hold = true;
    rerender(<PdfViewer document={second} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    expect(labels()).toEqual(["v1", "v1"]);
    second.releaseDrawings();
    await flush();
    expect(labels()).toEqual(["v2", "v2"]);
  });

  it("does not let a slow drawing of an old document overwrite a newer one", async () => {
    const first = fakeDocument("v1", 1);
    first.hold = true;
    const { container, rerender } = render(<PdfViewer document={first} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    const second = fakeDocument("v2", 1);
    rerender(<PdfViewer document={second} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    first.releaseDrawings();
    await flush();
    expect(canvases(container).map((canvas) => canvas.dataset["label"])).toEqual(["v2"]);
  });
});

describe("PdfViewer text selection", () => {
  const withText = (doc: FakeDocument) => {
    const rendered: number[] = [];
    doc.renderText = (index, container) => {
      rendered.push(index);
      const span = window.document.createElement("span");
      span.textContent = `Text of page ${index + 1}`;
      container.replaceChildren(span);
      return { done: Promise.resolve(), cancel() {} };
    };
    return rendered;
  };

  it("draws a text layer and reports the selected text with its page when asked to", async () => {
    const doc = fakeDocument("a", 2);
    const rendered = withText(doc);
    const selected: Array<{ text: string; page: number }> = [];
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} onTextSelected={(s) => selected.push(s)} />);
    await flush();
    expect(rendered).toContain(0);
    const span = container.querySelector<HTMLElement>('[data-page="1"] .pdf-viewer__text span')!;
    const range = window.document.createRange();
    range.selectNodeContents(span);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(scroller(container));
    expect(selected).toEqual([{ text: "Text of page 1", page: 1 }]);
    window.getSelection()!.removeAllRanges();
  });

  it("draws no text layer without a listener, as before", async () => {
    const doc = fakeDocument("a", 2);
    const rendered = withText(doc);
    const { container } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} />);
    await flush();
    expect(rendered).toEqual([]);
    expect(container.querySelector(".pdf-viewer__text")).toBeNull();
  });
});

describe("PdfViewer explained passages", () => {
  const lines = (doc: FakeDocument, texts: string[][]) => {
    doc.renderText = (index, container) => {
      container.replaceChildren(...(texts[index] ?? []).map((text) => Object.assign(window.document.createElement("span"), { textContent: text })));
      return { done: Promise.resolve(), cancel() {} };
    };
  };
  const marked = (container: HTMLElement) => [...container.querySelectorAll(".pdf-viewer__explained")].map((span) => span.textContent);

  it("marks the text pieces that hold a passage, across pieces and hyphenation, and reads LaTeX as printed", async () => {
    const doc = fakeDocument("a", 2);
    lines(doc, [["Intro.", "Each colour class is up-", "dated in parallel without conflicts.", "Unrelated."], ["Critical points of the Heisenberg model"]]);
    const { container } = render(
      <PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={["each colour class is updated in parallel without conflicts", "Critical points~\\cite{chen1993} of the \\textbf{Heisenberg} model"]} />,
    );
    await flush();
    await flush();
    expect(marked(container)).toEqual(["Each colour class is up-", "dated in parallel without conflicts.", "Critical points of the Heisenberg model"]);
  });

  it("removes the stronger mark of the current passage too when highlighting is turned off", async () => {
    const passage = "each colour class is updated in parallel without conflicts";
    const doc = fakeDocument("a", 1);
    lines(doc, [["Each colour class is updated in parallel without conflicts."]]);
    doc.pageText = async () => "Each colour class is updated in parallel without conflicts.";
    const props = { document: doc, zoom: percent(100), anchor: top, onViewChange: () => {} };
    const { container, rerender } = render(<PdfViewer {...props} highlights={[passage]} focus={{ passage, nonce: 1 }} />);
    await flush();
    await flush();
    await act(async () => void (await new Promise((resolve) => setTimeout(resolve, 120))));
    expect(container.querySelectorAll(".pdf-viewer__explained--current")).toHaveLength(1);
    rerender(<PdfViewer {...props} highlights={[]} focus={null} />);
    await flush();
    expect(container.querySelectorAll(".pdf-viewer__explained, .pdf-viewer__explained--current")).toHaveLength(0);
  });

  it("removes the marks when the passages go away", async () => {
    const doc = fakeDocument("a", 1);
    lines(doc, [["Each colour class is updated in parallel without conflicts."]]);
    const props = { document: doc, zoom: percent(100), anchor: top, onViewChange: () => {} };
    const { container, rerender } = render(<PdfViewer {...props} highlights={["each colour class is updated in parallel without conflicts"]} />);
    await flush();
    await flush();
    expect(marked(container)).toHaveLength(1);
    rerender(<PdfViewer {...props} highlights={[]} />);
    await flush();
    expect(marked(container)).toEqual([]);
  });
});

describe("PdfViewer stepping to an explained passage", () => {
  const passage = "each colour class is updated in parallel without conflicts";

  it("finds the page that holds the passage, drawn or not, and scrolls to it", async () => {
    const doc = fakeDocument("a", 20);
    const asked: number[] = [];
    doc.pageText = async (index: number) => {
      asked.push(index);
      return index === 12 ? "Results. Each colour class is up- dated in parallel without conflicts. More." : "Other text.";
    };
    const { container, rerender } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={null} />);
    await flush();
    const start = scroller(container).scrollTop;
    expect(start).toBeLessThan(100);
    rerender(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={{ passage, nonce: 1 }} />);
    await flush();
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    expect(scroller(container).scrollTop).toBeCloseTo(layout.boxes[12]!.top - PAGE_GAP, 3);
    expect(asked.slice(0, 13)).toEqual(Array.from({ length: 13 }, (_, index) => index));
  });

  it("stays where it is when no page holds the passage", async () => {
    const doc = fakeDocument("a", 5);
    doc.pageText = async () => "nothing relevant";
    const { container, rerender } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={null} />);
    await flush();
    const start = scroller(container).scrollTop;
    rerender(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={{ passage, nonce: 1 }} />);
    await flush();
    await flush();
    expect(scroller(container).scrollTop).toBe(start);
  });

  it("drops the previous step's stronger mark when the next passage is not in the PDF", async () => {
    const doc = fakeDocument("a", 5);
    doc.pageText = async () => "nothing relevant";
    const { container, rerender } = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={null} />);
    await flush();
    const previous = document.createElement("span");
    previous.className = "pdf-viewer__explained pdf-viewer__explained--current";
    scroller(container).append(previous);
    rerender(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} highlights={[passage]} focus={{ passage, nonce: 2 }} />);
    await flush();
    expect(previous.classList.contains("pdf-viewer__explained--current")).toBe(false);
    expect(previous.classList.contains("pdf-viewer__explained")).toBe(true);
  });
});

describe("PdfViewer jumping to the source text a double click names", () => {
  const sentence = "each colour class is updated in parallel without conflicts";

  it("scrolls to the page that prints the narrowest candidate it finds and marks it there for a moment", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const doc = fakeDocument("a", 20);
      doc.pageText = async (index: number) => (index === 7 ? "Methods. Each colour class is up- dated in parallel without conflicts. More." : "Other text.");
      doc.renderText = (index, container) => {
        container.replaceChildren(...(index === 7 ? ["Methods.", "Each colour class is up-", "dated in parallel without conflicts.", "More."] : ["Other text."]).map((text) => Object.assign(window.document.createElement("span"), { textContent: text })));
        return { done: Promise.resolve(), cancel() {} };
      };
      const props = { document: doc, zoom: percent(100), anchor: top, onViewChange: () => {} };
      const { container, rerender } = render(<PdfViewer {...props} jump={null} />);
      await flush();
      rerender(<PdfViewer {...props} jump={{ candidates: ["nowhere in this document at all", sentence], nonce: 1 }} />);
      await flush();
      await flush();
      const layout = layoutPages(doc.pageSizes, CSS_UNITS);
      expect(scroller(container).scrollTop).toBeCloseTo(layout.boxes[7]!.top - PAGE_GAP, 3);
      // A browser reports the scroll the viewer made; jsdom does not, so the test does.
      fireEvent.scroll(scroller(container));
      await flush();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200);
      });
      const jumped = () => [...container.querySelectorAll(".pdf-viewer__jump")].map((span) => span.textContent);
      expect(jumped()).toEqual(["Each colour class is up-", "dated in parallel without conflicts."]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(jumped()).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("says when no page prints the clicked text, then lets the notice go", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const doc = fakeDocument("a", 3);
      doc.pageText = async () => "Other text.";
      const props = { document: doc, zoom: percent(100), anchor: top, onViewChange: () => {} };
      const { container, rerender } = render(<PdfViewer {...props} jump={null} />);
      await flush();
      const start = scroller(container).scrollTop;
      rerender(<PdfViewer {...props} jump={{ candidates: ["a sentence written after this PDF was compiled"], nonce: 1 }} />);
      await flush();
      await flush();
      expect(container.querySelector('[role="status"]')?.textContent).toBe("Not in this PDF. Compile to bring it up to date.");
      expect(scroller(container).scrollTop).toBe(start);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(container.querySelector('[role="status"]')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("finds a short table row", async () => {
    const doc = fakeDocument("a", 2);
    doc.pageText = async (index: number) => (index === 1 ? "Software Python 3.11.5 Triton 3.1.0" : "Other text.");
    const props = { document: doc, zoom: percent(100), anchor: top, onViewChange: () => {} };
    const { container, rerender } = render(<PdfViewer {...props} jump={null} />);
    await flush();
    rerender(<PdfViewer {...props} jump={{ candidates: ["Python & 3.11.5 \\\\"], nonce: 1 }} />);
    await flush();
    await flush();
    const layout = layoutPages(doc.pageSizes, CSS_UNITS);
    expect(scroller(container).scrollTop).toBeCloseTo(layout.boxes[1]!.top - PAGE_GAP, 3);
  });
});

describe("PdfViewer double click on the page text", () => {
  const page = ["Methods.", "Each colour class is up-", "dated in parallel without conflicts.", "More text here."];
  const setup = (answer: boolean) => {
    const doc = fakeDocument("a", 1);
    doc.renderText = (_index, container) => {
      container.replaceChildren(...page.map((text) => Object.assign(window.document.createElement("span"), { textContent: text })));
      return { done: Promise.resolve(), cancel() {} };
    };
    const asked: Array<{ candidates: readonly string[]; word: string }> = [];
    const utils = render(<PdfViewer document={doc} zoom={percent(100)} anchor={top} onViewChange={() => {}} onJumpToSource={(target) => (asked.push(target), answer)} />);
    return { ...utils, asked };
  };
  const doubleClick = (span: Element, word: string) => {
    const text = span.firstChild!;
    const at = (text.textContent ?? "").indexOf(word);
    const range = document.createRange();
    range.setStart(text, at);
    range.setEnd(text, at + word.length);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.doubleClick(span);
  };

  it("asks for the source of the clicked line, then of the lines around it, with the clicked word", async () => {
    const { container, asked } = setup(true);
    await flush();
    await flush();
    const span = [...container.querySelectorAll(".pdf-viewer__text span")].find((node) => node.textContent === page[2])!;
    doubleClick(span, "parallel");
    expect(asked).toEqual([
      {
        candidates: [page[2], `${page[1]} ${page[2]} ${page[3]}`, `${page[0]} ${page[1]} ${page[2]} ${page[3]}`],
        word: "parallel",
      },
    ]);
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("takes the word under the click when the browser selected only the space between two words", async () => {
    const { container, asked } = setup(true);
    await flush();
    await flush();
    const span = [...container.querySelectorAll(".pdf-viewer__text span")].find((node) => node.textContent === page[2])!;
    doubleClick(span, " ");
    expect(asked[0]?.word).toBe("without");
  });

  it("says so when the source does not hold the clicked text", async () => {
    const { container } = setup(false);
    await flush();
    await flush();
    doubleClick(container.querySelectorAll(".pdf-viewer__text span")[0]!, "Methods");
    await flush();
    expect(container.querySelector('[role="status"]')?.textContent).toBe("Not found in the LaTeX source.");
  });
});
