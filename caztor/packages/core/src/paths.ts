import type { RelPath, Result, StoreError } from "./ports.ts";

/** Top-level names that are never reachable through the file API. */
const AGENT_AND_TOOL_ROOTS = [".caztor", ".claude", ".opencode", ".agents", ".git", "node_modules"] as const;
export const RESERVED_ROOTS = [...AGENT_AND_TOOL_ROOTS, ".papersmith", ".pi", ".mcp.json", ".env", ".env.local"] as const;
/** Deeper folders that hold secrets: PaperSmith keeps Kaggle accounts in this one. */
const SECRET_FOLDERS = ["skills/kaggle-accounts/store"] as const;

/** Whether a project-relative path is a folder that holds secrets, or lies inside one. */
export function isSecretPath(path: string): boolean {
  const lower = path.toLowerCase();
  return SECRET_FOLDERS.some((folder) => lower === folder || lower.startsWith(`${folder}/`));
}

/** The part below `path` of each folder holding secrets that `path` contains. */
export function secretFoldersBelow(path: string): string[] {
  const prefix = `${path.toLowerCase()}/`;
  return SECRET_FOLDERS.filter((folder) => folder.startsWith(prefix)).map((folder) => folder.slice(prefix.length));
}

const MAX_PATH_LENGTH = 1024;
// C0 control characters (including NUL) and DEL.
const CONTROL_CHARACTER = /[\u0000-\u001f\u007f]/;

function fail(code: "invalid_path" | "outside_root" | "hidden", path: string): Result<RelPath, StoreError> {
  return { ok: false, error: { code, path } };
}

/**
 * Validates a project-relative path before any disk access.
 *
 * Accepts only forward-slash paths made of plain segments. A leading `-` is rejected
 * so a path can never be read as a command-line flag when it reaches a subprocess.
 */
export function parseRelPath(input: string): Result<RelPath, StoreError> {
  const parsed = parseSnapshotPath(input);
  if (!parsed.ok) return parsed;
  if ((RESERVED_ROOTS as readonly string[]).includes((input.split("/")[0] ?? "").toLowerCase()) || isSecretPath(input)) return fail("hidden", input);
  return parsed;
}

/**
 * The rules for a path inside an undo snapshot. It reserves fewer names than the file API, so snapshots taken before
 * a name was hidden stay readable and an agent's edit to `.env` can still be undone.
 */
export function parseSnapshotPath(input: string): Result<RelPath, StoreError> {
  if (input.length === 0 || input.length > MAX_PATH_LENGTH) return fail("invalid_path", input);
  if (input.includes("\\") || CONTROL_CHARACTER.test(input)) return fail("invalid_path", input);
  if (input.startsWith("/")) return fail("outside_root", input);
  if (input.startsWith("-")) return fail("invalid_path", input);

  const segments = input.split("/");
  if (segments.includes("..")) return fail("outside_root", input);
  if (segments.some((segment) => segment === "" || segment === ".")) return fail("invalid_path", input);

  const root = (segments[0] ?? "").toLowerCase();
  if ((AGENT_AND_TOOL_ROOTS as readonly string[]).includes(root)) return fail("hidden", input);

  return { ok: true, value: input as RelPath };
}
