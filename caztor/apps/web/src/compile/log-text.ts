/** The raw log view never puts more than this many characters into the page. */
export const MAX_SHOWN_LOG_CHARS = 200_000;

/** The end of a long log, where a run reports its problems, and how many characters before it are left out. */
export function boundLogText(text: string): { text: string; hidden: number } {
  if (text.length <= MAX_SHOWN_LOG_CHARS) return { text, hidden: 0 };
  return { text: text.slice(text.length - MAX_SHOWN_LOG_CHARS), hidden: text.length - MAX_SHOWN_LOG_CHARS };
}
