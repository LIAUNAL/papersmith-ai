import type { CompileEvent } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import { buildCompileArgs, buildCompileEnv } from "../../src/tectonic/command.ts";
import { fixture } from "../support/fixtures.ts";
import { drain, finishedOf, harness, phasesOf, request, ROOT, text } from "../support/compile-harness.ts";

const PDF = "%PDF-1.5 fake";

describe("TectonicCompiler spawn", () => {
  it("runs tectonic from the project root with the built argv and the allowlisted environment, and no shell input", async () => {
    const h = harness();
    h.child({ stderr: [fixture("bibtex-success.stderr")], exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    await drain(h.compiler.compile(request(), new AbortController().signal));

    expect(h.calls).toHaveLength(1);
    expect(h.calls[0]).toEqual({
      file: "tectonic",
      args: buildCompileArgs(request()),
      cwd: ROOT,
      env: buildCompileEnv({ PATH: "/usr/bin", HOME: "/home/test" }),
    });
    expect(h.calls[0]?.env).not.toHaveProperty("SECRET_TOKEN");
  });

  it("passes stop-on-first-error through to the argv", async () => {
    const h = harness();
    h.child({ exit: { code: 1, signal: null } });
    await drain(h.compiler.compile(request({ stopOnFirstError: true }), new AbortController().signal));
    expect(h.calls[0]?.args).not.toContain("continue-on-errors");
  });

  it("refuses a main file with an unsafe name without spawning anything", async () => {
    const h = harness();
    const events = await drain(h.compiler.compile(request({ main: "-Z shell-escape.tex" as never }), new AbortController().signal));
    expect(h.calls).toEqual([]);
    const result = finishedOf(events);
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]).toMatchObject({ severity: "error", source: "caztor" });
    expect(result.diagnostics[0]?.message).toMatch(/main file/i);
  });

  it("reports a missing binary as engine-missing with a readable error, not a crash", async () => {
    const h = harness();
    h.child({ spawnError: "ENOENT" });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.status).toBe("engine-missing");
    expect(result.pdfRev).toBeNull();
    expect(result.diagnostics).toHaveLength(1);
    expect(result.diagnostics[0]).toMatchObject({ severity: "error", source: "caztor" });
    expect(result.diagnostics[0]?.message).toMatch(/tectonic.*not (found|installed)/i);
  });
});

