import type { FileSystem } from "../infra.ts";

/** Longest log that is read whole to look for diagnostics. */
export const PARSE_LIMIT_BYTES = 8 * 1024 * 1024;
/** Of a longer log only this many bytes from the end are read for diagnostics: that is where a run ends and reports. */
export const PARSE_TAIL_BYTES = 4 * 1024 * 1024;
/** A log kept or served keeps this much of its start and this much of its end; a shorter log is kept whole. */
export const KEEP_HEAD_BYTES = 256 * 1024;
export const KEEP_TAIL_BYTES = 768 * 1024;

function isMissing(error: unknown): boolean {
  return (error as { code?: string } | null)?.code === "ENOENT";
}

async function sizeOf(fs: FileSystem, file: string): Promise<number | null> {
  try {
    const stats = await fs.stat(file);
    return stats.isFile() ? stats.size : null;
  } catch (error) {
    if (isMissing(error)) return null;
    throw error;
  }
}

/** The log as text for the diagnostics parsers, without reading more than the limits allow. Null when there is no log. */
export async function readLogForParsing(fs: FileSystem, file: string): Promise<{ text: string; skippedBytes: number } | null> {
  const size = await sizeOf(fs, file);
  if (size === null) return null;
  const decoder = new TextDecoder();
  if (size <= PARSE_LIMIT_BYTES) return { text: decoder.decode(await fs.readFile(file)), skippedBytes: 0 };
  const tail = await fs.readRange(file, size - PARSE_TAIL_BYTES, PARSE_TAIL_BYTES);
  return { text: decoder.decode(tail), skippedBytes: size - tail.length };
}

/**
 * The log in a size that is fit to copy, serve and show: whole when it is short, otherwise its start and its end with a
 * line between them that says how much was left out. Null when there is no log.
 */
export async function readBoundedLog(fs: FileSystem, file: string): Promise<{ bytes: Uint8Array; omittedBytes: number } | null> {
  const size = await sizeOf(fs, file);
  if (size === null) return null;
  if (size <= KEEP_HEAD_BYTES + KEEP_TAIL_BYTES) return { bytes: await fs.readFile(file), omittedBytes: 0 };
  const head = await fs.readRange(file, 0, KEEP_HEAD_BYTES);
  const tail = await fs.readRange(file, size - KEEP_TAIL_BYTES, KEEP_TAIL_BYTES);
  const omittedBytes = size - head.length - tail.length;
  const marker = new TextEncoder().encode(
    `\n\n[Caztor left out ${omittedBytes} bytes from the middle of this log because it is too large to show. The start and the end are kept.]\n\n`,
  );
  const bytes = new Uint8Array(head.length + marker.length + tail.length);
  bytes.set(head, 0);
  bytes.set(marker, head.length);
  bytes.set(tail, head.length + marker.length);
  return { bytes, omittedBytes };
}
