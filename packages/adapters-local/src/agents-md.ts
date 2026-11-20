import { AGENT_BLOCK_BEGIN, AGENT_BLOCK_END, AGENT_TARGETS, hashBytes } from "@caztor/core";
import type { ContentHash, StatePort } from "@caztor/core";
import { joinPath } from "./containment.ts";
import type { FileSystem } from "./infra.ts";

/** The managed block in `text`: where it starts and ends, none, or markers that cannot be trusted. */
export function findBlock(text: string): { kind: "none" } | { kind: "broken" } | { kind: "block"; start: number; end: number } {
  const begins = text.split(AGENT_BLOCK_BEGIN).length - 1;
  const ends = text.split(AGENT_BLOCK_END).length - 1;
  if (begins === 0 && ends === 0) return { kind: "none" };
  const start = text.indexOf(AGENT_BLOCK_BEGIN);
  const end = text.indexOf(AGENT_BLOCK_END);
  if (begins !== 1 || ends !== 1 || end < start) return { kind: "broken" };
  return { kind: "block", start, end: end + AGENT_BLOCK_END.length };
}

/** Hash of the text between the markers, which is what the state records for the block. Null when the block has no usual shape. */
export async function blockBodyHash(block: string): Promise<ContentHash | null> {
  const opening = `${AGENT_BLOCK_BEGIN}\n`;
  if (!block.startsWith(opening) || !block.endsWith(AGENT_BLOCK_END)) return null;
  return hashBytes(new TextEncoder().encode(block.slice(opening.length, block.length - AGENT_BLOCK_END.length)));
}

/** A file this large is never one Caztor wrote. */
const MAX_OWN_BYTES = 256 * 1024;

export interface AgentsMdVisibilityOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  state: StatePort;
}

/**
 * True while the top-level AGENTS.md is exactly what Caztor wrote: the state says Caztor created it, and the file still
 * holds nothing but the block whose body has the recorded hash. Anything else, such as a file the user rewrote outside
 * the app, counts as the user's and is shown.
 */
export function createAgentsMdVisibility(options: AgentsMdVisibilityOptions): () => Promise<boolean> {
  const target = AGENT_TARGETS.codex;
  return async () => {
    const known = (await options.state.load()).provisioned[target];
    if (known?.createdByCaztor !== true) return false;
    try {
      const full = joinPath(await options.fs.realpath(options.root), target);
      const stats = await options.fs.lstat(full);
      if (stats.isSymbolicLink() || !stats.isFile() || stats.size > MAX_OWN_BYTES) return false;
      const text = new TextDecoder().decode(await options.fs.readFile(full));
      const found = findBlock(text);
      if (found.kind !== "block") return false;
      if ((text.slice(0, found.start) + text.slice(found.end)).trim() !== "") return false;
      return (await blockBodyHash(text.slice(found.start, found.end))) === known.hash;
    } catch {
      return false;
    }
  };
}