describe("TectonicCompiler events and phases", () => {
  it("starts with a compile id, then reports each phase change once, then finishes under the same id", async () => {
    const h = harness();
    h.child({ stderr: [fixture("bibtex-success.stderr")], exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    const events = await drain(h.compiler.compile(request(), new AbortController().signal));

    expect(events[0]).toEqual({ type: "started", compileId: "c1" });
    expect(events.at(-1)).toMatchObject({ type: "finished", compileId: "c1" });
    expect(phasesOf(events)).toEqual(["typesetting", "bibliography", "typesetting", "finalizing"]);
  });

  it("reports a distinct downloading phase for the first-run download notes, once", async () => {
    const h = harness();
    h.child({ stderr: [fixture("first-run-download.stderr")], exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    const events = await drain(h.compiler.compile(request(), new AbortController().signal));
    expect(phasesOf(events)).toEqual(["downloading", "finalizing"]);
  });

  it("reads phases from output split anywhere, even inside a line", async () => {
    const h = harness();
    const stderr = "note: Running TeX ...\nnote: Running BibTeX on main.aux ...\n";
    h.child({ stderr: [stderr.slice(0, 30), stderr.slice(30)], exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    expect(phasesOf(await drain(h.compiler.compile(request(), new AbortController().signal)))).toEqual(["typesetting", "bibliography"]);
  });
});

describe("TectonicCompiler with the engine's output split over both streams", () => {
  // Observed with tectonic 0.17.0 when stdout and stderr are separate pipes: notes on stdout, warnings and errors on stderr.
  const notes = [
    "note: Running TeX ...\nnote: Rerunning TeX because \"err.aux\" changed ...\n",
    "note: Running xdvipdfmx ...\nnote: Writing `.caztor/build/out/err.pdf` (4.0 KiB)\n",
  ];

  it("reads phases from stdout and errors from stderr", async () => {
    const h = harness({ "/proj/err.tex": "x" });
    h.child(
      {
        stdout: notes,
        stderr: ["error: err.tex:3: Undefined control sequence\n", "warning: errors were issued by the TeX engine, but were ignored; use --print and/or --keep-logs for details.\n"],
        exit: { code: 0, signal: null },
      },
      { ".caztor/build/out/err.pdf": PDF },
    );
    const events = await drain(h.compiler.compile(request({ main: "err.tex" as never }), new AbortController().signal));

    expect(phasesOf(events)).toEqual(["typesetting", "finalizing"]);
    const result = finishedOf(events);
    expect(result.status).toBe("failed-with-errors");
    expect(result.diagnostics).toEqual([
      { severity: "error", file: "err.tex", line: 3, message: "Undefined control sequence", source: "stderr" },
    ]);
  });

  it("sees the downloading phase from stdout so the time limit extends", async () => {
    const h = harness();
    h.child({ stdout: ["note: downloading latex.ltx\n"] });
    const events: CompileEvent[] = [];
    const run = (async () => {
      for await (const event of h.compiler.compile(request(), new AbortController().signal)) events.push(event);
      return events;
    })();
    await vi.waitFor(() => expect(events.some((event) => event.type === "phase")).toBe(true));
    h.clock.advance(180_000);
    expect(h.fake.signals).toEqual([]);
    h.clock.advance(420_000);
    expect(h.fake.signals).toEqual(["SIGTERM"]);
    expect(phasesOf(await run)).toEqual(["downloading"]);
  });
});

describe("TectonicCompiler results", () => {
  it("succeeds with warnings from the kept log and serves the promoted PDF and log", async () => {
    const h = harness({ "/proj/main.tex": "x", "/proj/ref.tex": "y" });
    h.child(
      { stderr: [fixture("success-undefined-reference.stderr")], exit: { code: 0, signal: null } },
      { ".caztor/build/out/ref.pdf": PDF, ".caztor/build/out/ref.log": fixture("undefined-reference.log") },
    );
    const result = finishedOf(await drain(h.compiler.compile(request({ main: "ref.tex" as never }), new AbortController().signal)));

    expect(result.status).toBe("success");
    expect(result.logAvailable).toBe(true);
    expect(result.pdfRev).not.toBeNull();
    expect(result.diagnostics.map((d) => [d.severity, d.file, d.line, d.source])).toEqual([
      ["warning", "ref.tex", 3, "log"],
      ["warning", "ref.tex", 3, "log"],
    ]);
    expect(text(await h.compiler.readArtifact("pdf"))).toBe(PDF);
    expect(text(await h.compiler.readArtifact("log"))).toBe(fixture("undefined-reference.log"));
  });

  it("is failed-with-errors when the engine exits 0 with a PDF but printed errors, and still promotes the PDF", async () => {
    const h = harness({ "/proj/err.tex": "x" });
    h.child(
      { stderr: [fixture("continue-undefined.stderr")], exit: { code: 0, signal: null } },
      { ".caztor/build/out/err.pdf": PDF, ".caztor/build/out/err.log": fixture("undefined.log") },
    );
    const result = finishedOf(await drain(h.compiler.compile(request({ main: "err.tex" as never }), new AbortController().signal)));

    expect(result.status).toBe("failed-with-errors");
    expect(result.diagnostics.filter((d) => d.severity === "error").map((d) => [d.file, d.line])).toEqual([
      ["err.tex", 3],
      ["err.tex", 4],
    ]);
    expect(result.diagnostics.filter((d) => d.severity === "warning").map((d) => d.source)).toEqual(["log"]);
    expect(text(await h.compiler.readArtifact("pdf"))).toBe(PDF);
  });

  it("is failed when the engine halted without a PDF, keeping the located error and the previous preview", async () => {
    const h = harness({ "/proj/err.tex": "x", "/proj/.caztor/build/preview.pdf": "OLD PREVIEW" });
    // A PDF left in the output folder by an earlier run must not be mistaken for this run's output.
    await h.fs.mkdir("/proj/.caztor/build/out", { recursive: true });
    await h.fs.writeFile("/proj/.caztor/build/out/err.pdf", new TextEncoder().encode("STALE"));
    h.child(
      { stderr: [fixture("halt-undefined.stderr")], exit: { code: 1, signal: null } },
      { ".caztor/build/out/err.log": fixture("undefined.log") },
    );
    const result = finishedOf(await drain(h.compiler.compile(request({ main: "err.tex" as never, stopOnFirstError: true }), new AbortController().signal)));

    expect(result.status).toBe("failed");
    expect(result.pdfRev).toBeNull();
    expect(result.diagnostics.filter((d) => d.severity === "error")).toEqual([
      expect.objectContaining({ file: "err.tex", line: 3, message: "Undefined control sequence" }),
    ]);
    expect(text(await h.compiler.readArtifact("pdf"))).toBe("OLD PREVIEW");
  });

  it("maps the recorded offline failure to the readable download error", async () => {
    const h = harness();
    h.child({ stderr: [fixture("offline-first-run.stderr")], exit: { code: 101, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toBe(
      "Could not download LaTeX support files. The first compile needs a network connection.",
    );
  });

  it("adds the biblatex notice when a project file needs biber", async () => {
    const h = harness({ "/proj/main.tex": "\\documentclass{article}\n\\usepackage{biblatex}\n" });
    h.child({ stderr: [fixture("bibtex-success.stderr")], exit: { code: 0, signal: null } }, { ".caztor/build/out/main.pdf": PDF });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.status).toBe("success");
    expect(result.diagnostics).toEqual([expect.objectContaining({ severity: "warning", source: "caztor", file: "main.tex", line: 2 })]);
  });

  it("explains the opaque spawn error when biblatex needs biber, which is not supported", async () => {
    const h = harness({ "/proj/main.tex": "\\documentclass{article}\n\\usepackage{biblatex}\n\\addbibresource{r.bib}\n" });
    h.child({ stderr: [fixture("biblatex-biber-missing.stderr")], exit: { code: 1, signal: null } }, { ".caztor/build/out/main.log": "" });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    const errors = result.diagnostics.filter((d) => d.severity === "error");
    expect(result.status).toBe("failed");
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toMatch(/biblatex needs biber.*not supported.*BibTeX.*natbib.*\\bibliographystyle/s);
    expect(errors[0]?.message).not.toContain("os error 2");
    expect(errors[0]?.detail).toBe("No such file or directory (os error 2)");
    expect(result.diagnostics.some((d) => d.severity === "warning" && d.file === "main.tex")).toBe(true);
  });

  it("leaves a spawn error alone when the project does not use biblatex", async () => {
    const h = harness();
    h.child({ stderr: ["error: No such file or directory (os error 2)\n"], exit: { code: 1, signal: null } });
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.diagnostics.filter((d) => d.severity === "error").map((d) => d.message)).toEqual(["No such file or directory (os error 2)"]);
  });

  it("names files read from outside the project in warnings, from the engine warning and from the log", async () => {
    const h = harness();
    const stderr = "warning: accessing absolute path `/elsewhere/secret.tex`; build may not be reproducible in other environments\n";
    h.child(
      { stderr: [stderr], exit: { code: 0, signal: null } },
      { ".caztor/build/out/main.pdf": PDF, ".caztor/build/out/main.log": "(main.tex\n(../other/notes.tex)\n)" },
    );
    const result = finishedOf(await drain(h.compiler.compile(request(), new AbortController().signal)));
    expect(result.status).toBe("success");
    expect(result.diagnostics.map((d) => [d.severity, d.file, d.message])).toEqual([
      ["warning", null, "The document reads a file outside the project: /elsewhere/secret.tex"],
      ["warning", null, "The document reads a file outside the project: /other/notes.tex"],
    ]);
  });
});
