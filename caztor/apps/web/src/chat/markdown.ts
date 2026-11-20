/**
 * A small Markdown reader for assistant text, which is untrusted. It produces a tree of plain data, never HTML:
 * raw HTML stays text, images are not loaded, only http, https and mailto links survive, and an unfinished
 * construct (a fence or an emphasis still being streamed) degrades to text or code instead of failing.
 * Mathematics (`$…$`, `\(…\)`, `$$…$$`, `\[…\]`, and fences tagged latex, tex or math) is kept as its TeX
 * source, read before emphasis so a subscript's `_` is never taken for one.
 */
export type Inline =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] }
  | { type: "math"; tex: string; display: boolean };

export type Block =
  | { type: "paragraph"; inlines: Inline[] }
  | { type: "heading"; level: number; inlines: Inline[] }
  | { type: "code"; language: string; text: string }
  | { type: "math"; tex: string }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "quote"; inlines: Inline[] }
  | { type: "rule" };

const SAFE_PROTOCOLS = ["http:", "https:", "mailto:"];
const isWordChar = (char: string | undefined): boolean => char !== undefined && /[\p{L}\p{N}]/u.test(char);

/** Returns the link target when it is safe to offer, else null. */
function safeHref(raw: string): string | null {
  try {
    const url = new URL(raw);
    return SAFE_PROTOCOLS.includes(url.protocol) ? raw : null;
  } catch {
    return null;
  }
}

function plainText(inlines: Inline[]): string {
  return inlines.map((inline) => (inline.type === "text" || inline.type === "code" ? inline.text : inline.type === "math" ? inline.tex : plainText(inline.children))).join("");
}

/** Reads `[label](target)` at `start` (the `[`). Returns the label, the target and where it ends. */
function readLink(src: string, start: number): { label: string; target: string; end: number } | null {
  const close = src.indexOf("]", start + 1);
  if (close === -1 || src[close + 1] !== "(") return null;
  let depth = 1;
  let i = close + 2;
  for (; i < src.length && depth > 0; i += 1) {
    const char = src[i]!;
    if (/\s/.test(char)) return null;
    if (char === "(") depth += 1;
    else if (char === ")") depth -= 1;
  }
  if (depth !== 0) return null;
  return { label: src.slice(start + 1, close), target: src.slice(close + 2, i - 1), end: i };
}

/**
 * Mathematics starting at `at`: `$$…$$` and `\[…\]` as display, `\(…\)` and `$…$` inline. A single `$` opens only
 * when a non-space follows and closes only after a non-space and before a non-digit, so prices ("$5 and $10") stay
 * text. An escaped `\$` is text.
 */
function readMath(src: string, at: number): { tex: string; display: boolean; end: number } | null {
  if (src[at - 1] === "\\" && src[at] === "$") return null;
  const pairs: Array<[string, string, boolean]> = [
    ["$$", "$$", true],
    ["\\[", "\\]", true],
    ["\\(", "\\)", false],
  ];
  for (const [open, close, display] of pairs) {
    if (!src.startsWith(open, at)) continue;
    const end = src.indexOf(close, at + open.length);
    const tex = end === -1 ? "" : src.slice(at + open.length, end).trim();
    return tex === "" ? null : { tex, display, end: end + close.length };
  }
  if (src[at] !== "$" || /\s/.test(src[at + 1] ?? " ")) return null;
  for (let end = src.indexOf("$", at + 1); end !== -1; end = src.indexOf("$", end + 1)) {
    if (src[end - 1] === "\\") continue;
    if (/\s/.test(src[end - 1]!) || /\d/.test(src[end + 1] ?? "")) return null;
    const tex = src.slice(at + 1, end);
    return tex.includes("\n") ? null : { tex, display: false, end: end + 1 };
  }
  return null;
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let text = "";
  const flush = () => {
    if (text !== "") out.push({ type: "text", text });
    text = "";
  };
  const push = (inline: Inline) => {
    flush();
    out.push(inline);
  };
  let i = 0;
  while (i < src.length) {
    const char = src[i]!;
    const math = readMath(src, i);
    if (math !== null) {
      push({ type: "math", tex: math.tex, display: math.display });
      i = math.end;
      continue;
    }
    if (char === "`") {
      let run = 1;
      while (src[i + run] === "`") run += 1;
      const fence = "`".repeat(run);
      const close = src.indexOf(fence, i + run);
      if (close > i + run) {
        push({ type: "code", text: src.slice(i + run, close) });
        i = close + run;
        continue;
      }
      text += fence;
      i += run;
      continue;
    }
    if (char === "[" || (char === "!" && src[i + 1] === "[")) {
      const image = char === "!";
      const link = readLink(src, image ? i + 1 : i);
      if (link !== null) {
        const children = parseInline(link.label);
        if (image) text += `[image: ${plainText(children)}]`;
        else {
          const href = safeHref(link.target);
          if (href === null) text += plainText(children);
          else push({ type: "link", href, children });
        }
        i = link.end;
        continue;
      }
    }
    if (char === "*" || char === "_") {
      const double = src[i + 1] === char;
      const size = double ? 2 : 1;
      const marker = char.repeat(size);
      const intraword = char === "_" && isWordChar(src[i - 1]);
      let close = -1;
      if (!intraword && !/\s/.test(src[i + size] ?? " ")) {
        close = src.indexOf(marker, i + size + 1);
        // A single marker must not be the start of a double one, and `_` must end a word.
        while (close !== -1 && ((!double && src[close + 1] === char) || (char === "_" && isWordChar(src[close + size])) || /\s/.test(src[close - 1] ?? ""))) {
          close = src.indexOf(marker, close + 1);
        }
      }
      if (close !== -1) {
        const children = parseInline(src.slice(i + size, close));
        push(double ? { type: "strong", children } : { type: "em", children });
        i = close + size;
        continue;
      }
      text += marker;
      i += size;
      continue;
    }
    text += char;
    i += 1;
  }
  flush();
  return out;
}

