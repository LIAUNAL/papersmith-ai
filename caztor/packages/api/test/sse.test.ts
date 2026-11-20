import { describe, expect, it } from "vitest";
import { createApp, type ApiDeps } from "../src/app.ts";
import { createEventHub, formatSseEvent, HEARTBEAT_MS } from "../src/sse.ts";
import { headers, security } from "./support.ts";

/** A clock that only moves when told to; timers fire in due order. */
function fakeClock() {
  let now = 0;
  let nextId = 0;
  const timers = new Map<number, { due: number; fn: () => void }>();
  return {
    setTimeout(fn: () => void, ms: number) {
      const id = (nextId += 1);
      timers.set(id, { due: now + ms, fn });
      return () => void timers.delete(id);
    },
    advance(ms: number) {
      const target = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, timer]) => timer.due <= target).sort((a, b) => a[1].due - b[1].due)[0];
        if (due === undefined) break;
        timers.delete(due[0]);
        now = due[1].due;
        due[1].fn();
      }
      now = target;
    },
    pending: () => timers.size,
  };
}

function unusedPort<T extends object>(name: string): T {
  return new Proxy({}, { get: () => () => Promise.reject(new Error(`${name} is not used by the event stream`)) }) as T;
}

function setup() {
  const clock = fakeClock();
  const events = createEventHub();
  const deps: ApiDeps = { projectName: "p", store: unusedPort("store"), state: unusedPort("state"), events, clock };
  return { app: createApp(deps, security), clock, events };
}

async function open(app: ReturnType<typeof setup>["app"]) {
  const response = await app.request("/api/events", { headers: headers() });
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  return { response, reader, next: async () => decoder.decode((await reader.read()).value) };
}

describe("formatSseEvent", () => {
  it("frames id, event and a single-line JSON data field, ending with a blank line", () => {
    expect(formatSseEvent({ id: 7, event: "file_changed", data: { path: "a.tex", hash: null } })).toBe(
      'id: 7\nevent: file_changed\ndata: {"path":"a.tex","hash":null}\n\n',
    );
  });

  it("keeps newlines inside data escaped so one event is always one frame", () => {
    const frame = formatSseEvent({ id: 1, event: "x", data: { text: "a\nb\r\nc" } });
    expect(frame).toBe('id: 1\nevent: x\ndata: {"text":"a\\nb\\r\\nc"}\n\n');
    expect(frame.split("\n").filter((line) => line !== "")).toHaveLength(3);
  });

  it("refuses an event name that could inject another field", () => {
    expect(() => formatSseEvent({ id: 1, event: "x\ndata: evil", data: {} })).toThrow(/event name/i);
  });
});

describe("GET /api/events", () => {
  it("is rejected without the launch token", async () => {
    const { app } = setup();
    const response = await app.request("/api/events", { headers: { host: "127.0.0.1:4173" } });
    expect(response.status).toBe(401);
  });

  it("answers as an event stream that is never cached, with the security headers", async () => {
    const { app } = setup();
    const { response, reader } = await open(app);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    await reader.cancel();
  });

  it("sends published events with increasing ids", async () => {
    const { app, events } = setup();
    const { next, reader } = await open(app);
    events.publish("file_changed", { path: "a.tex", hash: null });
    events.publish("compile.started", { compileId: "c1" });
    expect(await next()).toBe('id: 1\nevent: file_changed\ndata: {"path":"a.tex","hash":null}\n\n');
    expect(await next()).toBe('id: 2\nevent: compile.started\ndata: {"compileId":"c1"}\n\n');
    await reader.cancel();
  });

  it("delivers each event to every connected client with the same id", async () => {
    const { app, events } = setup();
    const first = await open(app);
    const second = await open(app);
    events.publish("file_changed", { path: "b.tex", hash: null });
    expect(await first.next()).toBe(await second.next());
    await first.reader.cancel();
    await second.reader.cancel();
  });

  it("sends a comment heartbeat every 15 seconds and not before", async () => {
    const { app, clock, events } = setup();
    const { next, reader } = await open(app);
    expect(HEARTBEAT_MS).toBe(15_000);
    clock.advance(14_999);
    events.publish("file_changed", { path: "a.tex", hash: null });
    expect(await next()).toMatch(/^id: 1\n/);
    clock.advance(1);
    expect(await next()).toBe(": heartbeat\n\n");
    clock.advance(15_000);
    expect(await next()).toBe(": heartbeat\n\n");
    await reader.cancel();
  });

  it("stops listening and cancels the heartbeat when the client disconnects", async () => {
    const { app, clock, events } = setup();
    const { reader } = await open(app);
    expect(events.subscriberCount()).toBe(1);
    expect(clock.pending()).toBe(1);
    await reader.cancel();
    expect(events.subscriberCount()).toBe(0);
    expect(clock.pending()).toBe(0);
  });
});
