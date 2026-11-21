import { describe, expect, it } from "vitest";
import { explainedPassages, findPassages, findPrinted, plainText } from "./passages.ts";

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

  it("reads math commands as the symbols the PDF prints", () => {
    expect(plainText("\\gamma(\\mathbf{c}, \\alpha) = \\mathbf{K}\\mathbf{c} + \\mathbf{o}_{\\alpha} \\pmod{\\boldsymbol{\\omega}},")).toBe(
      "γ(c, α) = Kc + o_α (mod ω),",
    );
  });
});

describe("where a passage is printed in a PDF page", () => {
  // Text as pdf.js gives it for the compiled paper: math glyphs, a micro sign, a hyphenated line end, an accent.
  const page = [
    "updated at once. The independence of A in the interaction graph (Λ, E) guar-",
    "antees that simultaneous single-site updates reproduce the corresponding",
    "γ(c, α) = Kc + oα (mod ω), K ∈ ZF ×D , oα ∈ G, (6)",
    "Kδ + oα′ − oα ̸≡ 0 (mod ω) for every (α, α′ , δ, J) ∈ B. (7)",
    "kµ Lµ ≡ 0 (mod ω), (8)",
    "the Néel order of the antiferromagnet",
    "since the energy change of Equation (2) at each updated site then depends only on spins outside A.",
    "γ(c, α) ̸= γ(c + δ, α′ ) and G = Zω1 × · · · × ZωF",
  ].join(" ");
  const printed = (passage: string) => findPrinted(page, passage).map((range) => page.slice(range.from, range.to));

  it("finds prose with inline math", () => {
    expect(printed("The independence of $\\mathcal{A}$ in the interaction graph $(\\Lambda, \\mathcal{E})$ guarantees that simultaneous")).toEqual([
      "The independence of A in the interaction graph (Λ, E) guar- antees that simultaneous",
    ]);
  });

  it("finds a displayed formula", () => {
    expect(printed("\\gamma(\\mathbf{c}, \\alpha) = \\mathbf{K}\\mathbf{c} + \\mathbf{o}_{\\alpha} \\pmod{\\boldsymbol{\\omega}},")).toEqual([
      "γ(c, α) = Kc + oα (mod ω",
    ]);
    expect(printed("\\mathbf{K}\\boldsymbol{\\delta} + \\mathbf{o}_{\\alpha'} - \\mathbf{o}_{\\alpha} \\not\\equiv \\mathbf{0} \\pmod{\\boldsymbol{\\omega}}")).toEqual([
      "Kδ + oα′ − oα ̸≡ 0 (mod ω",
    ]);
  });

  it("finds a short formula, whatever mu the font prints", () => {
    expect(printed("\\mathbf{k}_{\\mu} L_{\\mu} \\equiv \\mathbf{0} \\pmod{\\boldsymbol{\\omega}} ,")).toEqual(["kµ Lµ ≡ 0 (mod ω"]);
  });

  it("finds the text around a reference, which the PDF prints as a number", () => {
    expect(printed("since the energy change of Equation~\\eqref{eq:local-field} at each updated site then depends only on spins outside $\\mathcal{A}$.")).toEqual([
      "since the energy change of Equation",
      "at each updated site then depends only on spins outside A",
    ]);
  });

  it("finds formulas of six letters or more", () => {
    expect(printed("\\gamma(\\mathbf{c}, \\alpha) \\neq \\gamma(\\mathbf{c} + \\boldsymbol{\\delta}, \\alpha')")).toEqual(["γ(c, α) ̸= γ(c + δ, α"]);
    expect(printed("\\mathcal{G}=\\mathbb{Z}_{\\omega_1}\\times\\dots\\times\\mathbb{Z}_{\\omega_F}")).toEqual(["G = Zω1 × · · · × ZωF"]);
    expect(printed("(\\mathbf{K},\\mathbf{o},\\boldsymbol{\\omega})")).toEqual([]);
  });

  it("matches accented letters written as LaTeX accents", () => {
    expect(printed("the N\\'{e}el order of the antiferromagnet")).toEqual(["the Néel order of the antiferromagnet"]);
  });

  it("does not take a short prose quotation for a passage", () => {
    expect(printed("the Néel order")).toEqual([]);
  });
});

