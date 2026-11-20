import { StreamLanguage, type Language } from "@codemirror/language";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { bibtexParser } from "./bibtex.ts";

const latex = StreamLanguage.define(stex);
const bibtex = StreamLanguage.define(bibtexParser);

/** The language for a project file, chosen by extension (any letter case), or null for plain text. */
export function languageFor(path: string): Language | null {
  const name = path.slice(path.lastIndexOf("/") + 1);
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return null;
  switch (name.slice(dot + 1).toLowerCase()) {
    case "tex":
    case "sty":
    case "cls":
      return latex;
    case "bib":
      return bibtex;
    default:
      return null;
  }
}