const FENCE = /^ {0,3}```\s*([^\s`]*)/;
/** Fence languages whose body is always a formula. */
const MATH_FENCES: ReadonlySet<string> = new Set(["math", "katex"]);
/** Fence languages that hold either a formula or LaTeX source the assistant proposes. */
const LATEX_FENCES: ReadonlySet<string> = new Set(["latex", "tex"]);
/** What only LaTeX source has: sectioning, references, text styling, environments of a document, comments. */
const SOURCE_ONLY =
  /\\(?:documentclass|usepackage|input|include|section|subsection|subsubsection|paragraph|chapter|caption|label|ref|eqref|autoref|cref|cite[a-z]*|footnote|emph|textbf|textit|item|begin\{(?:document|figure|table|itemize|enumerate|abstract))\b|(?:^|[^\\])%/;

/** A latex or tex fence is shown as a formula unless it holds something only LaTeX source has. */
export const looksLikeFormula = (tex: string): boolean => tex.trim() !== "" && !SOURCE_ONLY.test(tex);
const RULE = /^ {0,3}([-*_])(\s*\1){2,}\s*$/;
const HEADING = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const NUMBERED = /^\s{0,3}\d+[.)]\s+(.*)$/;
const QUOTE = /^ {0,3}>\s?(.*)$/;

export function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const endParagraph = () => {
    if (paragraph.length > 0) blocks.push({ type: "paragraph", inlines: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]!;
    const fence = FENCE.exec(line);
    if (fence !== null) {
      endParagraph();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^ {0,3}```\s*$/.test(lines[i]!)) {
        body.push(lines[i]!);
        i += 1;
      }
      const language = (fence[1] ?? "").toLowerCase();
      const text = body.join("\n");
      const formula = MATH_FENCES.has(language) || (LATEX_FENCES.has(language) && looksLikeFormula(text));
      blocks.push(formula ? { type: "math", tex: text } : { type: "code", language: fence[1] ?? "", text });
      continue;
    }
    // A display block whose `$$` or `\[` stands on its own line, with the formula on the lines below.
    const opener = /^\s*(\$\$|\\\[)\s*$/.exec(line);
    if (opener !== null) {
      const closer = opener[1] === "$$" ? "$$" : "\\]";
      const end = lines.findIndex((next, at) => at > i && next.trim() === closer);
      if (end !== -1) {
        endParagraph();
        blocks.push({ type: "math", tex: lines.slice(i + 1, end).join("\n").trim() });
        i = end;
        continue;
      }
    }
    if (line.trim() === "") {
      endParagraph();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading !== null) {
      endParagraph();
      blocks.push({ type: "heading", level: heading[1]!.length, inlines: parseInline(heading[2]!) });
      continue;
    }
    if (RULE.test(line)) {
      endParagraph();
      blocks.push({ type: "rule" });
      continue;
    }
    const quote = QUOTE.exec(line);
    if (quote !== null) {
      endParagraph();
      const body = [quote[1]!];
      while (i + 1 < lines.length && QUOTE.test(lines[i + 1]!)) body.push(QUOTE.exec(lines[++i]!)![1]!);
      const quoted = body.join(" ").trim();
      // A quoted equation of the paper's source (a command, no `$`, nothing only prose has) is shown typeset.
      const formula = !quoted.includes("$") && /\\[a-zA-Z]/.test(quoted) && looksLikeFormula(quoted);
      blocks.push({ type: "quote", inlines: formula ? [{ type: "math", tex: quoted, display: true }] : parseInline(quoted) });
      continue;
    }
    const ordered = NUMBERED.test(line);
    if (ordered || BULLET.test(line)) {
      endParagraph();
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [pattern.exec(line)![1]!];
      while (i + 1 < lines.length) {
        const next = lines[i + 1]!;
        const item = pattern.exec(next);
        if (item !== null && !RULE.test(next)) items.push(item[1]!);
        else if (/^\s{2,}\S/.test(next) && !BULLET.test(next) && !NUMBERED.test(next)) items[items.length - 1] += ` ${next.trim()}`;
        else break;
        i += 1;
      }
      blocks.push({ type: "list", ordered, items: items.map(parseInline) });
      continue;
    }
    paragraph.push(line.trim());
  }
  endParagraph();
  return blocks;
}
