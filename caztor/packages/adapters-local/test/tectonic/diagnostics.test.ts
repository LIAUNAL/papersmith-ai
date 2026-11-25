import { parseRelPath, type Diagnostic, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { parseStderr, type FileResolver } from "../../src/tectonic/diagnostics.ts";
import { fixture } from "../support/fixtures.ts";

function rel(path: string): RelPath {
  const parsed = parseRelPath(path);
  if (!parsed.ok) throw new Error(`bad test path ${path}`);
  return parsed.value;
}

/** Knows the project's files; resolves a name as given or with `.tex` appended. */
function resolverFor(...files: string[]): FileResolver {
  const known = new Set(files);
  return (raw) => [raw, `${raw}.tex`].map((candidate) => (known.has(candidate) ? rel(candidate) : null)).find((hit) => hit !== null) ?? null;
}

const errors = (all: Diagnostic[]) => all.filter((d) => d.severity === "error");
const warnings = (all: Diagnostic[]) => all.filter((d) => d.severity === "warning");

describe("parseStderr errors", () => {
  it("extracts file, line and message from `error: file:line: message` and lists a repeated error once", () => {
    const found = errors(parseStderr(fixture("continue-undefined.stderr"), resolverFor("err.tex")));
    expect(found).toEqual([
      { severity: "error", file: "err.tex", line: 3, message: "Undefined control sequence", source: "stderr" },
      { severity: "error", file: "err.tex", line: 4, message: "Undefined control sequence", source: "stderr" },
    ]);
  });

  it("consumes the 'errors were ignored' marker instead of listing it as a warning", () => {
    const found = parseStderr(fixture("continue-undefined.stderr"), resolverFor("err.tex"));
    expect(warnings(found)).toEqual([]);
  });

  it("resolves a file named without its extension through the resolver", () => {
    const found = errors(parseStderr(fixture("continue-input-errors.stderr"), resolverFor("ch/one.tex", "ch/two.tex")));
    expect(found.map((d) => [d.file, d.line])).toEqual([
      ["ch/one.tex", 3],
      ["ch/two.tex", 2],
    ]);
  });

  it("drops the engine wrapper lines and the transcript when a located error exists, keeping `caused by` as detail", () => {
    const found = parseStderr(fixture("halt-undefined.stderr"), resolverFor("err.tex"));
    expect(found).toEqual([
      {
        severity: "error",
        file: "err.tex",
        line: 3,
        message: "Undefined control sequence",
        detail: "halted on potentially-recoverable error as specified",
        source: "stderr",
      },
    ]);
  });

  it("does not read lines of the transcript between the rules as diagnostics", () => {
    const text = [
      "error: a.tex:1: Real problem",
      "error: something bad happened inside XeTeX; its output follows:",
      "",
      "=".repeat(79),
      "error: lookalike inside the transcript",
      "warning: also not real",
      "=".repeat(79),
      "error: the XeTeX engine had an unrecoverable error",
    ].join("\n");
    const found = parseStderr(text, resolverFor("a.tex"));
    expect(found.map((d) => d.message)).toEqual(["Real problem"]);
  });

  it("keeps the unrecoverable-error line as a file-less error when no located error exists", () => {
    const text = [
      "error: something bad happened inside XeTeX; its output follows:",
      "=".repeat(79),
      "transcript",
      "=".repeat(79),
      "error: the XeTeX engine had an unrecoverable error",
      "caused by: halted on potentially-recoverable error as specified",
    ].join("\n");
    expect(parseStderr(text, resolverFor())).toEqual([
      {
        severity: "error",
        file: null,
        line: null,
        message: "the XeTeX engine had an unrecoverable error",
        detail: "halted on potentially-recoverable error as specified",
        source: "stderr",
      },
    ]);
  });

  it("reports any other `error:` line as an error without a file", () => {
    const found = parseStderr("error: output directory \"out\" does not exist\n", resolverFor());
    expect(found).toEqual([
      { severity: "error", file: null, line: null, message: 'output directory "out" does not exist', source: "stderr" },
    ]);
  });

  it("keeps a message that contains colons and digits intact", () => {
    const found = parseStderr("error: a.tex:12: Missing $ inserted: 3: really\n", resolverFor("a.tex"));
    expect(found[0]).toMatchObject({ file: "a.tex", line: 12, message: "Missing $ inserted: 3: really" });
  });

  it("keeps the raw name in the message when the file does not resolve to a project file", () => {
    const found = parseStderr("error: unknown/place.tex:7: Bad thing\n", resolverFor("a.tex"));
    expect(found).toEqual([
      { severity: "error", file: null, line: null, message: "unknown/place.tex: Bad thing", source: "stderr" },
    ]);
  });

  it("reports nothing for a run that printed only notes", () => {
    expect(parseStderr(fixture("bibtex-success.stderr"), resolverFor("main.tex"))).toEqual([]);
  });
});

describe("parseStderr warnings", () => {
  it("reports a located warning and consumes the generic 'warnings were issued' marker", () => {
    const found = parseStderr(fixture("warnings.stderr"), resolverFor("sections/body.tex"));
    expect(found).toEqual([
      {
        severity: "warning",
        file: "sections/body.tex",
        line: 5,
        message: "Overfull \\hbox (112.15999pt too wide) detected at line 5",
        source: "stderr",
      },
    ]);
  });

  it("leaves the absolute-path warning to the outside-read check", () => {
    expect(parseStderr(fixture("outside-read.stderr"), resolverFor("main.tex"))).toEqual([]);
  });

  it("reports a warning without a location as a file-less warning", () => {
    const found = parseStderr("warning: something to know\n", resolverFor());
    expect(found).toEqual([{ severity: "warning", file: null, line: null, message: "something to know", source: "stderr" }]);
  });
});

describe("parseStderr readability", () => {
  it("drops the '! LaTeX Error:' prefix from a message", () => {
    const found = parseStderr("error: a.tex:4: ! LaTeX Error: Environment foo undefined.\n", resolverFor("a.tex"));
    expect(found).toEqual([{ severity: "error", file: "a.tex", line: 4, message: "Environment foo undefined.", source: "stderr" }]);
  });

  it("keeps the prefix of other messages, such as package errors", () => {
    const found = parseStderr("error: a.tex:4: Package natbib Error: Bibliography not compatible.\n", resolverFor("a.tex"));
    expect(found[0]?.message).toBe("Package natbib Error: Bibliography not compatible.");
  });

  it("keeps the missing file and drops the errors that only follow from it, before and after other missing files", () => {
    const found = parseStderr(fixture("missing-package.stderr"), resolverFor("main.tex"));
    expect(found.map((d) => [d.line, d.message])).toEqual([
      [3, "File `nosuchpkg.sty' not found."],
      [6, "File `chapter.tex' not found."],
      [9, "Package natbib Error: Bibliography not compatible with author-year citations."],
    ]);
  });

  it("keeps an undefined control sequence when no file is missing", () => {
    const found = parseStderr("error: a.tex:2: Undefined control sequence\n", resolverFor("a.tex"));
    expect(found.map((d) => d.message)).toEqual(["Undefined control sequence"]);
  });

  it("attributes an overfull or underfull box in a paragraph to the first line of the paragraph", () => {
    const found = parseStderr(
      "warning: a.tex:9: Overfull \\hbox (3.0pt too wide) in paragraph at lines 5--9\nwarning: a.tex:12: Underfull \\vbox (badness 10000) in alignment at lines 11--12\nwarning: a.tex:3: Overfull \\hbox (1pt too wide) detected at line 3\n",
      resolverFor("a.tex"),
    );
    expect(found.map((d) => d.line)).toEqual([5, 11, 3]);
  });
});
