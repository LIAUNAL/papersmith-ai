import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CompileResult } from "../api/types.ts";
import { INITIAL_COMPILE_STATE, type CompileState } from "../compile/compile-state.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { fakeDocument, fakeEngine, type FakeDocument } from "../testing/fake-pdf.ts";
import { CSS_UNITS, layoutPages, scrollTopFor } from "./layout.ts";
import { PdfPreview } from "./PdfPreview.tsx";
import { createPrefsStore } from "./prefs.ts";

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(700);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(900);
});
afterEach(() => vi.restoreAllMocks());

const flush = () => act(async () => void (await new Promise((resolve) => setTimeout(resolve, 0))));
const result = (extra: Partial<CompileResult> = {}): CompileResult => ({ status: "success", pdfRev: "1", diagnostics: [], durationMs: 5, logAvailable: true, ...extra });
const finished = (id: string, extra: Partial<CompileResult> = {}): CompileState => ({
  ...INITIAL_COMPILE_STATE,
  pdfAvailable: (extra.pdfRev ?? "1") !== null,
  last: { compileId: id, result: result(extra) },
});

function memoryStorage() {
  const data: Record<string, string> = {};
  return { data, getItem: (key: string) => data[key] ?? null, setItem: (key: string, value: string) => void (data[key] = value) };
}

function setup(documents: FakeDocument[] = [fakeDocument("v1", 10)], storage = memoryStorage()) {
  const fake = createFakeApi();
  fake.compile.pdf = new Uint8Array([0x25, 0x50, 0x44, 0x46]);
  const engine = fakeEngine(...documents);
  const prefs = createPrefsStore(storage, "thesis");
  const ui = (compile: CompileState) => <PdfPreview api={fake.api} engine={engine} compile={compile} prefs={prefs} />;
  const view = render(ui(INITIAL_COMPILE_STATE));
  return { fake, engine, storage, view, ui, show: async (compile: CompileState) => { view.rerender(ui(compile)); await flush(); } };
}

const pages = () => [...document.querySelectorAll<HTMLElement>(".pdf-viewer__page")];
const scroller = () => document.querySelector<HTMLElement>(".pdf-viewer")!;

