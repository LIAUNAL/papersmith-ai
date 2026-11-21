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
/** A formula prints few letters, so its printed form is looked for from this many on. */
const MIN_FORMULA_KEY_LENGTH = 6;
const MIN_WORDS = 4;
const MAX_PASSAGES = 30;

const squash = (text: string) => text.replace(/\s+/g, " ").trim();
const isWordChar = (char: string) => /[\p{L}\p{N}]/u.test(char);
/** Math symbols fonts print for a Greek letter: the increment sign for \Delta. */
const LOOK_ALIKE: Record<string, string> = { "∆": "Δ" };
/** The letters and digits of one character as compared: compatibility forms folded (ﬁ, µ, 𝐊), accents dropped, lowercase. */
const fold = (char: string) => [...(LOOK_ALIKE[char] ?? char).normalize("NFKD").toLowerCase()].filter(isWordChar).join("");
const keyOf = (text: string) => [...text].map(fold).join("");
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
export function findPassages(text: string, passages: readonly string[], minLength = MIN_KEY_LENGTH): Range[] {
  // The letters and digits of the text, lowercased, with where each one came from.
  const chars = [...text];
  const offsets: number[] = [];
  let key = "";
  let offset = 0;
  for (const char of chars) {
    const folded = fold(char);
    key += folded;
    for (let unit = 0; unit < folded.length; unit++) offsets.push(offset);
    offset += char.length;
  }
  const ranges: Range[] = [];
  for (const passage of passages) {
    const wanted = keyOf(passage);
    if (wanted.length < minLength) continue;
    for (let at = key.indexOf(wanted); at !== -1; at = key.indexOf(wanted, at + wanted.length)) {
      const last = offsets[at + wanted.length - 1]!;
      ranges.push({ from: offsets[at]!, to: last + (text.codePointAt(last)! > 0xffff ? 2 : 1) });
    }
  }
  return ranges.sort((a, b) => a.from - b.from);
}

/** A citation or cross-reference, which the PDF prints as a number the source does not hold. */
const REFERENCE = /\\(?:cite[pt]?|ref|eqref|label|autoref|cref|Cref)\*?(?:\[[^\]]*\])?\{[^}]*\}/g;

/**
 * Every place a PDF page prints a passage, quoted as written or as LaTeX source, in order. A passage that holds a
 * reference is also looked for piece by piece around it, since the page prints a number there.
 */
export function findPrinted(text: string, passage: string, fewestLetters?: number): Range[] {
  const minLength = fewestLetters ?? (/\\[a-zA-Z]/.test(passage) ? MIN_FORMULA_KEY_LENGTH : MIN_KEY_LENGTH);
  const pieces = passage.split(REFERENCE).map(plainText);
  const forms = new Set([passage, plainText(passage), ...(pieces.length > 1 ? pieces : [])]);
  const merged: Range[] = [];
  for (const range of findPassages(text, [...forms], minLength)) {
    const last = merged.at(-1);
    if (last !== undefined && range.from < last.to) last.to = Math.max(last.to, range.to);
    else merged.push({ ...range });
  }
  return merged;
}

/** The symbols math commands print. A command not listed prints nothing a passage is compared on. */
const SYMBOLS: Record<string, string> = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ϵ", varepsilon: "ε", zeta: "ζ", eta: "η", theta: "θ",
  vartheta: "ϑ", iota: "ι", kappa: "κ", lambda: "λ", mu: "μ", nu: "ν", xi: "ξ", pi: "π", varpi: "ϖ", rho: "ρ",
  varrho: "ϱ", sigma: "σ", varsigma: "ς", tau: "τ", upsilon: "υ", phi: "ϕ", varphi: "φ", chi: "χ", psi: "ψ",
  omega: "ω", Gamma: "Γ", Delta: "Δ", Theta: "Θ", Lambda: "Λ", Xi: "Ξ", Pi: "Π", Sigma: "Σ", Upsilon: "Υ",
  Phi: "Φ", Psi: "Ψ", Omega: "Ω", ell: "ℓ", hbar: "ħ", equiv: "≡", neq: "≠", ne: "≠", leq: "≤", le: "≤",
  geq: "≥", ge: "≥", in: "∈", times: "×", cdot: "·", pm: "±", to: "→", infty: "∞", partial: "∂", nabla: "∇",
  bmod: "mod", mod: "mod",
};
/** Fence an unwrapped command argument while the next commands are read; neither is a brace nor a letter. */
const OPEN = "\u0002";
const CLOSE = "\u0003";
/** Operators LaTeX prints by name. */
const OPERATORS = new Set(["sin", "cos", "tan", "sinh", "cosh", "tanh", "exp", "log", "ln", "max", "min", "sup", "inf", "lim", "det", "dim", "ker", "arg", "gcd", "Pr"]);

/** LaTeX as a reader sees it in the PDF: references dropped, commands replaced by their text or symbol, accents bare. */
export function plainText(latex: string): string {
  let text = latex
    .replace(REFERENCE, "")
    .replace(/\\multicolumn\{[^{}]*\}\{(?:[^{}]|\{[^{}]*\})*\}/g, "")
    .replace(/\\['"`^~=.]\{?([a-zA-Z])\}?/g, "$1");
  // Innermost first, until nothing changes, so \pmod{\boldsymbol{\omega}} keeps its "mod". An unwrapped argument stays
  // fenced until the end, so \times\mathbb{Z} does not become the command \timesZ.
  for (let previous = ""; previous !== text; ) {
    previous = text;
    text = text.replace(/\\pmod\{([^{}]*)\}/g, " (mod $1)").replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}/g, `${OPEN}$1${CLOSE}`);
  }
  return squash(
    text
      .replace(/\\([a-zA-Z]+)\*?/g, (_, name: string) => SYMBOLS[name] ?? (OPERATORS.has(name) ? name : " "))
      .replace(/[{}\u0002\u0003]/g, "")
      .replace(/[$~]/g, " ")
      .replace(/\s+([,.;:])/g, "$1"),
  );
}
