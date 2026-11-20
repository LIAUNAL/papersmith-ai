import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createCompileCoordinator, type CompileEvent, type CompileRequest, type CompileResult, type CompilerPort } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import { cleanupProjects, harness, type Harness } from "./support.ts";

cleanupProjects();

const ok = (extra: Partial<CompileResult> = {}): CompileResult => ({
  status: "success",
  pdfRev: "5",
  diagnostics: [],
  durationMs: 12,
  logAvailable: true,
  ...extra,
});

interface Run {
  req: CompileRequest;
  signal: AbortSignal;
  phase(phase: "downloading" | "typesetting" | "bibliography" | "finalizing"): void;
  finish(result: CompileResult): void;
}

/** A compiler the test drives by hand, with settable artifacts and availability. */
function fakeCompiler(state: { available: { ok: boolean; version?: string }; pdf: Uint8Array | null; log: Uint8Array | null }) {
  const runs: Run[] = [];
  const artifactReads: string[] = [];
  const compiler: CompilerPort = {
    available: async () => state.available,
    async readArtifact(kind) {
      artifactReads.push(kind);
      return kind === "pdf" ? state.pdf : state.log;
    },
    compile(req, signal) {
      const queue: CompileEvent[] = [];
      let wake: (() => void) | null = null;
      let done = false;
      const push = (event: CompileEvent) => {
        queue.push(event);
        wake?.();
      };
      runs.push({
        req,
        signal,
        phase: (phase) => push({ type: "phase", phase }),
        finish: (result) => {
          push({ type: "finished", compileId: "adapter", result });
          done = true;
        },
      });
      return (async function* () {
        for (;;) {
          const next = queue.shift();
          if (next !== undefined) {
            yield next;
            if (next.type === "finished") return;
          } else if (done) return;
          else await new Promise<void>((resolve) => (wake = resolve));
        }
      })();
    },
  };
  return { compiler, runs, artifactReads };
}

function withCompile(files: Record<string, string> = { "main.tex": "\\documentclass{article}" }) {
  const state = { available: { ok: true, version: "0.17.0" } as { ok: boolean; version?: string }, pdf: null as Uint8Array | null, log: null as Uint8Array | null };
  const fake = fakeCompiler(state);
  const coordinator = createCompileCoordinator({ compiler: fake.compiler, newId: (() => { let n = 0; return () => `c${(n += 1)}`; })() });
  const h: Harness = harness({ compile: { coordinator, compiler: fake.compiler } });
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(dirname(join(h.root, name)), { recursive: true });
    writeFileSync(join(h.root, name), text);
  }
  return { h, state, coordinator, ...fake };
}

