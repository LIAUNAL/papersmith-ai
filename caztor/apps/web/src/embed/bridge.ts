/**
 * Messages between Caztor and the page that shows it in a frame (a PaperSmith dashboard). Both directions are pinned
 * to the origin the server was started with and its loopback twin (`127.0.0.1` and `localhost` on the same port are
 * the same dashboard): requests are taken only from the parent window at one of those origins, and messages are
 * addressed to the one that actually framed Caztor.
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

const LOOPBACK_TWIN = /^(https?):\/\/(127\.0\.0\.1|localhost)((?::\d{1,5})?)$/;

/** `origin` and, for `127.0.0.1` or `localhost`, the other name on the same scheme and port, as the dashboard allows them. */
export function embedOrigins(origin: string): string[] {
  const match = LOOPBACK_TWIN.exec(origin);
  if (match === null) return [origin];
  const [, scheme, host, port] = match;
  return [origin, `${scheme}://${host === "127.0.0.1" ? "localhost" : "127.0.0.1"}${port}`];
}

/** The allowed origin the embedding page has sent a message from, once it has. */
let framedBy: string | null = null;

/** Forgets the origin learned from the embedding page's messages (a new page load starts without it). */
export function forgetFramingOrigin(): void {
  framedBy = null;
}

/** What the browser says about the page that framed this one. */
export interface FramingHints {
  ancestorOrigins?: ArrayLike<string> | undefined;
  referrer: string;
}

function hints(): FramingHints {
  return { ancestorOrigins: window.location.ancestorOrigins, referrer: document.referrer };
}

/**
 * The origin of the page that framed Caztor, when it is one of the allowed ones: learned from its messages, else what
 * the browser says (`location.ancestorOrigins`, then the referrer). Null while unknown.
 */
export function framingOrigin(origin: string, frame: FramingHints = hints()): string | null {
  const allowed = embedOrigins(origin);
  if (framedBy !== null && allowed.includes(framedBy)) return framedBy;
  const ancestor = frame.ancestorOrigins?.[0];
  if (ancestor !== undefined && allowed.includes(ancestor)) return ancestor;
  try {
    const referrer = new URL(frame.referrer).origin;
    if (allowed.includes(referrer)) return referrer;
  } catch {
    // No referrer, or not a URL.
  }
  return null;
}

/**
 * Posts to the embedding page at the origin that framed Caztor. While that is unknown, the message is addressed to
 * each allowed origin in turn: the browser delivers it only when the parent is at the origin named, so only the real
 * one receives it.
 */
function post(origin: string, message: Record<string, unknown>): void {
  const target = framingOrigin(origin);
  for (const to of target === null ? embedOrigins(origin) : [target]) window.parent.postMessage(message, to);
}

/** Tells the embedding page what was selected in the PDF. */
export function postSelection(origin: string, selection: PdfSelection): void {
  post(origin, { type: SELECTION_MESSAGE, text: selection.text, page: selection.page });
}

/** Tells the embedding page that Caztor listens now, so it can send what Caztor needs from it, such as its theme. */
export function postReady(origin: string): void {
  post(origin, { type: READY_MESSAGE });
}

/**
 * Messages from the embedding page at `origin` or its loopback twin only, as plain objects. The origin they come from
 * is the one later messages are addressed to. Returns the function that stops listening.
 */
function listen(origin: string, handle: (data: Record<string, unknown>) => void): () => void {
  const allowed = embedOrigins(origin);
  const listener = (event: MessageEvent) => {
    if (!allowed.includes(event.origin) || event.source !== window.parent) return;
    framedBy = event.origin;
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
