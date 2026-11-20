import { fileURLToPath } from "node:url";

/**
 * The folder with the shipped agent definitions (`claude.md`, `opencode.md`, `codex.md`), found from this file's
 * location in the repository, so it does not depend on the directory the server was started from.
 */
export function defaultAgentsDir(): string {
  return fileURLToPath(new URL("../../../agents/", import.meta.url)).replace(/\/$/, "");
}
