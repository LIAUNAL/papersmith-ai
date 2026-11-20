import { highlightTree } from "@lezer/highlight";
import { describe, expect, it } from "vitest";
import { languageFor } from "./languages.ts";
import { highlightStyle } from "./theme.ts";

/** The class that the highlight style gives each piece of `source`, as `[text, class]` for the styled pieces. */
function styled(path: string, source: string): Array<[string, string]> {
  const language = languageFor(path);
  if (language === null) throw new Error(`No language for ${path}`);
  const tree = language.parser.parse(source);
  const pieces: Array<[string, string]> = [];
  highlightTree(tree, highlightStyle, (from, to, classes) => pieces.push([source.slice(from, to), classes]));
  return pieces;
}

describe("languageFor", () => {
  it.each(["main.tex", "style.sty", "thesis.cls", "chapters/Intro.TEX"])("uses the LaTeX language for %s", (path) => {
    expect(languageFor(path)?.name).toBe("stex");
  });

  it("uses the BibTeX language for .bib files in any letter case", () => {
    expect(languageFor("refs.bib")?.name).toBe("bibtex");
    expect(languageFor("deep/REFS.BIB")?.name).toBe("bibtex");
  });

  it.each(["notes.txt", "Makefile", "README", ".tex.bak", "image.png"])("has no language for %s", (path) => {
    expect(languageFor(path)).toBeNull();
  });
});

describe("syntax highlighting", () => {
  it("styles a LaTeX command differently from plain text", () => {
    const pieces = styled("main.tex", "\\section{A}");
    const command = pieces.find(([text]) => text.startsWith("\\section"));
    expect(command).toBeDefined();
    expect(command?.[1]).not.toBe("");
    // The argument is plain text: it either has no style or a different one from the command.
    const argument = pieces.find(([text]) => text === "A");
    expect(argument?.[1]).not.toBe(command?.[1]);
  });

  it("styles a LaTeX comment and math differently from a command", () => {
    const pieces = styled("main.tex", "% a note\n$x^2$ \\emph{y}");
    const comment = pieces.find(([text]) => text.includes("a note"));
    const command = pieces.find(([text]) => text.includes("\\emph"));
    expect(comment?.[1]).toBeTruthy();
    expect(command?.[1]).toBeTruthy();
    expect(comment?.[1]).not.toBe(command?.[1]);
  });

  it("styles BibTeX entry types, fields and values with distinct styles", () => {
    const pieces = styled("refs.bib", "@article{k,\n  author = {Knuth},\n  year = 1984\n}");
    const type = pieces.find(([text]) => text === "@article")?.[1];
    const field = pieces.find(([text]) => text === "author")?.[1];
    const value = pieces.find(([text]) => text === "{Knuth}")?.[1];
    const number = pieces.find(([text]) => text === "1984")?.[1];
    expect([type, field, value, number].every((classes) => classes !== undefined && classes !== "")).toBe(true);
    expect(new Set([type, field, value, number]).size).toBe(4);
  });
});
