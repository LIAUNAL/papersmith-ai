import { afterEach, describe, expect, it, vi } from "vitest";
import { listenForCompose, listenForTheme, postReady, postSelection } from "./bridge.ts";

const SMITH = "http://127.0.0.1:8765";
afterEach(() => vi.restoreAllMocks());

describe("embed bridge", () => {
  it("posts a PDF selection to the embedding page, addressed to its origin only", () => {
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    postSelection(SMITH, { text: "spin lattice", page: 3 });
    expect(post).toHaveBeenCalledWith({ type: "caztor:pdf-selection", text: "spin lattice", page: 3 }, SMITH);
  });

  it("hands over a compose request only from the embedding page and origin, with text", () => {
    const seen: string[] = [];
    const stop = listenForCompose(SMITH, (text) => seen.push(text));
    const send = (data: unknown, origin: string, source: MessageEventSource | null = window.parent) =>
      window.dispatchEvent(new MessageEvent("message", { data, origin, source }));
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
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    postReady(SMITH);
    expect(post).toHaveBeenCalledWith({ type: "caztor:ready" }, SMITH);
  });

  it("takes a light or dark theme only from the embedding page and origin", () => {
    const seen: string[] = [];
    const stop = listenForTheme(SMITH, (theme) => seen.push(theme));
    const send = (data: unknown, origin: string, source: MessageEventSource | null = window.parent) =>
      window.dispatchEvent(new MessageEvent("message", { data, origin, source }));
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