describe("POST /api/compile", () => {
  it("starts the compile of main.tex with the saved stop-on-error setting and answers 202 with the id", async () => {
    const { h, runs } = withCompile();
    const response = await h.call("POST", "/api/compile", { body: {} });
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ compileId: "c1", queued: false });
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    expect(runs[0]?.req).toEqual({ main: "main.tex", stopOnFirstError: false, sandboxed: false });
  });

  it("follows the persisted toggle and the configured main file", async () => {
    const { h, runs } = withCompile({ "main.tex": "x", "paper/thesis.tex": "y" });
    await h.deps.state.update({ stopOnFirstError: true, mainFile: "paper/thesis.tex" as never });
    await h.call("POST", "/api/compile", { body: {} });
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    expect(runs[0]?.req).toEqual({ main: "paper/thesis.tex", stopOnFirstError: true, sandboxed: false });
  });

  it("accepts an empty body and a body that names the main file", async () => {
    const { h, runs } = withCompile({ "main.tex": "x", "other.tex": "y" });
    expect((await h.call("POST", "/api/compile", { body: "" })).status).toBe(202);
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    runs[0]!.finish(ok());
    expect((await h.call("POST", "/api/compile", { body: { main: "other.tex" } })).status).toBe(202);
    await vi.waitFor(() => expect(runs).toHaveLength(2));
    expect(runs[1]?.req.main).toBe("other.tex");
  });

  it("queues overlapping requests as one follow-up and runs nothing concurrently", async () => {
    const { h, runs, coordinator } = withCompile();
    expect(await (await h.call("POST", "/api/compile", { body: {} })).json()).toEqual({ compileId: "c1", queued: false });
    expect(await (await h.call("POST", "/api/compile", { body: {} })).json()).toEqual({ compileId: "c2", queued: true });
    expect(await (await h.call("POST", "/api/compile", { body: {} })).json()).toEqual({ compileId: "c3", queued: true });
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    expect(coordinator.status().queued).toEqual({ compileId: "c3" });
    runs[0]!.finish(ok());
    await vi.waitFor(() => expect(runs).toHaveLength(2));
    runs[1]!.finish(ok());
    await coordinator.idle();
    expect(runs).toHaveLength(2);
  });

  it.each([
    ["a path outside the project", { main: "../outside.tex" }],
    ["a name that would read as an option", { main: "-Z shell-escape.tex" }],
    ["a reserved path", { main: ".caztor/x.tex" }],
    ["a value that is not a string", { main: 7 }],
  ])("refuses %s with 400 and starts nothing", async (_name, body) => {
    const { h, runs } = withCompile();
    const response = await h.call("POST", "/api/compile", { body });
    expect(response.status).toBe(400);
    expect(((await response.json()) as { error: string }).error).toBe("invalid_main");
    expect(runs).toEqual([]);
  });

  it("refuses malformed JSON with 400", async () => {
    const { h, runs } = withCompile();
    const response = await h.call("POST", "/api/compile", { body: "{not json" });
    expect(response.status).toBe(400);
    expect(runs).toEqual([]);
  });

  it("says when the main file does not exist, and when no main file can be chosen", async () => {
    const missing = withCompile();
    const absent = await missing.h.call("POST", "/api/compile", { body: { main: "gone.tex" } });
    expect(absent.status).toBe(404);
    expect(((await absent.json()) as { error: string }).error).toBe("main_not_found");

    const ambiguous = withCompile({ "a.tex": "x", "b.tex": "y" });
    const none = await ambiguous.h.call("POST", "/api/compile", { body: {} });
    expect(none.status).toBe(409);
    const body = (await none.json()) as { error: string; message: string };
    expect(body.error).toBe("no_main_file");
    expect(body.message).toMatch(/main file/i);
  });

  it("uses the only .tex file at the top level when there is no main.tex", async () => {
    const { h, runs } = withCompile({ "thesis.tex": "x", "refs.bib": "y" });
    expect((await h.call("POST", "/api/compile", { body: {} })).status).toBe(202);
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    expect(runs[0]?.req.main).toBe("thesis.tex");
  });

  it("answers with a readable error instead of crashing when the engine is missing", async () => {
    const { h, state, runs } = withCompile();
    state.available = { ok: false };
    const response = await h.call("POST", "/api/compile", { body: {} });
    expect(response.status).toBe(503);
    const body = (await response.json()) as { error: string; message: string };
    expect(body.error).toBe("engine_unavailable");
    expect(body.message).toMatch(/tectonic/i);
    expect(runs).toEqual([]);
  });

  it("answers 503 when no compiler is wired", async () => {
    const h = harness();
    const response = await h.call("POST", "/api/compile", { body: {} });
    expect(response.status).toBe(503);
  });

  it("is refused without the launch token, and with a non-JSON content type", async () => {
    const { h, runs } = withCompile();
    expect((await h.call("POST", "/api/compile", { body: {}, headers: { "x-caztor-token": "stale" } })).status).toBe(401);
    expect((await h.call("POST", "/api/compile", { body: "x", headers: { "content-type": "text/plain" } })).status).toBe(415);
    expect(runs).toEqual([]);
  });
});

describe("POST /api/compile/cancel and GET /api/compile/status", () => {
  it("cancels the running compile, discards the queued one and reports it in the status", async () => {
    const { h, runs, coordinator } = withCompile();
    await h.call("POST", "/api/compile", { body: {} });
    await h.call("POST", "/api/compile", { body: {} });
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    expect(await (await h.call("GET", "/api/compile/status")).json()).toEqual({
      running: { compileId: "c1" },
      queued: { compileId: "c2" },
      last: null,
      pdfAvailable: false,
    });

    const cancelled = await h.call("POST", "/api/compile/cancel", { body: {} });
    expect(cancelled.status).toBe(200);
    expect(await cancelled.json()).toEqual({ cancelled: true });
    expect(runs[0]?.signal.aborted).toBe(true);

    const result = ok({ status: "cancelled", pdfRev: null, logAvailable: false });
    runs[0]!.finish(result);
    await coordinator.idle();
    expect(runs).toHaveLength(1);
    expect(await (await h.call("GET", "/api/compile/status")).json()).toEqual({
      running: null,
      queued: null,
      last: { compileId: "c1", result },
      pdfAvailable: false,
    });
  });

  it("says a preview PDF exists even when this server run has not compiled yet (after a restart)", async () => {
    const { h, state } = withCompile();
    state.pdf = new TextEncoder().encode("%PDF-1.5 old");
    expect(await (await h.call("GET", "/api/compile/status")).json()).toEqual({
      running: null,
      queued: null,
      last: null,
      pdfAvailable: true,
    });
  });

  it("reports that nothing was cancelled when nothing runs", async () => {
    const { h } = withCompile();
    expect(await (await h.call("POST", "/api/compile/cancel", { body: {} })).json()).toEqual({ cancelled: false });
  });

  it("requires the token for the status", async () => {
    const { h } = withCompile();
    expect((await h.call("GET", "/api/compile/status", { headers: { "x-caztor-token": "no" } })).status).toBe(401);
  });
});

