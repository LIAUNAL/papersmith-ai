import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { CompileEvent, CompileRequest, CompilerPort, RelPath } from "@caztor/core";
import { afterEach, describe, expect, it } from "vitest";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../src/node-infra.ts";
import { confirmRecipe, withBuildRecipe } from "../../src/tectonic/build-recipe.ts";

const KEY = new TextEncoder().encode("k".repeat(43));
const trustKey = async () => KEY;
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/** A project with a recipe the host confirmed, unless `confirmed` is false. */
async function project(recipe?: unknown, confirmed = true): Promise<string> {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-recipe-")));
  dirs.push(root);
  mkdirSync(join(root, "paper"));
  writeFileSync(join(root, "paper", "main.tex"), "blocks");
  if (recipe !== undefined) {
    mkdirSync(join(root, ".caztor"));
    writeFileSync(join(root, ".caztor", "build.json"), typeof recipe === "string" ? recipe : JSON.stringify(recipe));
    if (confirmed && typeof recipe !== "string") expect((await confirmRecipe({ fs: nodeFileSystem, root, trustKey })).ok).toBe(true);
  }
  return root;
}

/** Records what it was asked to compile and finishes successfully. */
function innerCompiler(): CompilerPort & { asked: CompileRequest[] } {
  const asked: CompileRequest[] = [];
  return {
    asked,
    available: async () => ({ ok: true }),
    readArtifact: async () => null,
    async *compile(req) {
      asked.push(req);
      yield { type: "started", compileId: "inner" };
      yield { type: "finished", compileId: "inner", result: { status: "success", pdfRev: "r1", diagnostics: [], durationMs: 1, logAvailable: true } };
    },
  };
}

async function run(compiler: CompilerPort, main: string, extra: Partial<CompileRequest> = {}, signal = new AbortController().signal): Promise<CompileEvent[]> {
  const events: CompileEvent[] = [];
  for await (const event of compiler.compile({ main: main as RelPath, stopOnFirstError: false, ...extra }, signal)) events.push(event);
  return events;
}

const finished = (events: CompileEvent[]) => events.find((event) => event.type === "finished") as Extract<CompileEvent, { type: "finished" }>;

function wrap(root: string, inner: CompilerPort, timeoutMs?: number) {
  return withBuildRecipe(inner, {
    fs: nodeFileSystem,
    spawner: createNodeSpawner(),
    clock: systemClock,
    root,
    parentEnv: { PATH: process.env["PATH"], HOME: root, TMPDIR: tmpdir(), OPENAI_API_KEY: "secret" },
    trustKey,
    ...(timeoutMs === undefined ? {} : { timeoutMs }),
  });
}

const node = process.execPath;

