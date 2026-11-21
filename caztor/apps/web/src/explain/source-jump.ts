/**
 * What a double click in the LaTeX source looks for in the PDF: the words around the clicked one, then more of the
 * line, then the whole line. The PDF finds the first that a page prints (see `findPrinted`), so the narrowest text
 * that still names one place wins.
 */
import { plainText } from "./passages.ts";

/** Words taken on each side of the clicked one, narrowest first. */
const RADII = [6, 12];
/** Commands that print nothing a reader could find on the page; a line of only these looks for nothing. */
const STRUCTURE =
  /\\(?:begin|end|label|input|include|usepackage|documentclass|bibliographystyle|bibliography|includegraphics|newcommand|renewcommand|vspace|hspace|centering|maketitle|clearpage|newpage)\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*/g;
/** A printed form with fewer letters and digits than this names no place. */
const MIN_LETTERS = 6;

const letters = (text: string) => [...text.normalize("NFKD")].filter((char) => /[\p{L}\p{N}]/u.test(char)).length;

/** The texts to look for, narrowest first, for a double click at `column` (0-based) of `line`. */
export function jumpCandidates(line: string, column: number): string[] {
  const source = line.replace(/(?<!\\)%.*$/, "").trimEnd();
  if (letters(plainText(source.replace(STRUCTURE, " "))) < MIN_LETTERS) return [];
  const words = [...source.matchAll(/\S+/g)].map((match) => ({ from: match.index, to: match.index + match[0].length }));
  let clicked = words.findIndex((word) => column < word.to);
  if (clicked === -1) clicked = words.length - 1;
  const candidates: string[] = [];
  for (const radius of RADII) {
    const first = words[Math.max(0, clicked - radius)]!;
    const last = words[Math.min(words.length - 1, clicked + radius)]!;
    candidates.push(source.slice(first.from, last.to));
  }
  candidates.push(source.trim());
  return [...new Set(candidates)].filter((candidate) => letters(plainText(candidate)) >= MIN_LETTERS);
}
