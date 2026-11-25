import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PdfDocument, PdfEngine } from "./engine.ts";

/**
 * PDF.js behind the engine seam. Loaded on first use, so the library stays out of the main bundle. The worker is a
 * same-origin asset (the page's content security policy allows scripts and workers from 'self' only), scripting inside
 * PDFs stays off (the default) and WebAssembly is not used (that would need 'wasm-unsafe-eval').
 */
export const pdfjsEngine: PdfEngine = {
  async open(bytes): Promise<PdfDocument> {
    const pdfjs = await import("pdfjs-dist");
    pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
    // PDF.js takes ownership of the buffer it is given, so it gets a copy.
    const loading = pdfjs.getDocument({ data: bytes.slice(), useWasm: false });
    const doc = await loading.promise;
    const pages = await Promise.all(Array.from({ length: doc.numPages }, (_, index) => doc.getPage(index + 1)));
    const pageSizes = pages.map((page) => {
      const view = page.getViewport({ scale: 1 });
      return { width: view.width, height: view.height };
    });
    return {
      pageSizes,
      render(index, canvas, scale) {
        const page = pages[index];
        if (page === undefined) return { done: Promise.reject(new Error(`There is no page ${index + 1}.`)), cancel() {} };
        const viewport = page.getViewport({ scale });
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        const context = canvas.getContext("2d");
        if (context === null) return { done: Promise.reject(new Error("The browser cannot draw on a canvas.")), cancel() {} };
        const task = page.render({ canvasContext: context, canvas, viewport });
        const done = task.promise.then(() => undefined);
        done.catch(() => {});
        return { done, cancel: () => task.cancel() };
      },
      renderText(index, container, scale) {
        const page = pages[index];
        if (page === undefined) return { done: Promise.reject(new Error(`There is no page ${index + 1}.`)), cancel() {} };
        container.replaceChildren();
        // The text layer sizes itself and its spans from this variable, as in PDF.js's own viewer.
        container.style.setProperty("--total-scale-factor", String(scale));
        const layer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container, viewport: page.getViewport({ scale }) });
        const done = layer.render().then(() => undefined);
        done.catch(() => {});
        return { done, cancel: () => layer.cancel() };
      },
      async pageText(index) {
        const page = pages[index];
        if (page === undefined) return "";
        const content = await page.getTextContent();
        return content.items.map((item) => ("str" in item ? item.str : "")).join(" ");
      },
      destroy() {
        void loading.destroy();
      },
    };
  },
};
