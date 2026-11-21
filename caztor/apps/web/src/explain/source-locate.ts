/**
 * Where a line printed in the PDF is in the LaTeX source, for a double click in the PDF: the inverse of
 * `jumpCandidates`. The source is read line by line as the PDF prints it (`plainText`) and the printed text is looked
 * for in that, so a citation printed as "[3]", "Equation (3)", a heading number and a word hyphenated at a line end do
 * not stop it.
 */
import { findPassages, plainText } from "./passages.ts";

/** A place in the source: 1-based line, and the clicked word's column and length in it (0 when it is not found). */
export interface SourcePlace {
  line: number;
  column: number;
  length: number;
}

/**
 * Digits are left out on both sides: the PDF prints numbers the source names by label (citations, equation and
 * section references, heading numbers), and the letters around them still say where the line is.
 */
const withoutDigits = (text: string) => text.replace(/\p{N}/gu, "");
/** A printed text with fewer letters and digits than this names no place; a wider candidate is tried. */
const MIN_LETTERS = 8;

const bare = (word: string) => word.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

function columnOf(line: string, word: string): number {
  if (word === "") return -1;
  const exact = line.indexOf(word);
  return exact !== -1 ? exact : line.toLowerCase().indexOf(word.toLowerCase());
}

/** The place of the first candidate (narrowest first) the source holds, or null when it holds none of them. */
export function locateInSource(source: string, candidates: readonly string[], word: string): SourcePlace | null {
  const lines = source.split("\n");
  const starts: number[] = [];
  let printed = "";
  for (const line of lines) {
    starts.push(printed.length);
    printed += `${/^\s*%/.test(line) ? "" : withoutDigits(plainText(line))} `;
  }
  const lineAt = (offset: number) => {
    let index = 0;
    while (index + 1 < starts.length && starts[index + 1]! <= offset) index += 1;
    return index;
  };
  const clicked = bare(word);
  for (const candidate of candidates) {
    const range = findPassages(printed, [withoutDigits(candidate)], MIN_LETTERS)[0];
    if (range === undefined) continue;
    const first = lineAt(range.from);
    const last = lineAt(range.to - 1);
    for (let index = first; index <= last; index += 1) {
      const column = columnOf(lines[index]!, clicked);
      if (column !== -1) return { line: index + 1, column, length: clicked.length };
    }
    return { line: first + 1, column: 0, length: 0 };
  }
  return null;
}
