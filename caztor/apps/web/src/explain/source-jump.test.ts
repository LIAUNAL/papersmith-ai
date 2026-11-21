import { describe, expect, it } from "vitest";
import { jumpCandidates } from "./source-jump.ts";

describe("what a double click in the source looks for in the PDF", () => {
  const line = "Classical spin models describe how magnetic order emerges from the interactions between localized moments, from the Ising model~\\cite{x} with two states per site.";

  it("starts with six words on each side of the clicked word, then twelve, then to the whole line", () => {
    const at = line.indexOf("emerges") + 2;
    expect(jumpCandidates(line, at)).toEqual([
      "spin models describe how magnetic order emerges from the interactions between localized moments,",
      "Classical spin models describe how magnetic order emerges from the interactions between localized moments, from the Ising model~\\cite{x} with two",
      line,
    ]);
  });

  it("looks only for the whole line when it is short", () => {
    expect(jumpCandidates("\\gamma(\\mathbf{c}, \\alpha) = \\mathbf{K}\\mathbf{c} + \\mathbf{o}_{\\alpha}", 3)).toEqual(["\\gamma(\\mathbf{c}, \\alpha) = \\mathbf{K}\\mathbf{c} + \\mathbf{o}_{\\alpha}"]);
  });

  it("looks for nothing on a comment, a blank line or a bare command", () => {
    expect(jumpCandidates("%% paper-writing block introduction.block-1 begin", 5)).toEqual([]);
    expect(jumpCandidates("   ", 1)).toEqual([]);
    expect(jumpCandidates("\\end{equation}", 2)).toEqual([]);
  });
});
