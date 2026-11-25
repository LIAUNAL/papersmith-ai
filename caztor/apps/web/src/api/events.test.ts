import { describe, expect, it } from "vitest";
import { createApiClient } from "./client.ts";
import type { ServerEvent } from "./types.ts";

const TOKEN = "launch-token-0123456789";
const frame = (id: number, event: string, data: unknown) => `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** A response whose body yields the given chunks, then ends (or stays open when `open`). */
function streamOf(chunks: string[], open = false, signal?: AbortSignal): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (!open) controller.close();
      else signal?.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
    },
  });
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

/** Resolves once `count` events arrived. */
function collector(count: number) {
  const events: ServerEvent[] = [];
  let done: () => void = () => {};
  const reached = new Promise<void>((resolve) => (done = resolve));
  return {
    events,
    reached,
    listener: (event: ServerEvent) => {
      events.push(event);
      if (events.length >= count) done();
    },
  };
}

describe("subscribeEvents", () => {
  it("reads the stream with fetch, sending the token header and no cookie-style credentials", async () => {
    const seen: Array<{ url: string; headers: Record<string, string> }> = [];
    const fetchFn = async (input: RequestInfo | URL, init?: RequestInit) => {
      seen.push({ url: String(input), headers: Object.fromEntries(new Headers(init?.headers).entries()) });
      return streamOf([frame(1, "file_changed", { path: "a.tex" })], true, init?.signal ?? undefined);
    };
    const { events, reached, listener } = collector(1);
    const stop = createApiClient({ token: TOKEN, fetch: fetchFn }).subscribeEvents(listener);
    await reached;
    stop();

    expect(seen[0]).toEqual({ url: "/api/events", headers: { "x-caztor-token": TOKEN, accept: "text/event-stream" } });
    expect(events).toEqual([{ id: 1, event: "file_changed", data: { path: "a.tex" } }]);
  });

  it("delivers frames split across chunks", async () => {
    const text = frame(1, "file_changed", { path: "a.tex" }) + frame(2, "file_changed", { path: "b.tex" });
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) =>
      streamOf([text.slice(0, 10), text.slice(10, 40), text.slice(40)], true, init?.signal ?? undefined);
    const { events, reached, listener } = collector(2);
    const stop = createApiClient({ token: TOKEN, fetch: fetchFn }).subscribeEvents(listener);
    await reached;
    stop();
    expect(events.map((event) => event.data)).toEqual([{ path: "a.tex" }, { path: "b.tex" }]);
  });

  it("reconnects after the stream ends, waiting first, and announces that events may have been missed", async () => {
    let connections = 0;
    const waits: number[] = [];
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      connections += 1;
      return connections === 1 ? streamOf([frame(1, "file_changed", { path: "a.tex" })]) : streamOf([frame(2, "file_changed", { path: "b.tex" })], true, init?.signal ?? undefined);
    };
    const { events, reached, listener } = collector(3);
    const stop = createApiClient({ token: TOKEN, fetch: fetchFn, wait: async (ms) => void waits.push(ms) }).subscribeEvents(listener);
    await reached;
    stop();

    expect(connections).toBe(2);
    expect(waits).toEqual([1000]);
    expect(events.map((event) => event.event)).toEqual(["file_changed", "stream_resumed", "file_changed"]);
  });

  it("keeps retrying with a growing delay when the server cannot be reached or refuses", async () => {
    let attempts = 0;
    const waits: number[] = [];
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      attempts += 1;
      if (attempts === 1) throw new TypeError("Failed to fetch");
      if (attempts === 2) return new Response("nope", { status: 503 });
      if (attempts === 3) return new Response("nope", { status: 503 });
      return streamOf([frame(9, "file_changed", {})], true, init?.signal ?? undefined);
    };
    const { reached, listener } = collector(2);
    const stop = createApiClient({ token: TOKEN, fetch: fetchFn, wait: async (ms) => void waits.push(ms) }).subscribeEvents(listener);
    await reached;
    stop();

    expect(attempts).toBe(4);
    expect(waits).toEqual([1000, 2000, 4000]);
  });

  it("stops reading and reconnecting once unsubscribed", async () => {
    let connections = 0;
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      connections += 1;
      return streamOf([frame(1, "file_changed", {})], true, init?.signal ?? undefined);
    };
    const { reached, listener } = collector(1);
    const stop = createApiClient({ token: TOKEN, fetch: fetchFn, wait: async () => {} }).subscribeEvents(listener);
    await reached;
    stop();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(connections).toBe(1);
  });

  it("opens one connection for any number of subscribers and delivers every event to each", async () => {
    let connections = 0;
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      connections += 1;
      return streamOf([frame(1, "file_changed", { path: "a.tex" })], true, init?.signal ?? undefined);
    };
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    const first = collector(1);
    const second = collector(1);
    const stopFirst = client.subscribeEvents(first.listener);
    const stopSecond = client.subscribeEvents(second.listener);
    await Promise.all([first.reached, second.reached]);
    stopFirst();
    stopSecond();
    expect(connections).toBe(1);
    expect(first.events).toEqual([{ id: 1, event: "file_changed", data: { path: "a.tex" } }]);
    expect(second.events).toEqual(first.events);
  });

  it("keeps the connection while one subscriber remains and closes it after the last leaves", async () => {
    const signals: AbortSignal[] = [];
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      signals.push(init?.signal as AbortSignal);
      return streamOf([], true, init?.signal ?? undefined);
    };
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    const stopFirst = client.subscribeEvents(() => {});
    const stopSecond = client.subscribeEvents(() => {});
    await new Promise((resolve) => setTimeout(resolve, 10));
    stopFirst();
    expect(signals).toHaveLength(1);
    expect(signals[0]?.aborted).toBe(false);
    stopSecond();
    expect(signals[0]?.aborted).toBe(true);
    stopSecond();
  });

  it("opens a new connection when someone subscribes again after everyone left", async () => {
    let connections = 0;
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) => {
      connections += 1;
      return streamOf([], true, init?.signal ?? undefined);
    };
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    client.subscribeEvents(() => {})();
    await new Promise((resolve) => setTimeout(resolve, 10));
    client.subscribeEvents(() => {})();
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(connections).toBe(2);
  });

  it("does not let a failing subscriber stop the others", async () => {
    const fetchFn = async (_input: RequestInfo | URL, init?: RequestInit) =>
      streamOf([frame(1, "file_changed", { path: "a.tex" })], true, init?.signal ?? undefined);
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    const healthy = collector(1);
    const stopBad = client.subscribeEvents(() => {
      throw new Error("subscriber failure");
    });
    const stopGood = client.subscribeEvents(healthy.listener);
    await healthy.reached;
    stopBad();
    stopGood();
    expect(healthy.events).toHaveLength(1);
  });
});
