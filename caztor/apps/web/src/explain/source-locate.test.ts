import { describe, expect, it } from "vitest";
import { locateInSource } from "./source-locate.ts";

const SOURCE = [
  "\\section{Introduction}\\label{sec:introduction}",
  "%% paper-writing block introduction.block-1 begin",
  "Classical spin models describe how magnetic order emerges from the interactions between localized moments, from the Ising model with two states per site to vector spins carrying exchange, Dzyaloshinskii--Moriya interaction and anisotropy~\\cite{spirit2019}. Their phase transitions are a long-standing benchmark.",
  "Confined chiral magnets add topological textures, in which bimerons,",
  "skyrmions or polarised states are selected by the applied field~\\cite{bimeron2018}.",
  "\\begin{equation}",
  "\\gamma(\\mathbf{c}, \\alpha) = \\mathbf{K}\\mathbf{c} + \\mathbf{o}_{\\alpha} \\pmod{\\boldsymbol{\\omega}},",
  "\\end{equation}",
  "\\subsection{Exact linear colourings}\\label{sec:colourings}",
  "The colouring keeps the energy of Equation~\\eqref{eq:energy} and changes only the order, as Section~\\ref{sec:batching} explains.",
].join("\n");

describe("where a PDF line is in the LaTeX source", () => {
  it("finds a printed line, hyphenated and with a citation number, and the clicked word in it", () => {
    const place = locateInSource(SOURCE, ["exchange, Dzyaloshinskii–Moriya interaction and anisotropy [1]. Their phase transi-"], "anisotropy");
    expect(place).toEqual({ line: 3, column: SOURCE.split("\n")[2]!.indexOf("anisotropy"), length: "anisotropy".length });
  });

  it("finds a printed line that runs across two source lines, on the line of the clicked word", () => {
    const place = locateInSource(SOURCE, ["topological textures, in which bimerons, skyrmions or polarised states are"], "skyrmions");
    expect(place).toEqual({ line: 5, column: 0, length: "skyrmions".length });
  });

  it("finds a displayed formula", () => {
    const place = locateInSource(SOURCE, ["γ(c, α) = Kc + oα (mod ω), (6)"], "Kc");
    expect(place?.line).toBe(7);
  });

  it("tries the wider candidates when the narrowest is too short to name a place", () => {
    const place = locateInSource(SOURCE, ["benchmark.", "Their phase transitions are a long-standing benchmark."], "benchmark");
    expect(place?.line).toBe(3);
  });

  it("reads past the numbers the PDF prints for references and section headings", () => {
    expect(locateInSource(SOURCE, ["keeps the energy of Equation (1) and changes only the order, as Section 3.5"], "energy")?.line).toBe(10);
    expect(locateInSource(SOURCE, ["3.3. Exact linear colourings"], "linear")).toEqual({ line: 9, column: "\\subsection{Exact ".length, length: 6 });
  });

  it("finds nothing for text the source does not hold, such as the graphical abstract", () => {
    expect(locateInSource(SOURCE, ["One generated GPU kernel writes one kernel per system"], "kernel")).toBeNull();
  });
});
