import { existsSync, mkdtempSync, realpathSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { CompileEvent, CompileRequest, RelPath } from "@caztor/core";
import { afterEach, describe, expect, it } from "vitest";
import { createProjectStore } from "../../src/project-store.ts";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../../src/node-infra.ts";
import { createTectonicCompiler } from "../../src/tectonic/compiler.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function project(files: Record<string, string>) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-real-")));
  dirs.push(root);
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(join(root, name, ".."), { recursive: true });
    writeFileSync(join(root, name), text);
  }
  const compiler = createTectonicCompiler({
    spawner: createNodeSpawner(),
    clock: systemClock,
    fs: nodeFileSystem,
    root,
    store: createProjectStore({ fs: nodeFileSystem, root }),
    parentEnv: process.env,
  });
  return { root, compiler };
}

const req = (main: string, stopOnFirstError = false): CompileRequest => ({ main: main as RelPath, stopOnFirstError });

async function run(compiler: ReturnType<typeof project>["compiler"], request: CompileRequest, signal = new AbortController().signal) {
  const events: CompileEvent[] = [];
  for await (const event of compiler.compile(request, signal)) events.push(event);
  const finished = events.find((event) => event.type === "finished");
  if (finished?.type !== "finished") throw new Error("no finished event");
  return { events, result: finished.result };
}

const MAIN = "\\documentclass{article}\n\\begin{document}\nCited \\cite{knuth84}. \\input{sec}\n\\bibliographystyle{plain}\n\\bibliography{refs}\n\\end{document}\n";
const BIB = "@book{knuth84, author={Donald Knuth}, title={The TeXbook}, publisher={Addison-Wesley}, year={1984}}\n";

describe.skipIf(process.env["CAZTOR_REAL_BIN"] !== "1")("real tectonic (opt-in)", () => {
  it("reports the installed version", async () => {
    const { compiler } = project({});
    const probe = await compiler.available();
    expect(probe.ok).toBe(true);
    expect(probe.version).toMatch(/^\d+\.\d+/);
  });

  it("compiles a BibTeX project with an \\input to a PDF and promotes it", async () => {
    const { compiler } = project({ "main.tex": MAIN, "sec.tex": "Section text.\n", "refs.bib": BIB });
    const { events, result } = await run(compiler, req("main.tex"));
    expect(result.status).toBe("success");
    expect(result.pdfRev).not.toBeNull();
    expect(events.some((event) => event.type === "phase" && event.phase === "bibliography")).toBe(true);
    const pdf = await compiler.readArtifact("pdf");
    expect(new TextDecoder().decode(pdf!.slice(0, 4))).toBe("%PDF");
  });

  it("lists an undefined control sequence with file and line, keeps the PDF with errors, and halts when asked", async () => {
    const { compiler } = project({ "err.tex": "\\documentclass{article}\n\\begin{document}\n\\badmacro\nHello.\n\\end{document}\n" });
    const continued = await run(compiler, req("err.tex"));
    expect(continued.result.status).toBe("failed-with-errors");
    expect(continued.result.diagnostics).toContainEqual(
      expect.objectContaining({ severity: "error", file: "err.tex", line: 3, message: "Undefined control sequence" }),
    );
    expect(new TextDecoder().decode((await compiler.readArtifact("pdf"))!.slice(0, 4))).toBe("%PDF");

    const halted = await run(compiler, req("err.tex", true));
    expect(halted.result.status).toBe("failed");
    expect(halted.result.pdfRev).toBeNull();
    expect(halted.result.diagnostics[0]).toMatchObject({ file: "err.tex", line: 3 });
    // The earlier good preview is still served.
    expect(new TextDecoder().decode((await compiler.readArtifact("pdf"))!.slice(0, 4))).toBe("%PDF");
  });

  it("reads an undefined-reference warning with its line from the kept log, and still succeeds", async () => {
    const { compiler } = project({ "ref.tex": "\\documentclass{article}\n\\begin{document}\nSee \\ref{nolabel}.\n\\end{document}\n" });
    const { result } = await run(compiler, req("ref.tex"));
    expect(result.status).toBe("success");
    expect(result.diagnostics).toContainEqual(
      expect.objectContaining({ severity: "warning", file: "ref.tex", line: 3, source: "log" }),
    );
    expect(result.logAvailable).toBe(true);
  });

  it("does not run a shell command from \\write18", async () => {
    const { root, compiler } = project({
      "shell.tex": "\\documentclass{article}\n\\begin{document}\n\\immediate\\write18{touch pwned.txt}\nHi\n\\end{document}\n",
    });
    await run(compiler, req("shell.tex"));
    expect(existsSync(join(root, "pwned.txt"))).toBe(false);
    expect(existsSync(join(root, ".caztor/build/out/pwned.txt"))).toBe(false);
  });

  it("names a file read from outside the project", async () => {
    const { root, compiler } = project({ "main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{../outside-secret.tex}\n\\end{document}\n" });
    writeFileSync(join(root, "..", "outside-secret.tex"), "Secret.\n");
    dirs.push(join(root, "..", "outside-secret.tex"));
    const { result } = await run(compiler, req("main.tex"));
    expect(result.diagnostics.some((d) => d.severity === "warning" && /outside the project: .*outside-secret\.tex$/.test(d.message))).toBe(true);
  });

  it("cancels a run and leaves the previous preview in place", async () => {
    const { compiler } = project({ "main.tex": "\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n" });
    await run(compiler, req("main.tex"));
    const before = base64Of(await compiler.readArtifact("pdf"));
    const controller = new AbortController();
    controller.abort();
    const { result } = await run(compiler, req("main.tex"), controller.signal);
    expect(result.status).toBe("cancelled");
    expect(base64Of(await compiler.readArtifact("pdf"))).toBe(before);
  });
});

function base64Of(bytes: Uint8Array | null): string {
  return bytes === null ? "" : Buffer.from(bytes).toString("base64");
}
