/**
 * The passages of the paper an assistant's reply explains, and where they are in a text. A reply points at a passage
 * by quoting it: inline code, a block quote or text in quotation marks. Matching compares letters and digits only,
 * so line breaks, extra spaces, hyphenation and punctuation do not stop a passage from being found.
 */

export interface Range {
  from: number;
  to: number;
}

/** A quotation shorter than this, in letters and digits, is a name or a path, not a passage. */
const MIN_KEY_LENGTH = 20;
const MIN_WORDS = 4;
const MAX_PASSAGES = 30;

const squash = (text: string) => text.replace(/\s+/g, " ").trim();
const isWordChar = (char: string) => /[\p{L}\p{N}]/u.test(char);
const keyOf = (text: string) => [...text.toLowerCase()].filter(isWordChar).join("");
/** Prose of a few words, or a formula long enough to name one place. */
const looksLikePassage = (text: string) => keyOf(text).length >= MIN_KEY_LENGTH && (text.split(" ").length >= MIN_WORDS || text.includes("\\"));

/** Every string inside the JSON code blocks of a reply, as PaperSmith's tutors answer, in order. */
function jsonStrings(reply: string): string[] {
  const strings: string[] = [];
  const collect = (value: unknown): void => {
    if (typeof value === "string") strings.push(value);
    else if (Array.isArray(value)) value.forEach(collect);
    else if (typeof value === "object" && value !== null) Object.values(value).forEach(collect);
  };
  for (const match of reply.matchAll(/```json\s*\n([\s\S]*?)\n```/g)) {
    try {
      collect(JSON.parse(match[1]!));
    } catch {
      // Not valid JSON: its text is read as it is.
    }
  }
  return strings;
}

/** The quoted passages of a reply, in order of appearance, each once. */
export function explainedPassages(reply: string): string[] {
  const inner = jsonStrings(reply);
  if (inner.length > 0) return explainedPassages(inner.join("\n\n").concat("\n", reply.replace(/```json\s*\n[\s\S]*?\n```/g, "")));
  const found: Array<{ at: number; text: string }> = [];
  for (const match of reply.matchAll(/\$\$([\s\S]+?)\$\$|\$([^$\n]+)\$/g)) found.push({ at: match.index, text: (match[1] ?? match[2])! });
  for (const match of reply.matchAll(/`([^`\n]+)`/g)) found.push({ at: match.index, text: match[1]! });
  for (const match of reply.matchAll(/“([^”\n]+)”|"([^"\n]+)"/g)) found.push({ at: match.index, text: (match[1] ?? match[2])! });
  for (const match of reply.matchAll(/(?:^>[ \t]?.*(?:\n|$))+/gm)) found.push({ at: match.index, text: match[0].replace(/^>[ \t]?/gm, " ") });
  const seen = new Set<string>();
  const passages: string[] = [];
  for (const { text } of found.sort((a, b) => a.at - b.at)) {
    const passage = squash(text);
    const key = keyOf(passage);
    if (!looksLikePassage(passage) || seen.has(key)) continue;
    seen.add(key);
    passages.push(passage);
    if (passages.length === MAX_PASSAGES) break;
  }
  return passages;
}

/** Every place in `text` where one of the passages is, as ranges of `text`, in order. */
export function findPassages(text: string, passages: readonly string[]): Range[] {
  // The letters and digits of the text, lowercased, with where each one came from.
  const chars = [...text];
  const offsets: number[] = [];
  let key = "";
  let offset = 0;
  for (const char of chars) {
    if (isWordChar(char)) {
      key += char.toLowerCase();
      offsets.push(offset);
    }
    offset += char.length;
  }
  const ranges: Range[] = [];
  for (const passage of passages) {
    const wanted = keyOf(passage);
    if (wanted.length < MIN_KEY_LENGTH) continue;
    for (let at = key.indexOf(wanted); at !== -1; at = key.indexOf(wanted, at + wanted.length)) {
      const last = offsets[at + wanted.length - 1]!;
      ranges.push({ from: offsets[at]!, to: last + (text.codePointAt(last)! > 0xffff ? 2 : 1) });
    }
  }
  return ranges.sort((a, b) => a.from - b.from);
}

/** LaTeX as a reader sees it in the PDF: references dropped, commands replaced by their text, math symbols bare. */
export function plainText(latex: string): string {
  return squash(
    latex
      .replace(/\\(?:cite[pt]?|ref|eqref|label|autoref|cref|Cref)\*?(?:\[[^\]]*\])?\{[^}]*\}/g, "")
      .replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g, "$1")
      .replace(/\\[a-zA-Z]+\*?/g, " ")
      .replace(/[{}$~]/g, " ")
      .replace(/\s+([,.;:])/g, "$1"),
  );
}
