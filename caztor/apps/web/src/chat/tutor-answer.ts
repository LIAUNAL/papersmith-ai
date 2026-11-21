/** Reading a PaperSmith tutor's JSON answer (math-tutor, experiments-tutor), whole or while it arrives. */

/** A PaperSmith tutor's structured turn (math-tutor, experiments-tutor), as its JSON block says it. */
export interface TutorAnswer {
  reply: string;
  [field: string]: unknown;
}

const FENCE = /```json[ \t]*\n([\s\S]*?)\n```/;

/** The text around a tutor's JSON answer, and the answer; null when the text holds no such block. */
export function splitTutorAnswer(text: string): { before: string; answer: TutorAnswer; raw: string; after: string } | null {
  const match = FENCE.exec(text);
  if (match === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(match[1]!);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed) || typeof (parsed as { reply?: unknown }).reply !== "string") return null;
  return { before: text.slice(0, match.index).trim(), answer: parsed as TutorAnswer, raw: match[1]!, after: text.slice(match.index + match[0].length).trim() };
}

const OPEN_FENCE = /```json[ \t]*\n/;

/** A key the object has no value for yet: `"key"` or `"key":` right after `{` or `,`, dropped with its comma. */
function withoutDanglingKey(text: string, closer: string | undefined): string {
  if (closer !== "}") return text;
  const key = /(^|[{,])\s*"(?:[^"\\]|\\.)*"\s*:?$/.exec(text);
  if (key === null) return text;
  return text.slice(0, key.index + key[1]!.length).replace(/,$/, "");
}

/**
 * `body`, the start of a JSON value still being written, closed so it parses: an open string is ended (an escape cut
 * in two is left out), a key still without its value is dropped, and the open objects and arrays are closed. When the
 * end cannot be closed so, it is cut back to the previous comma or opening bracket and tried again.
 */
export function closePartialJson(body: string): unknown {
  let text = body;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const closers: string[] = [];
    const boundaries: number[] = [];
    let inString = false;
    let escaped = false;
    let escapeAt = -1;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i]!;
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") {
          escaped = true;
          escapeAt = i;
        }
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') inString = true;
      else if (char === "{" || char === "[") {
        closers.push(char === "{" ? "}" : "]");
        boundaries.push(i + 1);
      } else if (char === "}" || char === "]") closers.pop();
      else if (char === ",") boundaries.push(i);
    }
    let closed = text;
    if (inString) {
      // An escape cut in two (a lone backslash, or \u with fewer than four digits) waits for the rest.
      const cutEscape = escaped || (escapeAt !== -1 && text[escapeAt + 1] === "u" && !/^[0-9a-fA-F]{4}/.test(text.slice(escapeAt + 2, escapeAt + 6)) && text.length < escapeAt + 6);
      closed = (cutEscape ? closed.slice(0, escapeAt) : closed) + '"';
    }
    closed = withoutDanglingKey(closed.replace(/\s+$/, ""), closers.at(-1)).replace(/,\s*$/, "");
    try {
      return JSON.parse(closed + closers.reverse().join(""));
    } catch {
      const cut = boundaries.filter((at) => at < text.length).pop();
      if (cut === undefined || cut <= 0) return undefined;
      text = text.slice(0, cut);
    }
  }
  return undefined;
}

/**
 * A tutor's JSON answer that is still arriving: the fence is open and the object not finished, so what is written so
 * far is read as an answer (each field once it has begun, the last one as far as it goes). Null when the text is not
 * such an answer. `reply` is null while the fields before it are still being written.
 */
export function streamingTutorAnswer(text: string): { before: string; reply: string | null; answer: TutorAnswer | null } | null {
  if (FENCE.test(text)) return null;
  const open = OPEN_FENCE.exec(text);
  if (open === null) return null;
  const body = text.slice(open.index + open[0].length);
  if (!body.trimStart().startsWith("{") && body.trim() !== "") return null;
  const before = text.slice(0, open.index).trim();
  const parsed = body.trim() === "" ? undefined : closePartialJson(body);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return { before, reply: null, answer: null };
  const fields = parsed as Record<string, unknown>;
  const reply = typeof fields["reply"] === "string" ? fields["reply"] : null;
  return { before, reply, answer: { ...fields, reply: reply ?? "" } };
}
