import { describe, expect, it } from "vitest";
import { endOfDocumentMisplaced, markersKept, moveEndOfDocument, paperMarkerLines, paperTemplate } from "../src/paper-markers.ts";

const DOC = [
  "\\documentclass{article}",
  "%% paper-writing block intro.lead begin sha256=" + "a".repeat(64),
  "Some text.",
  "%% paper-writing block intro.lead end",
  "",
].join("\n");

describe("PaperSmith block markers", () => {
  it("are the lines that start with the marker prefix, valid or not, in order", () => {
    expect(paperMarkerLines(`${DOC}%% paper-writing block broken\r\n  %% paper-writing block indented\n`)).toEqual([
      `%% paper-writing block intro.lead begin sha256=${"a".repeat(64)}`,
      "%% paper-writing block intro.lead end",
      "%% paper-writing block broken",
    ]);
  });

  it("are kept when only the text between them changes", () => {
    expect(markersKept(DOC, DOC.replace("Some text.", "Other text.\nMore."))).toBe(true);
  });

  it.each([
    ["removed", DOC.replace("%% paper-writing block intro.lead end\n", "")],
    ["edited", DOC.replace("intro.lead end", "intro.lede end")],
    ["moved apart from its line start", DOC.replace("%% paper-writing block intro.lead end", "x %% paper-writing block intro.lead end")],
    ["duplicated", `${DOC}%% paper-writing block intro.lead end\n`],
  ])("are not kept when one is %s", (_label, after) => {
    expect(markersKept(DOC, after)).toBe(false);
  });

  it("do not limit a file that has none", () => {
    expect(markersKept("plain", "%% paper-writing block made by hand")).toBe(true);
  });
});

describe("the regions PaperSmith keeps in the paper", () => {
  it("are protected like the blocks", () => {
    const doc = "%% paper-writing declarations begin sha256=" + "b".repeat(64) + "\n%% {}\n%% paper-writing declarations end\n";
    expect(paperMarkerLines(doc)).toHaveLength(2);
    expect(markersKept(doc, doc.replace("declarations end", "declarations ended"))).toBe(false);
  });
});

describe("the end of the document", () => {
  const appended = "\\begin{document}\nHi\n\\end{document}\n%% paper-writing block a begin sha256=" + "c".repeat(64) + "\nText\n%% paper-writing block a end\n";

  it("is out of place when PaperSmith added a block after it", () => {
    expect(endOfDocumentMisplaced(appended)).toBe(true);
    expect(endOfDocumentMisplaced("\\begin{document}\nHi\n\\end{document}\n")).toBe(false);
    expect(endOfDocumentMisplaced("no end at all\n%% paper-writing block a end\n")).toBe(false);
  });

  it("ignores one inside a block or region, which is the block's own text", () => {
    const inside = "\\begin{document}\n%% paper-writing block a begin sha256=x\ntext\n\\end{document}\nmore\n%% paper-writing block a end\n";
    expect(endOfDocumentMisplaced(inside)).toBe(false);
    expect(moveEndOfDocument(inside)).toBe(inside);
    const both = `\\end{document}\n${inside}`;
    expect(moveEndOfDocument(both)).toBe(`${inside}\\end{document}\n`);
  });

  it("recognises one followed by a comment", () => {
    const commented = appended.replace("\\end{document}\n", "\\end{document} % the end\n");
    expect(endOfDocumentMisplaced(commented)).toBe(true);
    expect(moveEndOfDocument(commented).endsWith("%% paper-writing block a end\n\\end{document}\n")).toBe(true);
  });

  it("moves to the end, keeping every block byte for byte", () => {
    const moved = moveEndOfDocument(appended);
    expect(moved.endsWith("%% paper-writing block a end\n\\end{document}\n")).toBe(true);
    expect(moved.match(/\\end\{document\}/g)).toHaveLength(1);
    expect(markersKept(appended, moved)).toBe(true);
    expect(endOfDocumentMisplaced(moved)).toBe(false);
  });
});

describe("the starter paper", () => {
  it("is a whole document whose body PaperSmith can extend, with the title escaped", () => {
    const tex = paperTemplate("Spin & 50% of $x_1$ {here}");
    expect(tex).toMatch(/^\\documentclass/m);
    expect(tex).toContain("\\title{Spin \\& 50\\% of \\$x\\_1\\$ \\{here\\}}");
    expect(tex.trimEnd().endsWith("\\end{document}")).toBe(true);
    expect(paperMarkerLines(tex)).toEqual([]);
    expect(paperTemplate(undefined)).toContain("\\title{Title}");
  });
});
