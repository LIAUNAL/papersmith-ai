/** One replacement turning an old text into a new one. */
export interface TextChange {
  from: number;
  to: number;
  insert: string;
}

const isHighSurrogate = (code: number) => code >= 0xd800 && code <= 0xdbff;
const isLowSurrogate = (code: number) => code >= 0xdc00 && code <= 0xdfff;

/**
 * The smallest single replacement from `before` to `after`, or null when they are equal. Replacing only the
 * differing middle lets an editor keep the cursor, the selection and the scroll position outside of it.
 */
export function minimalChange(before: string, after: string): TextChange | null {
  if (before === after) return null;
  const shortest = Math.min(before.length, after.length);
  let start = 0;
  while (start < shortest && before.charCodeAt(start) === after.charCodeAt(start)) start += 1;
  // Never cut between the two halves of a character outside the basic plane.
  if (start > 0 && isHighSurrogate(before.charCodeAt(start - 1))) start -= 1;
  let endBefore = before.length;
  let endAfter = after.length;
  while (endBefore > start && endAfter > start && before.charCodeAt(endBefore - 1) === after.charCodeAt(endAfter - 1)) {
    endBefore -= 1;
    endAfter -= 1;
  }
  if (endBefore < before.length && isLowSurrogate(before.charCodeAt(endBefore))) {
    endBefore += 1;
    endAfter += 1;
  }
  return { from: start, to: endBefore, insert: after.slice(start, endAfter) };
}
