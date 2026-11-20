import type { StreamParser, StringStream } from "@codemirror/language";

/*
 * A small BibTeX tokenizer for CodeMirror's `StreamLanguage`. BibTeX ignores everything outside an entry, so that
 * text is styled as a comment. Inside an entry the stages are: type, opening delimiter, citation key, then
 * `name = value` pairs separated by commas until the closing delimiter.
 */

type Stage = "open" | "key" | "field" | "equals" | "value" | "ignored";

interface Entry {
  stage: Stage;
  closer: ")" | "}";
  /** Whether a citation key is expected (regular entries) or fields start directly (@string) or a value (@preamble). */
  first: Stage;
  /** Open braces inside the value being read. */
  depth: number;
  /** Inside a double-quoted value. */
  quoted: boolean;
}

interface BibState {
  entry: Entry | null;
}

const ENTRY_TYPE = /^@[A-Za-z]+/;
const KEY = /^[^\s,={}()"#]+/;
const FIELD_NAME = /^[A-Za-z_][\w:.+-]*/;
const NUMBER = /^\d+/;
const MACRO = /^[A-Za-z_][\w:.+-]*/;

function firstStageOf(type: string): Stage {
  switch (type.toLowerCase()) {
    case "@string":
      return "field";
    case "@preamble":
      return "value";
    case "@comment":
      return "ignored";
    default:
      return "key";
  }
}

/** Reads the rest of a braced or quoted value on this line, keeping the depth for the next line. */
function readValue(stream: StringStream, entry: Entry): string {
  for (;;) {
    const char = stream.next();
    if (char === undefined) return "string";
    if (char === "\\") {
      stream.next();
    } else if (char === "{") {
      entry.depth += 1;
    } else if (char === "}") {
      entry.depth -= 1;
      if (entry.depth === 0 && !entry.quoted) return "string";
    } else if (char === '"' && entry.quoted && entry.depth === 0) {
      entry.quoted = false;
      return "string";
    }
  }
}

function insideEntry(stream: StringStream, entry: Entry): string | null {
  // A value that is still open continues on this line.
  if (entry.depth > 0 || entry.quoted) return readValue(stream, entry);
  if (stream.eatSpace()) return null;

  if (entry.stage === "ignored") {
    // `@comment` text runs to the closing delimiter, with nested braces balanced.
    return readIgnored(stream, entry);
  }
  const char = stream.peek();
  if (char === entry.closer) {
    stream.next();
    return finish(entry);
  }
  switch (entry.stage) {
    case "open":
      entry.closer = stream.next() === "(" ? ")" : "}";
      entry.stage = entry.first;
      return "bracket";
    case "key":
      if (stream.match(KEY)) {
        entry.stage = "field";
        return "labelName";
      }
      break;
    case "field":
      if (stream.match(FIELD_NAME)) {
        entry.stage = "equals";
        return "propertyName";
      }
      break;
    case "equals":
      if (stream.eat("=")) {
        entry.stage = "value";
        return "operator";
      }
      break;
    case "value":
      return valuePart(stream, entry);
  }
  if (stream.eat(",")) {
    entry.stage = "field";
    return null;
  }
  stream.next();
  return null;
}

function valuePart(stream: StringStream, entry: Entry): string | null {
  if (stream.eat(",")) {
    entry.stage = "field";
    return null;
  }
  if (stream.eat("#")) return "operator";
  if (stream.match(NUMBER)) return "number";
  if (stream.peek() === "{") {
    stream.next();
    entry.depth = 1;
    return readValue(stream, entry);
  }
  if (stream.peek() === '"') {
    stream.next();
    entry.quoted = true;
    return readValue(stream, entry);
  }
  if (stream.match(MACRO)) return "variableName";
  stream.next();
  return null;
}

function readIgnored(stream: StringStream, entry: Entry): string {
  if (entry.depth === 0) {
    // The brace after `@comment`.
    if (stream.eat("{")) {
      entry.depth = 1;
      return "bracket";
    }
    // `@comment` without a brace: the rest of the line is a comment.
    stream.skipToEnd();
    return "comment";
  }
  for (;;) {
    const char = stream.next();
    if (char === undefined) return "comment";
    if (char === "{") entry.depth += 1;
    else if (char === "}") entry.depth -= 1;
    if (entry.depth === 0) return "comment";
  }
}

function finish(entry: Entry): string {
  entry.stage = "open";
  entry.depth = 0;
  return "bracket";
}

export const bibtexParser: StreamParser<BibState> = {
  name: "bibtex",
  startState: () => ({ entry: null }),
  copyState: (state) => ({ entry: state.entry === null ? null : { ...state.entry } }),
  token(stream, state) {
    // A line that starts a new entry ends a broken one, so a typo does not swallow the rest of the file.
    if (stream.sol() && /^@[A-Za-z]/.test(stream.string)) state.entry = null;
    const entry = state.entry;
    if (entry === null) {
      if (stream.match(ENTRY_TYPE)) {
        state.entry = { stage: "open", closer: "}", first: firstStageOf(stream.current()), depth: 0, quoted: false };
        return "keyword";
      }
      // Skip to the next `@` (or the end of the line): this is free text that BibTeX ignores.
      stream.next();
      stream.skipTo("@") || stream.skipToEnd();
      return "comment";
    }
    return insideEntry(stream, entry);
  },
};
