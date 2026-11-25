import { describe, expect, it, vi } from "vitest";
import {
  createCompileCoordinator,
  type CompileEvent,
  type CompileRequest,
  type CompileResult,
  type CompilerPort,
  type CoordinatorEvent,
  type RelPath,
} from "../src/index.ts";

const result = (status: CompileResult["status"], extra: Partial<CompileResult> = {}): CompileResult => ({
  status,
  pdfRev: null,
  diagnostics: [],
  durationMs: 5,
  logAvailable: false,
  ...extra,
});

interface Call {
  req: CompileRequest;
  signal: AbortSignal;
  emit(event: CompileEvent): void;
  finish(r: CompileResult): void;
  end(): void;
  fail(error: Error): void;
}

/** A compiler whose runs are driven by the test: nothing happens until a call emits or finishes. */
function controlledCompiler() {
  const calls: Call[] = [];
  const compiler: CompilerPort = {
    available: async () => ({ ok: true }),
    readArtifact: async () => null,
    compile(req, signal) {
      const queue: Array<{ event: CompileEvent } | { done: true } | { error: Error }> = [];
      let wake: (() => void) | null = null;
      const push = (item: (typeof queue)[number]) => {
        queue.push(item);
        wake?.();
      };
      calls.push({
        req,
        signal,
        emit: (event) => push({ event }),
        finish: (r) => {
          push({ event: { type: "finished", compileId: "adapter-id", result: r } });
          push({ done: true });
        },
        end: () => push({ done: true }),
        fail: (error) => push({ error }),
      });
      return (async function* () {
        for (;;) {
          const item = queue.shift();
          if (item === undefined) {
            await new Promise<void>((resolve) => (wake = resolve));
            continue;
          }
          if ("done" in item) return;
          if ("error" in item) throw item.error;
          yield item.event;
        }
      })();
    },
  };
  return { compiler, calls };
}

const main = (name: string) => name as RelPath;
const req = (name = "main.tex", stopOnFirstError = false): CompileRequest => ({ main: main(name), stopOnFirstError });

function setup() {
  const { compiler, calls } = controlledCompiler();
  let n = 0;
  const coordinator = createCompileCoordinator({ compiler, newId: () => `c${(n += 1)}` });
  const events: CoordinatorEvent[] = [];
  coordinator.subscribe((event) => events.push(event));
  return { coordinator, calls, events };
}

const typesOf = (events: CoordinatorEvent[]) => events.map((event) => `${event.type}:${event.compileId}`);

describe("one run at a time", () => {
  it("starts the first request at once and reports it as not queued", async () => {
    const { coordinator, calls, events } = setup();
    expect(coordinator.request(req())).toEqual({ compileId: "c1", queued: false });
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.req).toEqual(req());
    expect(typesOf(events)).toEqual(["started:c1"]);
    expect(coordinator.status().running).toEqual({ compileId: "c1" });
  });

  it("queues requests made during a run as one follow-up and never runs two at once", async () => {
    const { coordinator, calls } = setup();
    coordinator.request(req("a.tex"));
    expect(coordinator.request(req("b.tex"))).toEqual({ compileId: "c2", queued: true });
    expect(coordinator.request(req("c.tex"))).toEqual({ compileId: "c3", queued: true });
    expect(coordinator.request(req("d.tex", true))).toEqual({ compileId: "c4", queued: true });
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(coordinator.status().queued).toEqual({ compileId: "c4" });

    calls[0]!.finish(result("success"));
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.req).toEqual(req("d.tex", true));
    expect(coordinator.status().queued).toBeNull();
    calls[1]!.finish(result("success"));
    await coordinator.idle();
    expect(calls).toHaveLength(2);
  });

  it("starts the follow-up only after the first run has finished", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req("a.tex"));
    coordinator.request(req("b.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.finish(result("success"));
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect(typesOf(events)).toEqual(["started:c1", "queued:c2", "finished:c1", "started:c2"]);
  });

  it("accepts a new request after everything finished and runs it at once", async () => {
    const { coordinator, calls } = setup();
    coordinator.request(req());
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.finish(result("success"));
    await coordinator.idle();
    expect(coordinator.request(req("again.tex"))).toEqual({ compileId: "c2", queued: false });
    await vi.waitFor(() => expect(calls).toHaveLength(2));
  });
});

