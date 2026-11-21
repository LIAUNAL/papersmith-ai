/**
 * Where a line printed in the PDF is in the LaTeX source, for a double click in the PDF: the inverse of
 * `jumpCandidates`. The source is read line by line as the PDF prints it (`plainText`) and the printed text is looked
 * for in that, so a citation printed as "[3]", "Equation (3)", a heading number and a word hyphenated at a line end do
 * not stop it.
 */
import { findPassages, plainText, type Range } from "./passages.ts";

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

const isLetter = (char: string | undefined) => char !== undefined && /[\p{L}\p{N}]/u.test(char);

/** Where `word` starts in `line`: the whole-word occurrence nearest `near` (a column), else any occurrence; -1 when none. */
function columnOf(line: string, word: string, near: number): number {
  if (word === "") return -1;
  const occurrences = (text: string, wanted: string) => {
    const found: number[] = [];
    for (let at = text.indexOf(wanted); at !== -1; at = text.indexOf(wanted, at + 1)) found.push(at);
    return found;
  };
  let all = occurrences(line, word);
  if (all.length === 0) all = occurrences(line.toLowerCase(), word.toLowerCase());
  if (all.length === 0) return -1;
  const whole = all.filter((at) => !isLetter(line[at - 1]) && !isLetter(line[at + word.length]));
  const pool = whole.length > 0 ? whole : all;
  return pool.reduce((best, at) => (Math.abs(at - near) < Math.abs(best - near) ? at : best));
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
  const placeOf = (range: Range): SourcePlace => {
    const first = lineAt(range.from);
    const last = lineAt(range.to - 1);
    // Where in each line the clicked text sits, as a share of the line printed, scaled to the source line.
    const middle = (range.from + range.to) / 2;
    for (let index = first; index <= last; index += 1) {
      const start = starts[index]!;
      const end = starts[index + 1] ?? printed.length;
      const share = Math.min(Math.max((middle - start) / Math.max(end - start, 1), 0), 1);
      const column = columnOf(lines[index]!, clicked, share * lines[index]!.length);
      if (column !== -1) return { line: index + 1, column, length: clicked.length };
    }
    return { line: first + 1, column: 0, length: 0 };
  };
  // The narrowest candidate the source holds says where; when it is there more than once, a wider one says which.
  let narrow: Range[] | null = null;
  for (const [index, candidate] of candidates.entries()) {
    const ranges = findPassages(printed, [withoutDigits(candidate)], MIN_LETTERS);
    if (ranges.length === 0) continue;
    narrow ??= ranges;
    if (ranges.length > 1 && index < candidates.length - 1) continue;
    const wide = ranges[0]!;
    return placeOf(narrow.find((range) => range.from >= wide.from && range.to <= wide.to) ?? wide);
  }
  return narrow === null ? null : placeOf(narrow[0]!);
}

const isWordChar = (char: string | undefined) => char !== undefined && /[\p{L}\p{N}'’-]/u.test(char);

/**
 * The word at `offset` of `text`, for a double click the browser resolved to the space between two words: the word
 * around the offset, else the nearest one before it, else the nearest one after it; empty when there is none.
 */
export function wordAround(text: string, offset: number): string {
  let at = offset;
  if (!isWordChar(text[at])) {
    let left = at - 1;
    while (left >= 0 && !isWordChar(text[left])) left -= 1;
    if (left >= 0) at = left;
    else {
      let right = at + 1;
      while (right < text.length && !isWordChar(text[right])) right += 1;
      if (right >= text.length) return "";
      at = right;
    }
  }
  let from = at;
  let to = at + 1;
  while (from > 0 && isWordChar(text[from - 1])) from -= 1;
  while (to < text.length && isWordChar(text[to])) to += 1;
  return text.slice(from, to);
}
