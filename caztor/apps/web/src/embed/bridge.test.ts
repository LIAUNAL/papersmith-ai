import { afterEach, describe, expect, it, vi } from "vitest";
import { embedOrigins, forgetFramingOrigin, framingOrigin, listenForCompose, listenForTheme, postReady, postSelection } from "./bridge.ts";

const SMITH = "http://127.0.0.1:8765";
const TWIN = "http://localhost:8765";
afterEach(() => {
  vi.restoreAllMocks();
  forgetFramingOrigin();
  Reflect.deleteProperty(document, "referrer");
});

function framedFrom(referrer: string): void {
  Object.defineProperty(document, "referrer", { value: referrer, configurable: true });
}

const send = (data: unknown, origin: string, source: MessageEventSource | null = window.parent) =>
  window.dispatchEvent(new MessageEvent("message", { data, origin, source }));

describe("embed bridge", () => {
  it("posts a PDF selection to the embedding page, addressed to its origin only", () => {
    framedFrom(`${SMITH}/`);
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    postSelection(SMITH, { text: "spin lattice", page: 3 });
    expect(post.mock.calls).toEqual([[{ type: "caztor:pdf-selection", text: "spin lattice", page: 3 }, SMITH]]);
  });

  it("names the loopback twin of a loopback origin, and nothing more for any other", () => {
    expect(embedOrigins(SMITH)).toEqual([SMITH, TWIN]);
    expect(embedOrigins(TWIN)).toEqual([TWIN, SMITH]);
    expect(embedOrigins("https://box.lan:8765")).toEqual(["https://box.lan:8765"]);
  });

  it("addresses the twin that framed it: told by the browser, else learned from the page's messages", () => {
    expect(framingOrigin(SMITH, { ancestorOrigins: [TWIN], referrer: "" })).toBe(TWIN);
    expect(framingOrigin(SMITH, { referrer: `${TWIN}/#pdf` })).toBe(TWIN);
    expect(framingOrigin(SMITH, { ancestorOrigins: ["http://evil.example"], referrer: "http://evil.example/" })).toBeNull();
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    framedFrom(`${TWIN}/`);
    postReady(SMITH);
    expect(post.mock.calls).toEqual([[{ type: "caztor:ready" }, TWIN]]);
  });

  it("while the framing origin is unknown, tries each allowed one, then keeps to the one that answered", () => {
    framedFrom("");
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    postReady(SMITH);
    expect(post.mock.calls).toEqual([[{ type: "caztor:ready" }, SMITH], [{ type: "caztor:ready" }, TWIN]]);
    const seen: string[] = [];
    const stop = listenForTheme(SMITH, (theme) => seen.push(theme));
    send({ type: "caztor:theme", theme: "dark" }, TWIN);
    stop();
    expect(seen).toEqual(["dark"]);
    post.mockClear();
    postSelection(SMITH, { text: "x", page: 1 });
    expect(post.mock.calls).toEqual([[{ type: "caztor:pdf-selection", text: "x", page: 1 }, TWIN]]);
  });

  it("a message from an origin outside the allowed ones teaches nothing", () => {
    framedFrom("");
    const stop = listenForTheme(SMITH, () => {});
    send({ type: "caztor:theme", theme: "dark" }, "http://evil.example");
    stop();
    expect(framingOrigin(SMITH, { referrer: "" })).toBeNull();
  });

  it("hands over a compose request only from the embedding page and origin, with text", () => {
    const seen: string[] = [];
    const stop = listenForCompose(SMITH, (text) => seen.push(text));
    send({ type: "caztor:compose", text: "Delete the second sentence." }, SMITH);
    send({ type: "caztor:compose", text: "from elsewhere" }, "http://evil.example");
    send({ type: "caztor:compose", text: "not the parent" }, SMITH, null);
    send({ type: "caztor:compose", text: 42 }, SMITH);
    send({ type: "other", text: "x" }, SMITH);
    stop();
    send({ type: "caztor:compose", text: "after stop" }, SMITH);
    expect(seen).toEqual(["Delete the second sentence."]);
  });

  it("says it is ready to the embedding page, addressed to its origin only", () => {
    framedFrom(`${SMITH}/`);
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    postReady(SMITH);
    expect(post.mock.calls).toEqual([[{ type: "caztor:ready" }, SMITH]]);
  });

  it("takes a light or dark theme only from the embedding page and origin", () => {
    const seen: string[] = [];
    const stop = listenForTheme(SMITH, (theme) => seen.push(theme));
    send({ type: "caztor:theme", theme: "light" }, SMITH);
    send({ type: "caztor:theme", theme: "dark" }, "http://evil.example");
    send({ type: "caztor:theme", theme: "dark" }, SMITH, null);
    send({ type: "caztor:theme", theme: "sepia" }, SMITH);
    send({ type: "caztor:theme", theme: "dark" }, SMITH);
    stop();
    send({ type: "caztor:theme", theme: "light" }, SMITH);
    expect(seen).toEqual(["light", "dark"]);
  });
});
