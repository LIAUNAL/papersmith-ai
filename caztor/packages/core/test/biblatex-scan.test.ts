import { describe, expect, it } from "vitest";
import { biblatexNotice, type RelPath } from "../src/index.ts";

const path = (value: string) => value as RelPath;

describe("biblatexNotice", () => {
  it("flags \\usepackage{biblatex} and names the file and line", () => {
    const notice = biblatexNotice([
      { path: path("main.tex"), text: "\\documentclass{article}\n\\usepackage[style=ieee]{biblatex}\n\\begin{document}\\end{document}" },
    ]);
    expect(notice).toEqual({
      severity: "warning",
      file: "main.tex",
      line: 2,
      message: "This project uses biblatex, which needs biber. Biber is not supported; use BibTeX (\\bibliography) instead.",
      source: "caztor",
    });
  });

  it("flags biblatex inside a package list and \\RequirePackage", () => {
    expect(biblatexNotice([{ path: path("a.tex"), text: "\\usepackage{amsmath, biblatex}" }])?.line).toBe(1);
    expect(biblatexNotice([{ path: path("a.sty"), text: "\\RequirePackage[backend=biber]{biblatex}" }])?.file).toBe("a.sty");
  });

  it("flags \\addbibresource even when the package is loaded elsewhere", () => {
    const notice = biblatexNotice([
      { path: path("main.tex"), text: "\\input{setup}" },
      { path: path("refs.tex"), text: "% setup\n\\addbibresource{refs.bib}" },
    ]);
    expect(notice).toMatchObject({ file: "refs.tex", line: 2 });
  });

  it("ignores commented-out lines but not an escaped percent sign", () => {
    expect(biblatexNotice([{ path: path("a.tex"), text: "% \\usepackage{biblatex}\n\\usepackage{natbib}" }])).toBeNull();
    expect(biblatexNotice([{ path: path("a.tex"), text: "50\\% \\usepackage{biblatex}" }])?.line).toBe(1);
  });

  it("does not flag BibTeX projects", () => {
    expect(
      biblatexNotice([{ path: path("a.tex"), text: "\\usepackage{natbib}\n\\bibliographystyle{plain}\n\\bibliography{refs}" }]),
    ).toBeNull();
  });

  it("does not flag biblatex with the bibtex backend, which BibTeX can run", () => {
    expect(biblatexNotice([{ path: path("a.tex"), text: "\\usepackage[backend=bibtex,style=numeric]{biblatex}" }])).toBeNull();
    expect(biblatexNotice([{ path: path("a.tex"), text: "\\usepackage[backend=bibtex8]{biblatex}\n\\addbibresource{r.bib}" }])).toBeNull();
  });

  it("does not mistake another package whose name contains biblatex", () => {
    expect(biblatexNotice([{ path: path("a.tex"), text: "\\usepackage{biblatex-apa-extras}" }])).toBeNull();
  });
});