describe("build recipe (.caztor/build.json)", () => {
  const touching = { when: ["paper/main.tex"], before: [node, "-e", "require('fs').writeFileSync('ran', '')"], root: "paper/preview.tex" };

  it("does not run a recipe the host has not confirmed on this computer, and says how to confirm it", async () => {
    const root = await project(touching, false);
    const inner = innerCompiler();
    const result = finished(await run(wrap(root, inner), "paper/main.tex")).result;
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toContain(`npm start -- trust-build "${root}"`);
    expect(inner.asked).toEqual([]);
    expect(() => readFileSync(join(root, "ran"))).toThrow();
  });

  it("does not run a recipe changed after it was confirmed, or one sealed with another computer's key", async () => {
    const changed = await project(touching);
    writeFileSync(join(changed, ".caztor", "build.json"), JSON.stringify({ ...touching, before: [node, "-e", "require('fs').writeFileSync('ran', 'evil')"] }));
    const foreign = await project();
    mkdirSync(join(foreign, ".caztor"));
    writeFileSync(join(foreign, ".caztor", "build.json"), JSON.stringify(touching));
    expect((await confirmRecipe({ fs: nodeFileSystem, root: foreign, trustKey: async () => new TextEncoder().encode("x".repeat(43)) })).ok).toBe(true);
    for (const root of [changed, foreign]) {
      const inner = innerCompiler();
      expect(finished(await run(wrap(root, inner), "paper/main.tex")).result.status).toBe("failed");
      expect(() => readFileSync(join(root, "ran"))).toThrow();
    }
  });

  it("runs the declared step in the project folder, then compiles the declared root instead of the requested file", async () => {
    const root = await project({
      when: ["paper/main.tex"],
      before: [node, "-e", "require('fs').writeFileSync('paper/assembled.txt', process.cwd() + '|' + (process.env.OPENAI_API_KEY ?? 'no key'))"],
      root: "paper/preview.tex",
    });
    const inner = innerCompiler();
    const events = await run(wrap(root, inner), "paper/main.tex");
    expect(readFileSync(join(root, "paper", "assembled.txt"), "utf8")).toBe(`${root}|no key`);
    expect(inner.asked.map((req) => req.main)).toEqual(["paper/preview.tex"]);
    expect(finished(events).result.status).toBe("success");
  });

  it("compiles any other file as before, without running the step", async () => {
    const root = await project({ when: ["paper/main.tex"], before: [node, "-e", "require('fs').writeFileSync('ran', '')"], root: "paper/preview.tex" });
    const inner = innerCompiler();
    await run(wrap(root, inner), "paper/other.tex");
    expect(inner.asked.map((req) => req.main)).toEqual(["paper/other.tex"]);
    expect(() => readFileSync(join(root, "ran"))).toThrow();
  });

  it("without a recipe, nothing changes", async () => {
    const root = await project();
    const inner = innerCompiler();
    await run(wrap(root, inner), "paper/main.tex");
    expect(inner.asked.map((req) => req.main)).toEqual(["paper/main.tex"]);
  });

  it("reports a failing step with its exit code and output, and does not compile", async () => {
    const root = await project({ when: ["paper/main.tex"], before: [node, "-e", "console.error('KeyError: abstract'); process.exit(3)"], root: "paper/preview.tex" });
    const inner = innerCompiler();
    const result = finished(await run(wrap(root, inner), "paper/main.tex")).result;
    expect(inner.asked).toEqual([]);
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toContain("exit code 3");
    expect(result.diagnostics[0]?.detail).toContain("KeyError: abstract");
  });

  it("stops a step that runs too long", async () => {
    const root = await project({ when: ["paper/main.tex"], before: [node, "-e", "setTimeout(() => {}, 60000)"], root: "paper/preview.tex" });
    const inner = innerCompiler();
    const result = finished(await run(wrap(root, inner, 300), "paper/main.tex")).result;
    expect(inner.asked).toEqual([]);
    expect(result.status).toBe("timed-out");
  });

  it("stops the step when the compile is cancelled", async () => {
    const root = await project({ when: ["paper/main.tex"], before: [node, "-e", "setTimeout(() => {}, 60000)"], root: "paper/preview.tex" });
    const inner = innerCompiler();
    const abort = new AbortController();
    setTimeout(() => abort.abort(), 200);
    const result = finished(await run(wrap(root, inner), "paper/main.tex", {}, abort.signal)).result;
    expect(result.status).toBe("cancelled");
    expect(inner.asked).toEqual([]);
  });

  it("refuses to run the step in a sandboxed compile", async () => {
    const root = await project({ when: ["paper/main.tex"], before: [node, "-e", "require('fs').writeFileSync('ran', '')"], root: "paper/preview.tex" });
    const inner = innerCompiler();
    const result = finished(await run(wrap(root, inner), "paper/main.tex", { sandboxed: true })).result;
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toContain("sandbox");
    expect(inner.asked).toEqual([]);
    expect(() => readFileSync(join(root, "ran"))).toThrow();
  });

  it("reports an invalid recipe instead of compiling", async () => {
    for (const recipe of ["{not json", { when: ["paper/main.tex"], before: [], root: "paper/preview.tex" }, { when: ["paper/main.tex"], before: ["python3"], root: "../outside.tex" }]) {
      const root = await project(recipe, false);
      const inner = innerCompiler();
      const result = finished(await run(wrap(root, inner), "paper/main.tex")).result;
      expect(result.status).toBe("failed");
      expect(result.diagnostics[0]?.message).toContain(".caztor/build.json");
      expect(inner.asked).toEqual([]);
    }
  });

  it("never follows links: a seal or recipe that is a link is refused, and the linked file is left alone", async () => {
    const { symlinkSync } = await import("node:fs");
    const root = await project(touching, false);
    const victim = join(root, "victim.txt");
    writeFileSync(victim, "keep me");
    symlinkSync(victim, join(root, ".caztor", "build.seal"));
    const confirmed = await confirmRecipe({ fs: nodeFileSystem, root, trustKey });
    expect(confirmed.ok).toBe(false);
    expect(readFileSync(victim, "utf8")).toBe("keep me");
    const inner = innerCompiler();
    expect(finished(await run(wrap(root, inner), "paper/main.tex")).result.status).toBe("failed");
    expect(inner.asked).toEqual([]);
  });
});

