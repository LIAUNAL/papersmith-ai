/** The most rows kept; older ones are dropped from the top. */
export const MAX_ROWS = 400;
/** The most characters kept in one row. */
export const MAX_COLUMNS = 2_000;
/** An escape sequence longer than this is not one: it is dropped. */
const MAX_ESCAPE = 256;

export interface TerminalText {
  feed(bytes: Uint8Array): void;
  /** The rows as plain text, trailing spaces and empty rows at the end removed. */
  text(): string;
}

/**
 * A small model of what a terminal would show of a CLI's output: enough of the cursor codes for line output, a spinner
 * that redraws its line, and a full-screen program that draws rows by number. Colours, titles and links are dropped.
 */
export function createTerminalText(): TerminalText {
  const decoder = new TextDecoder("utf-8");
  let rows: string[][] = [];
  let row = 0;
  let col = 0;
  /** Row 1 of a program that addresses rows by number; rows above it scrolled away. */
  let base = 0;
  let pending = "";

  const ensure = () => {
    while (rows.length <= row) rows.push([]);
  };
  const trim = () => {
    const extra = rows.length - MAX_ROWS;
    if (extra > 0) {
      rows = rows.slice(extra);
      row = Math.max(0, row - extra);
      base = Math.max(0, base - extra);
    }
  };
  const put = (character: string) => {
    ensure();
    const line = rows[row]!;
    if (col >= MAX_COLUMNS) return;
    while (line.length < col) line.push(" ");
    line[col] = character;
    col += 1;
  };
  const clearScreen = () => {
    rows = [];
    base = 0;
  };

  function csi(body: string) {
    const final = body.at(-1)!;
    const privateMode = body.startsWith("?");
    const params = (privateMode ? body.slice(1, -1) : body.slice(0, -1)).split(";").map((part) => Number.parseInt(part, 10));
    const n = (index: number, fallback: number) => (Number.isFinite(params[index]) ? params[index]! : fallback);
    if (privateMode) {
      if (final === "h" && params.includes(1049)) clearScreen();
      return;
    }
    switch (final) {
      case "H":
      case "f":
        row = base + Math.max(1, n(0, 1)) - 1;
        col = Math.max(1, n(1, 1)) - 1;
        trim();
        break;
      case "d":
        row = base + Math.max(1, n(0, 1)) - 1;
        trim();
        break;
      case "A":
        row = Math.max(base, row - Math.max(1, n(0, 1)));
        break;
      case "B":
        row += Math.max(1, n(0, 1));
        trim();
        break;
      case "C":
        col += Math.max(1, n(0, 1));
        break;
      case "D":
        col = Math.max(0, col - Math.max(1, n(0, 1)));
        break;
      case "G":
        col = Math.max(1, n(0, 1)) - 1;
        break;
      case "K": {
        ensure();
        const mode = n(0, 0);
        const line = rows[row]!;
        if (mode === 0) line.length = Math.min(line.length, col);
        else if (mode === 1) for (let index = 0; index <= col && index < line.length; index += 1) line[index] = " ";
        else rows[row] = [];
        break;
      }
      case "J": {
        const mode = n(0, 0);
        if (mode === 0) {
          ensure();
          rows[row]!.length = Math.min(rows[row]!.length, col);
          rows.length = row + 1;
        } else if (mode >= 2) clearScreen();
        break;
      }
      default:
        break;
    }
  }

  function consume(input: string) {
    let index = 0;
    while (index < input.length) {
      const character = input[index]!;
      if (character === "\u001b") {
        const next = input[index + 1];
        if (next === undefined) return input.slice(index);
        if (next === "[") {
          let end = index + 2;
          while (end < input.length && !/[@-~]/.test(input[end]!)) end += 1;
          if (end >= input.length) return end - index > MAX_ESCAPE ? "" : input.slice(index);
          csi(input.slice(index + 2, end + 1));
          index = end + 1;
          continue;
        }
        if (next === "]" || next === "P" || next === "_") {
          // An OSC (title, link, colour query) or a device string: up to BEL or ESC \.
          let end = index + 2;
          while (end < input.length && input[end] !== "\u0007" && !(input[end] === "\u001b" && input[end + 1] === "\\")) end += 1;
          if (end >= input.length) return end - index > MAX_ESCAPE ? "" : input.slice(index);
          index = input[end] === "\u0007" ? end + 1 : end + 2;
          continue;
        }
        if (next === "(" || next === ")" || next === "#") {
          if (index + 2 >= input.length) return input.slice(index);
          index += 3;
          continue;
        }
        index += 2;
        continue;
      }
      if (character === "\n") {
        row += 1;
        col = 0;
        ensure();
        trim();
      } else if (character === "\r") col = 0;
      else if (character === "\b") col = Math.max(0, col - 1);
      else if (character === "\t") col = Math.min(MAX_COLUMNS, (Math.floor(col / 8) + 1) * 8);
      else if (character >= " " && character !== "\u007f") put(character);
      index += 1;
    }
    return "";
  }

  return {
    feed(bytes) {
      pending = consume(pending + decoder.decode(bytes, { stream: true }));
    },
    text() {
      const lines = rows.map((line) => line.join("").trimEnd());
      while (lines.length > 0 && lines.at(-1) === "") lines.pop();
      return lines.join("\n");
    },
  };
}
