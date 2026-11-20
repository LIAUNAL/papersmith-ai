/**
 * Messages between Caztor and the page that shows it in a frame (a PaperSmith dashboard). Both directions are pinned
 * to the one origin the server was started with: selections are addressed to it, and requests are taken only from the
 * parent window at that origin.
 */

export interface PdfSelection {
  text: string;
  /** One-based page number. */
  page: number;
}

export const SELECTION_MESSAGE = "caztor:pdf-selection";
export const COMPOSE_MESSAGE = "caztor:compose";
export const READY_MESSAGE = "caztor:ready";
export const THEME_MESSAGE = "caztor:theme";
export type EmbedTheme = "light" | "dark";

/** Tells the embedding page what was selected in the PDF. */
export function postSelection(origin: string, selection: PdfSelection): void {
  window.parent.postMessage({ type: SELECTION_MESSAGE, text: selection.text, page: selection.page }, origin);
}

/** Tells the embedding page that Caztor listens now, so it can send what Caztor needs from it, such as its theme. */
export function postReady(origin: string): void {
  window.parent.postMessage({ type: READY_MESSAGE }, origin);
}

/** Messages from the embedding page at `origin` only, as plain objects. Returns the function that stops listening. */
function listen(origin: string, handle: (data: Record<string, unknown>) => void): () => void {
  const listener = (event: MessageEvent) => {
    if (event.origin !== origin || event.source !== window.parent) return;
    const data: unknown = event.data;
    if (typeof data === "object" && data !== null) handle(data as Record<string, unknown>);
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}

/** Calls `onTheme` with each theme the embedding page sends: its own, light or dark. */
export function listenForTheme(origin: string, onTheme: (theme: EmbedTheme) => void): () => void {
  return listen(origin, ({ type, theme }) => {
    if (type === THEME_MESSAGE && (theme === "light" || theme === "dark")) onTheme(theme);
  });
}

/** Calls `onCompose` with the text of every compose request from the embedding page. Returns the function that stops listening. */
export function listenForCompose(origin: string, onCompose: (text: string) => void): () => void {
  return listen(origin, ({ type, text }) => {
    if (type === COMPOSE_MESSAGE && typeof text === "string" && text.trim() !== "") onCompose(text);
  });
}
