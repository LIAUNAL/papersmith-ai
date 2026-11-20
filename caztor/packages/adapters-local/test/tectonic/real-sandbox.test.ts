import { mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { inflateSync } from "node:zlib";
import type { CompileEvent, CompileRequest, RelPath } from "@caztor/core";
import { afterEach, describe, expect, it } from "vitest";
import type { Clock } from "../../src/infra.ts";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../src/node-infra.ts";
import { createProjectStore } from "../../src/project-store.ts";
import { createSandbox } from "../../src/sandbox.ts";
import { createTectonicCompiler } from "../../src/tectonic/compiler.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function folder(parent: string, prefix: string): string {
  const dir = realpathSync(mkdtempSync(join(parent, prefix)));
  dirs.push(dir);
  return dir;
}

function write(root: string, files: Record<string, string>): void {
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(join(root, name, ".."), { recursive: true });
    writeFileSync(join(root, name), text);
  }
}

interface Options {
  env?: Record<string, string | undefined>;
  clock?: Clock;
}

function compilerFor(root: string, options: Options = {}) {
  const env = { ...process.env, ...options.env };
  const clock = options.clock ?? systemClock;
  const spawner = createNodeSpawner();
  const sandbox = createSandbox({ spawner, clock, fs: nodeFileSystem, root, env });
  const compiler = createTectonicCompiler({
    spawner,
    clock,
    fs: nodeFileSystem,
    root,
    store: createProjectStore({ fs: nodeFileSystem, root }),
    parentEnv: env,
    sandbox,
  });
  return { compiler, sandbox };
}

const req = (main: string, sandboxed: boolean): CompileRequest => ({ main: main as RelPath, stopOnFirstError: false, sandboxed });

async function run(compiler: ReturnType<typeof compilerFor>["compiler"], request: CompileRequest, signal = new AbortController().signal) {
  const events: CompileEvent[] = [];
  for await (const event of compiler.compile(request, signal)) events.push(event);
  const finished = events.find((event) => event.type === "finished");
  if (finished?.type !== "finished") throw new Error("no finished event");
  return finished.result;
}

/** Processes whose command line mentions `needle`, found through /proc so no extra tool is needed. */
function processesMentioning(needle: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync("/proc")) {
    if (!/^\d+$/.test(entry) || Number(entry) === process.pid) continue;
    try {
      const command = readFileSync(`/proc/${entry}/cmdline`, "utf8").replaceAll("\0", " ");
      if (command.includes(needle)) found.push(`${entry}: ${command.slice(0, 80)}`);
    } catch {
      // The process ended while it was being read.
    }
  }
  return found;
}

/**
 * The PDF with every compressed stream expanded and the creation date, modification date and document id removed,
 * which are the only parts that differ between two runs (the dates sit inside compressed object streams).
 */
function stable(pdf: Uint8Array): string {
  const raw = Buffer.from(pdf).toString("latin1");
  const expanded = raw.replace(/stream\r?\n([\s\S]*?)\r?\nendstream/g, (whole, body: string) => {
    try {
      return `stream\n${inflateSync(Buffer.from(body, "latin1")).toString("latin1")}\nendstream`;
    } catch {
      return whole;
    }
  });
  return expanded
    .replace(/\/(CreationDate|ModDate) ?\([^)]*\)/g, "")
    .replace(/\/ID ?\[[^\]]*\]/g, "")
    .replace(/D:\d{14}[^)>\s]*/g, "")
    .replace(/<xmp:(CreateDate|ModifyDate|MetadataDate)>[^<]*<\/xmp:\1>/g, "")
    .replace(/<xmpMM:(DocumentID|InstanceID)>[^<]*<\/xmpMM:\1>/g, "");
}

const MAIN = "\\documentclass{article}\n\\begin{document}\nCited \\cite{knuth84}. \\input{chapters/one}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n";
const BIB = "@book{knuth84, author={Donald Knuth}, title={The TeXbook}, publisher={Addison-Wesley}, year={1984}}\n";
const PROJECT = { "main.tex": MAIN, "chapters/one.tex": "Chapter one text.\n", "refs.bib": BIB };

