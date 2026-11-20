import { describe, expect, it } from "vitest";
import { explainedPassages, findPassages, plainText } from "./passages.ts";

describe("the passages a reply explains", () => {
  it("takes inline code, block quotes and quoted text that read as passages, without duplicates", () => {
    const reply = [
      "The key sentence is `each colour class is updated in parallel without conflicts`.",
      "> Exact colourings keep detailed balance",
      "> for every sweep.",
      'You wrote “the generator compiles a spin model into one kernel” and later "the generator compiles a spin model into one kernel".',
      "Open `paper/main.tex` and run `make`.",
    ].join("\n");
    expect(explainedPassages(reply)).toEqual([
      "each colour class is updated in parallel without conflicts",
      "Exact colourings keep detailed balance for every sweep.",
      "the generator compiles a spin model into one kernel",
    ]);
  });

  it("reads the quotes inside a JSON reply, as PaperSmith's tutors answer", () => {
    const reply = 'Reading the thread.\n```json\n' + JSON.stringify({ reply: "The claim is:\n> each colour class is updated in parallel without conflicts\nso it is exact.", hint: "Look at `the stencil loads need no barrier at all`." }, null, 2) + "\n```";
    expect(explainedPassages(reply)).toEqual(["each colour class is updated in parallel without conflicts", "the stencil loads need no barrier at all"]);
  });

  it("takes long formulas, as written in LaTeX", () => {
    expect(explainedPassages("It follows from $$\\Delta E_i = 2\\bar{J}\\,(z_i - 2\\kappa_i) + 2 h\\, s_i$$ and $x$.")).toEqual(["\\Delta E_i = 2\\bar{J}\\,(z_i - 2\\kappa_i) + 2 h\\, s_i"]);
  });

  it("finds nothing in a reply that quotes nothing", () => {
    expect(explainedPassages("Equation 3 is exact because the colouring is proper.")).toEqual([]);
  });
});

describe("where a passage is", () => {
  it("finds it across line breaks, extra spaces, hyphenation and punctuation, as ranges of the original text", () => {
    const doc = "Intro.\nEach colour  class is up-\ndated in parallel, without conflicts. End.";
    const [range] = findPassages(doc, ["each colour class is updated in parallel without conflicts"]);
    expect(doc.slice(range!.from, range!.to)).toBe("Each colour  class is up-\ndated in parallel, without conflicts");
  });

  it("finds every occurrence and ignores passages too short to be meaningful", () => {
    const doc = "exact colourings keep balance here, and exact colourings keep balance there";
    expect(findPassages(doc, ["exact colourings keep balance"]).length).toBe(2);
    expect(findPassages(doc, ["here"])).toEqual([]);
  });

  it("reads LaTeX as the PDF shows it", () => {
    expect(plainText("Critical points~\\cite{chen1993} of the \\textbf{Heisenberg} model, $T_c$")).toBe("Critical points of the Heisenberg model, T_c");
  });
});