describe("PdfPreview states", () => {
  it("invites the user to compile when no PDF exists yet, and does not call the server", async () => {
    const { fake, engine } = setup();
    await flush();
    expect(screen.getByText("No preview yet")).toBeInTheDocument();
    expect(screen.getByText(/Compile the project to see the PDF here/)).toBeInTheDocument();
    expect(fake.calls.filter((call) => call.startsWith("readPdf"))).toEqual([]);
    expect(engine.opened).toEqual([]);
  });

  it("fetches the PDF with the API client and hands the bytes to the engine after a compile", async () => {
    const { fake, engine, show } = setup();
    await show(finished("c1", { pdfRev: "7" }));
    expect(fake.calls).toContain("readPdf 7");
    expect(engine.opened).toHaveLength(1);
    expect([...engine.opened[0]!]).toEqual([0x25, 0x50, 0x44, 0x46]);
    expect(pages()).toHaveLength(10);
    expect(screen.queryByText("No preview yet")).toBeNull();
    expect(screen.queryByText(/out of date/i)).toBeNull();
  });

  it("shows a preview that already exists on the server when the page opens", async () => {
    const { fake, show } = setup();
    await show({ ...INITIAL_COMPILE_STATE, pdfAvailable: true });
    expect(fake.calls).toContain("readPdf current");
    expect(pages()).toHaveLength(10);
  });

  it("keeps the last good PDF and marks it out of date when a compile fails", async () => {
    const { fake, show } = setup([fakeDocument("v1", 10), fakeDocument("v2", 10)]);
    await show(finished("c1", { pdfRev: "7" }));
    await show(finished("c2", { status: "failed", pdfRev: null }));
    expect(pages()).toHaveLength(10);
    expect(screen.getByRole("status", { name: "Preview status" })).toHaveTextContent(/out of date/i);
    expect(fake.calls.filter((call) => call.startsWith("readPdf"))).toEqual(["readPdf 7"]);
    await show(finished("c3", { pdfRev: "9" }));
    expect(screen.queryByText(/out of date/i)).toBeNull();
    expect(fake.calls).toContain("readPdf 9");
  });

  it("says why when the new PDF cannot be read and keeps the old one on screen", async () => {
    const { fake, show } = setup([fakeDocument("v1", 10)]);
    await show(finished("c1", { pdfRev: "7" }));
    fake.failNext(apiError("io", "The PDF could not be read.", 500));
    await show(finished("c2", { pdfRev: "8" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF could not be read.");
    expect(pages()).toHaveLength(10);
  });

  it("says so when the engine cannot open the file", async () => {
    const { engine, show } = setup([]);
    engine.fail = new Error("Invalid PDF structure.");
    await show(finished("c1", { pdfRev: "7" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF could not be shown: Invalid PDF structure.");
  });

  it("frees the previous document once the new one has replaced it", async () => {
    const first = fakeDocument("v1", 10);
    const { show } = setup([first, fakeDocument("v2", 10)]);
    await show(finished("c1", { pdfRev: "7" }));
    expect(first.destroyed).toBe(false);
    await show(finished("c2", { pdfRev: "8" }));
    expect(first.destroyed).toBe(true);
  });
});

describe("PdfPreview zoom and position", () => {
  it("zooms in and out in steps, and fits the width", async () => {
    const { show } = setup();
    await show(finished("c1", { pdfRev: "7" }));
    expect(screen.getByRole("button", { name: "Fit width" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    const widthAt = (percent: number) => 600 * (percent / 100) * CSS_UNITS;
    const width = () => parseFloat(pages()[0]?.style.width ?? "0");
    // Fit shows the 600 pt page at 876 px on a 900 px pane, which is 110 percent: the next level above is 125.
    expect(width()).toBeCloseTo(widthAt(125), 3);
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(width()).toBeCloseTo(widthAt(150), 3);
    await userEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(width()).toBeCloseTo(widthAt(125), 3);
    expect(screen.getByText("125%")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Fit width" }));
    expect(pages()[0]?.style.width).toBe("876px");
  });

  it("remembers zoom and position per project and restores them in a new session", async () => {
    const storage = memoryStorage();
    const first = setup([fakeDocument("v1", 10)], storage);
    await first.show(finished("c1", { pdfRev: "7" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    const layout = layoutPages(fakeDocument("x", 10).pageSizes, 1.5 * CSS_UNITS);
    fireEvent.scroll(scroller(), { target: { scrollTop: scrollTopFor(layout, { page: 2, offset: 0.5 }) } });
    await act(async () => void (await new Promise((resolve) => setTimeout(resolve, 400))));
    first.view.unmount();
    expect(JSON.parse(storage.data["caztor.preview.v1.thesis"]!)).toMatchObject({ zoom: { mode: "percent", percent: 150 }, anchor: { page: 2 } });

    const second = setup([fakeDocument("v1", 10)], storage);
    await second.show(finished("c1", { pdfRev: "7" }));
    expect(parseFloat(pages()[0]?.style.width ?? "0")).toBeCloseTo(600 * 1.5 * CSS_UNITS, 3);
    expect(scroller().scrollTop).toBeCloseTo(scrollTopFor(layout, { page: 2, offset: 0.5 }), 3);
  });

  it("keeps the page and the zoom when a compile produces a new PDF", async () => {
    const { show } = setup([fakeDocument("v1", 10), fakeDocument("v2", 10)]);
    await show(finished("c1", { pdfRev: "7" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    const layout = layoutPages(fakeDocument("x", 10).pageSizes, 1.5 * CSS_UNITS);
    const wanted = scrollTopFor(layout, { page: 2, offset: 0.3 });
    fireEvent.scroll(scroller(), { target: { scrollTop: wanted } });
    await flush();
    await show(finished("c2", { pdfRev: "8" }));
    expect(parseFloat(pages()[0]?.style.width ?? "0")).toBeCloseTo(600 * 1.5 * CSS_UNITS, 3);
    expect(scroller().scrollTop).toBeCloseTo(wanted, 3);
    expect(document.querySelector<HTMLCanvasElement>('canvas[data-page="2"]')?.dataset["label"]).toBe("v2");
  });
});