describe("GET /api/compile/pdf and /log", () => {
  const PDF = new TextEncoder().encode("%PDF-1.5\nbody");

  it("serves the promoted preview as application/pdf, uncached, with the security headers", async () => {
    const { h, state } = withCompile();
    state.pdf = PDF;
    const response = await h.call("GET", "/api/compile/pdf?rev=5");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("content-security-policy")).toContain("default-src 'self'");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(PDF);
  });

  it("is a 404 with a readable message while no preview exists", async () => {
    const { h } = withCompile();
    const response = await h.call("GET", "/api/compile/pdf");
    expect(response.status).toBe(404);
    expect(((await response.json()) as { error: string }).error).toBe("no_pdf");
  });

  it("serves only the promoted preview, whatever the query says", async () => {
    const { h, state, artifactReads } = withCompile();
    state.pdf = PDF;
    for (const query of ["?rev=../../etc/passwd", "?path=/etc/passwd", "?rev=..%2f..%2fsecret&file=main.tex", "/../../../etc/passwd"]) {
      const response = await h.call("GET", `/api/compile/pdf${query}`);
      if (response.status === 200) expect(new Uint8Array(await response.arrayBuffer())).toEqual(PDF);
    }
    expect(new Set(artifactReads)).toEqual(new Set(["pdf"]));
  });

  it("requires the launch token", async () => {
    const { h, state } = withCompile();
    state.pdf = PDF;
    expect((await h.call("GET", "/api/compile/pdf", { headers: { "x-caztor-token": "stale" } })).status).toBe(401);
    expect((await h.call("GET", "/api/compile/pdf", { headers: { host: "evil.example" } })).status).toBe(403);
  });

  it("serves the log as plain text and 404s when there is none", async () => {
    const { h, state } = withCompile();
    expect((await h.call("GET", "/api/compile/log")).status).toBe(404);
    state.log = new TextEncoder().encode("(main.tex\n! Undefined control sequence.\n");
    const response = await h.call("GET", "/api/compile/log");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/plain; charset=utf-8");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).toContain("Undefined control sequence");
  });
});

describe("compile events on /api/events", () => {
  it("publishes compile.started, compile.phase and compile.finished with the request's id", async () => {
    const { h, runs } = withCompile();
    const stream = await h.call("GET", "/api/events");
    const reader = stream.body!.getReader();
    const decoder = new TextDecoder();
    let received = "";
    const read = async (until: string) => {
      while (!received.includes(until)) received += decoder.decode((await reader.read()).value);
    };

    await h.call("POST", "/api/compile", { body: {} });
    await vi.waitFor(() => expect(runs).toHaveLength(1));
    runs[0]!.phase("downloading");
    const result = ok({ pdfRev: "9" });
    runs[0]!.finish(result);
    await read("event: compile.finished");
    await reader.cancel();

    const frames = received.split("\n\n").filter((frame) => frame.includes("event: compile."));
    const parsed = frames.map((frame) => ({
      event: /event: (\S+)/.exec(frame)![1],
      id: Number(/id: (\d+)/.exec(frame)![1]),
      data: JSON.parse(/data: (.*)/.exec(frame)![1]!) as unknown,
    }));
    expect(parsed.map((frame) => frame.event)).toEqual(["compile.started", "compile.phase", "compile.finished"]);
    expect(parsed.map((frame) => frame.data)).toEqual([
      { compileId: "c1" },
      { compileId: "c1", phase: "downloading" },
      { compileId: "c1", result },
    ]);
    expect(parsed[1]!.id).toBeGreaterThan(parsed[0]!.id);
  });
});

describe("compiles while collaborators can reach the server", () => {
  it("always run in the sandbox, whatever the project setting says", async () => {
    const t = withCompile();
    const h = harness({ compile: { coordinator: t.coordinator, compiler: t.compiler }, collaboratorMode: true, sandbox: async () => ({ ok: true, version: "bwrap" }) });
    writeFileSync(join(h.root, "main.tex"), "\\documentclass{article}");
    expect((await h.call("PATCH", "/api/settings", { body: { sandboxedCompile: false } })).status).toBe(200);

    expect((await h.call("POST", "/api/compile")).status).toBe(202);
    await vi.waitFor(() => expect(t.runs).toHaveLength(1));
    expect(t.runs[0]!.req.sandboxed).toBe(true);
  });

  it("are refused with a readable message when the sandbox cannot be used", async () => {
    const t = withCompile();
    const h = harness({ compile: { coordinator: t.coordinator, compiler: t.compiler }, collaboratorMode: true, sandbox: async () => ({ ok: false, reason: "Bubblewrap (bwrap) was not found." }) });
    writeFileSync(join(h.root, "main.tex"), "\\documentclass{article}");

    const refused = await h.call("POST", "/api/compile");
    expect(refused.status).toBe(409);
    expect(await refused.json()).toEqual({
      error: "sandbox_required",
      message: "Collaborators can reach this server, so every compile runs in the sandbox, and the sandbox cannot be used: Bubblewrap (bwrap) was not found.",
    });
    expect(t.runs).toEqual([]);
  });

  it("keep following the setting when nobody else can reach the server", async () => {
    const t = withCompile();
    expect((await t.h.call("POST", "/api/compile")).status).toBe(202);
    await vi.waitFor(() => expect(t.runs).toHaveLength(1));
    expect(t.runs[0]!.req.sandboxed).toBe(false);
  });
});