describe.skipIf(process.env["CAZTOR_REAL_BIN"] !== "1")("real bubblewrap sandbox (opt-in)", () => {
  it("probes as available on this machine", async () => {
    const { sandbox } = compilerFor(folder(tmpdir(), "caztor-sbx-"));
    const probe = await sandbox.probe();
    expect(probe.reason).toBeUndefined();
    expect(probe.ok).toBe(true);
    expect(probe.version).toMatch(/Tectonic \d/);
  }, 60_000);

  it("compiles a multi-file BibTeX project to the same PDF as the unsandboxed run", async () => {
    const plainRoot = folder(tmpdir(), "caztor-plain-");
    const boxedRoot = folder(tmpdir(), "caztor-boxed-");
    write(plainRoot, PROJECT);
    write(boxedRoot, PROJECT);
    const plain = await run(compilerFor(plainRoot).compiler, req("main.tex", false));
    const boxed = compilerFor(boxedRoot);
    const result = await run(boxed.compiler, req("main.tex", true));
    expect(plain.status).toBe("success");
    expect(result.status).toBe("success");
    const [a, b] = [await compilerFor(plainRoot).compiler.readArtifact("pdf"), await boxed.compiler.readArtifact("pdf")];
    expect(a).not.toBeNull();
    expect(stable(b!)).toBe(stable(a!));

    // Control: the comparison would notice a different document.
    const otherRoot = folder(tmpdir(), "caztor-other-");
    write(otherRoot, { ...PROJECT, "chapters/one.tex": "A different chapter, with more words in it.\n" });
    const other = compilerFor(otherRoot).compiler;
    expect((await run(other, req("main.tex", false))).status).toBe("success");
    expect(stable((await other.readArtifact("pdf"))!)).not.toBe(stable(a!));
  }, 180_000);

  it("cannot read an absolute path in the home folder or a ../ path outside the project, which work without it", async () => {
    const outside = folder(tmpdir(), "caztor-outside-");
    const home = folder(homedir(), ".caztor-sandbox-test-");
    writeFileSync(join(home, "secret.tex"), "HOMESECRET\n");
    writeFileSync(join(outside, "neighbour.tex"), "NEIGHBOUR\n");
    const root = join(outside, "project");
    write(root, { "home.tex": `\\documentclass{article}\\begin{document}\\input{${join(home, "secret")}}\\end{document}\n` });
    write(root, { "up.tex": "\\documentclass{article}\\begin{document}\\input{../neighbour}\\end{document}\n" });
    const { compiler } = compilerFor(root);

    expect((await run(compiler, req("home.tex", false))).status).toBe("success");
    expect((await run(compiler, req("up.tex", false))).status).toBe("success");
    const boxedHome = await run(compiler, req("home.tex", true));
    expect(boxedHome.status).not.toBe("success");
    expect(boxedHome.pdfRev).toBeNull();
    const boxedUp = await run(compiler, req("up.tex", true));
    expect(boxedUp.status).not.toBe("success");
    expect(boxedUp.pdfRev).toBeNull();
  }, 180_000);

  it("downloads packages on a first run with an empty cache, inside the sandbox", async () => {
    const cache = folder(tmpdir(), "caztor-cache-");
    const root = folder(tmpdir(), "caztor-first-");
    write(root, PROJECT);
    const { compiler } = compilerFor(root, { env: { TECTONIC_CACHE_DIR: cache } });
    const result = await run(compiler, req("main.tex", true));
    expect(result.status).toBe("success");
    expect(readdirSync(cache).length).toBeGreaterThan(0);
  }, 580_000);

  it("kills everything on cancel, leaving no bwrap or tectonic process", async () => {
    const cache = folder(tmpdir(), "caztor-cache-");
    const root = folder(tmpdir(), "caztor-cancel-");
    write(root, PROJECT);
    const { compiler } = compilerFor(root, { env: { TECTONIC_CACHE_DIR: cache } });
    const controller = new AbortController();
    const running = run(compiler, req("main.tex", true), controller.signal);
    const deadline = Date.now() + 30_000;
    while (processesMentioning(root).length === 0 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 100));
    expect(processesMentioning(root).length).toBeGreaterThan(0);
    controller.abort();
    expect((await running).status).toBe("cancelled");
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(processesMentioning(root)).toEqual([]);
  }, 120_000);

  it("kills everything at the time limit, leaving no bwrap or tectonic process", async () => {
    const cache = folder(tmpdir(), "caztor-cache-");
    const root = folder(tmpdir(), "caztor-limit-");
    write(root, PROJECT);
    // The limits are scaled to a few seconds; the first-run download would take far longer.
    const quick: Clock = { now: () => systemClock.now(), setTimeout: (fn, ms) => systemClock.setTimeout(fn, ms >= 100_000 ? 4_000 : ms) };
    const { compiler } = compilerFor(root, { env: { TECTONIC_CACHE_DIR: cache }, clock: quick });
    expect((await run(compiler, req("main.tex", true))).status).toBe("timed-out");
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(processesMentioning(root)).toEqual([]);
  }, 120_000);
});
