import { parseRelPath, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import type { FileResolver } from "../../src/tectonic/diagnostics.ts";
import { outsideReads, parseLog } from "../../src/tectonic/log-parser.ts";
import { fixture } from "../support/fixtures.ts";

function rel(path: string): RelPath {
  const parsed = parseRelPath(path);
  if (!parsed.ok) throw new Error(`bad test path ${path}`);
  return parsed.value;
}

function resolverFor(...files: string[]): FileResolver {
  const known = new Set(files);
  return (raw) => [raw, `${raw}.tex`].map((candidate) => (known.has(candidate) ? rel(candidate) : null)).find((hit) => hit !== null) ?? null;
}

describe("parseLog warnings", () => {
  it("reads undefined-reference and citation warnings with their line and file", () => {
    const { diagnostics } = parseLog(fixture("undefined-reference.log"), resolverFor("ref.tex"));
    expect(diagnostics).toEqual([
      { severity: "warning", file: "ref.tex", line: 3, message: "Reference `nolabel' on page 1 undefined", source: "log" },
      { severity: "warning", file: "ref.tex", line: 3, message: "Citation `missing' on page 1 undefined", source: "log" },
    ]);
  });

  it("does not list the undefined-references summary or the TeX errors, which come from stderr", () => {
    const { diagnostics } = parseLog(fixture("undefined.log"), resolverFor("err.tex"));
    expect(diagnostics.map((d) => d.message)).toEqual(["Reference `nolabel' on page 1 undefined"]);
  });

  it("attributes each warning to the file being read, including Package and Class warnings", () => {
    const { diagnostics } = parseLog(fixture("package-warnings.log"), resolverFor("main.tex", "sections/intro.tex", "sections/body.tex"));
    expect(diagnostics.map((d) => [d.file, d.line, d.message])).toEqual([
      ["sections/intro.tex", 2, "demo: Something looks odd here and continues on a second line"],
      ["sections/body.tex", 3, "Reference `missing-in-body' on page 1 undefined"],
      ["sections/body.tex", 4, "article: Class level warning"],
      ["main.tex", 5, "Citation `nokey' on page 1 undefined"],
      [
        "main.tex",
        5,
        "Reference `a-rather-long-label-name-that-forces-the-warning-line-to-wrap-around-the-log-width' on page 1 undefined",
      ],
    ]);
  });

  it("rejoins a message that the engine wrapped at 79 columns", () => {
    const first = "Package demo Warning: " + "x".repeat(57);
    expect(first.length).toBe(79);
    const log = ["(a.tex", "", first, "yyy on input line 4.", "", ")"].join("\n");
    const { diagnostics } = parseLog(log, resolverFor("a.tex"));
    expect(diagnostics).toEqual([
      { severity: "warning", file: "a.tex", line: 4, message: `demo: ${"x".repeat(57)}yyy`, source: "log" },
    ]);
  });

  it("gives a warning without a resolvable file no jump target and keeps the line in the text", () => {
    const log = ["(mystery/place", "", "LaTeX Warning: Something odd on input line 9.", "", ")"].join("\n");
    const { diagnostics } = parseLog(log, resolverFor("main.tex"));
    expect(diagnostics).toEqual([
      { severity: "warning", file: null, line: null, message: "Something odd on input line 9", source: "log" },
    ]);
  });

  it("keeps a warning that has no line number, without a line", () => {
    const log = ["(a.tex", "", "LaTeX Warning: Unused global option(s): [draft].", "", ")"].join("\n");
    const { diagnostics } = parseLog(log, resolverFor("a.tex"));
    expect(diagnostics).toEqual([
      { severity: "warning", file: "a.tex", line: null, message: "Unused global option(s): [draft].", source: "log" },
    ]);
  });

  it("lists a repeated warning once", () => {
    const block = ["LaTeX Warning: Reference `x' on page 1 undefined on input line 2.", ""];
    const { diagnostics } = parseLog(["(a.tex", "", ...block, ...block, ")"].join("\n"), resolverFor("a.tex"));
    expect(diagnostics).toHaveLength(1);
  });

  it("finds nothing in a log without warnings", () => {
    expect(parseLog("(a.tex\nHello\n)\n", resolverFor("a.tex")).diagnostics).toEqual([]);
  });
});

describe("parseLog opened files", () => {
  it("lists every file the engine opened, in order, as it printed them", () => {
    const { openedFiles } = parseLog(fixture("outside-read.log"), resolverFor("main.tex"));
    expect(openedFiles).toEqual(
      expect.arrayContaining(["main.tex", "article.cls", "main.aux", "../outside/secret.tex", "/work/outside/secret.tex"]),
    );
    expect(openedFiles.indexOf("../outside/secret.tex")).toBeLessThan(openedFiles.indexOf("/work/outside/secret.tex"));
  });
});

describe("outsideReads", () => {
  const root = "/work/proj";
  const message = "The document reads a file outside the project: /work/outside/secret.tex";

  it("turns the absolute-path warning into a warning naming the file", () => {
    const found = outsideReads({ root, stderr: fixture("outside-read.stderr"), openedFiles: [] });
    expect(found).toEqual([
      {
        severity: "warning",
        file: null,
        line: null,
        message,
        detail: "Compiling can read any file you can read, and its content can end up in the PDF and the log. Shell escape stays disabled.",
        source: "stderr",
      },
    ]);
  });

  it("reports a file the log shows resolving outside the root, even when the engine printed no warning", () => {
    const found = outsideReads({ root, stderr: "", openedFiles: ["main.tex", "article.cls", "../outside/secret.tex"] });
    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({ severity: "warning", file: null, line: null, message, source: "log" });
  });

  it("names one file once however many ways the run showed it", () => {
    const { openedFiles } = parseLog(fixture("outside-read.log"), resolverFor("main.tex"));
    const found = outsideReads({ root, stderr: fixture("outside-read.stderr"), openedFiles });
    expect(found.map((d) => d.message)).toEqual([message]);
  });

  it("reports each different outside file", () => {
    const found = outsideReads({ root, stderr: "", openedFiles: ["../a.tex", "/etc/hosts"] });
    expect(found.map((d) => d.message)).toEqual([
      "The document reads a file outside the project: /work/a.tex",
      "The document reads a file outside the project: /etc/hosts",
    ]);
  });

  it("ignores files inside the project, including absolute and dotted spellings", () => {
    const found = outsideReads({
      root,
      stderr: "warning: accessing absolute path `/work/proj/sub/x.tex`; build may not be reproducible in other environments\n",
      openedFiles: ["sections/../intro.tex", "./a.tex", "/work/proj/b.tex", "article.cls"],
    });
    expect(found).toEqual([]);
  });

  it("does not take a project folder that merely shares the root's prefix for the project", () => {
    const found = outsideReads({ root, stderr: "", openedFiles: ["/work/proj-other/x.tex"] });
    expect(found.map((d) => d.message)).toEqual(["The document reads a file outside the project: /work/proj-other/x.tex"]);
  });
});