describe("announcing the queue", () => {
  it("publishes the queued follow-up, a replacement of it, and its start", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req("a.tex"));
    coordinator.request(req("b.tex"));
    coordinator.request(req("c.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.finish(result("success"));
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect(typesOf(events)).toEqual(["started:c1", "queued:c2", "queued:c3", "finished:c1", "started:c3"]);
    calls[1]!.finish(result("success"));
    await coordinator.idle();
  });

  it("announces nothing for a request that starts at once and nothing when cancel finds no queued request", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req("a.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    coordinator.cancel();
    calls[0]!.finish(result("cancelled"));
    await coordinator.idle();
    expect(typesOf(events)).toEqual(["started:c1", "finished:c1"]);
  });
});

describe("cancel", () => {
  it("aborts the running compile and discards the queued follow-up", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req("a.tex"));
    coordinator.request(req("b.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));

    expect(coordinator.cancel()).toEqual({ cancelled: true });
    expect(calls[0]?.signal.aborted).toBe(true);
    expect(coordinator.status().queued).toBeNull();

    calls[0]!.finish(result("cancelled"));
    await coordinator.idle();
    expect(calls).toHaveLength(1);
    expect(typesOf(events)).toEqual(["started:c1", "queued:c2", "dequeued:c2", "finished:c1"]);
    expect(coordinator.status().last).toEqual({ compileId: "c1", result: result("cancelled") });
  });

  it("does nothing when nothing is running", () => {
    const { coordinator } = setup();
    expect(coordinator.cancel()).toEqual({ cancelled: false });
  });

  it("reports cancelled itself when the compiler stops without a result after the abort", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req());
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    coordinator.cancel();
    calls[0]!.end();
    await coordinator.idle();
    const finished = events.find((event) => event.type === "finished");
    expect(finished).toMatchObject({ compileId: "c1", result: { status: "cancelled" } });
  });

  it("lets a request made after the cancel run once the cancelled run ended", async () => {
    const { coordinator, calls } = setup();
    coordinator.request(req("a.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    coordinator.cancel();
    expect(coordinator.request(req("b.tex"))).toEqual({ compileId: "c2", queued: true });
    calls[0]!.finish(result("cancelled"));
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.req.main).toBe("b.tex");
  });
});

describe("events and status", () => {
  it("forwards phases and the result under the coordinator's id and remembers the last result", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req());
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.emit({ type: "started", compileId: "adapter-id" });
    calls[0]!.emit({ type: "phase", phase: "downloading" });
    calls[0]!.emit({ type: "phase", phase: "typesetting" });
    const done = result("success", { pdfRev: "7" });
    calls[0]!.finish(done);
    await coordinator.idle();

    expect(events).toEqual([
      { type: "started", compileId: "c1" },
      { type: "phase", compileId: "c1", phase: "downloading" },
      { type: "phase", compileId: "c1", phase: "typesetting" },
      { type: "finished", compileId: "c1", result: done },
    ]);
    expect(coordinator.status()).toEqual({ running: null, queued: null, last: { compileId: "c1", result: done } });
  });

  it("turns a compiler that throws into a failed result and goes on with the queue", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req("a.tex"));
    coordinator.request(req("b.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.fail(new Error("disk exploded"));
    await vi.waitFor(() => expect(calls).toHaveLength(2));

    const failed = events.find((event) => event.type === "finished");
    expect(failed).toMatchObject({ compileId: "c1", result: { status: "failed" } });
    expect(failed?.type === "finished" && failed.result.diagnostics[0]).toMatchObject({
      severity: "error",
      source: "caztor",
      detail: "disk exploded",
    });
  });

  it("reports failed when the compiler ends without a result and was not cancelled", async () => {
    const { coordinator, calls, events } = setup();
    coordinator.request(req());
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.end();
    await coordinator.idle();
    expect(events.at(-1)).toMatchObject({ type: "finished", result: { status: "failed" } });
  });

  it("stops sending to a listener that unsubscribed and survives a listener that throws", async () => {
    const { coordinator, calls } = setup();
    const kept: string[] = [];
    const unsubscribe = coordinator.subscribe((event) => kept.push(event.type));
    coordinator.subscribe(() => {
      throw new Error("bad listener");
    });
    coordinator.request(req());
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    unsubscribe();
    calls[0]!.finish(result("success"));
    await coordinator.idle();
    expect(kept).toEqual(["started"]);
    expect(coordinator.status().last?.result.status).toBe("success");
  });
});

describe("shutdown", () => {
  it("cancels what runs and resolves once the run ended", async () => {
    const { coordinator, calls } = setup();
    coordinator.request(req("a.tex"));
    coordinator.request(req("b.tex"));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    const closing = coordinator.shutdown();
    expect(calls[0]?.signal.aborted).toBe(true);
    calls[0]!.finish(result("cancelled"));
    await closing;
    expect(calls).toHaveLength(1);
    expect(coordinator.status().running).toBeNull();
  });
});
