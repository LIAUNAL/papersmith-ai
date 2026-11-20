/**
 * A small Markdown reader for assistant text, which is untrusted. It produces a tree of plain data, never HTML:
 * raw HTML stays text, images are not loaded, only http, https and mailto links survive, and an unfinished
 * construct (a fence or an emphasis still being streamed) degrades to text or code instead of failing.
 */
export type Inline =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] };

export type Block =
  | { type: "paragraph"; inlines: Inline[] }
  | { type: "heading"; level: number; inlines: Inline[] }
  | { type: "code"; language: string; text: string }
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
  return inlines.map((inline) => (inline.type === "text" || inline.type === "code" ? inline.text : plainText(inline.children))).join("");
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
      blocks.push({ type: "code", language: fence[1] ?? "", text: body.join("\n") });
      continue;
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
      blocks.push({ type: "quote", inlines: parseInline(body.join(" ")) });
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
