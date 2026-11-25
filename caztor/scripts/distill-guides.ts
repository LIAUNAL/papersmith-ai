/**
 * Regenerates `guides/` and `LICENSES/Apache-2.0.txt` from a papersmith-ai checkout.
 *
 * Usage: node scripts/distill-guides.ts <papersmith-dir> [commit]
 *
 * The sources are read with `git show <commit>:<path>`, so the result does not depend on the checkout's
 * working tree or on which commit it has checked out. The checkout is only read.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { GUIDE_SOURCE_FILES, buildGuideSet, findMissingEvidence } from "../packages/adapters-local/src/guides/build-set.ts";

export const DEFAULT_COMMIT = "1f09516";
export const REPOSITORY_URL = "https://github.com/Daprosero/papersmith-ai";

function show(dir: string, commit: string, path: string): string {
  return execFileSync("git", ["-C", dir, "show", `${commit}:${path}`], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
}

export interface BuiltFromRepository {
  readonly files: Record<string, string>;
  readonly license: string;
}

/** Builds the guide files and the license text from `commit` of the repository at `dir`. */
export function buildFromRepository(dir: string, commit: string): BuiltFromRepository {
  try {
    execFileSync("git", ["-C", dir, "rev-parse", "--verify", "--quiet", `${commit}^{commit}`], { stdio: "ignore" });
  } catch {
    throw new Error(`Commit ${commit} does not exist in ${dir}`);
  }
  const sources: Record<string, string> = {};
  for (const file of GUIDE_SOURCE_FILES) sources[file] = show(dir, commit, `sections/${file}`);
  const missing = findMissingEvidence(sources);
  if (missing.length > 0) throw new Error(`Shared conventions cite text that is not in the sources:\n${missing.join("\n")}`);
  const set = buildGuideSet({
    sources,
    commit,
    repository: REPOSITORY_URL,
    sha256: (text) => createHash("sha256").update(text).digest("hex"),
  });
  return { files: set.files, license: show(dir, commit, "LICENSE") };
}

function main(): void {
  const [dir, commit = DEFAULT_COMMIT] = process.argv.slice(2);
  if (dir === undefined) throw new Error("Usage: node scripts/distill-guides.ts <papersmith-dir> [commit]");
  const root = join(dirname(fileURLToPath(import.meta.url)), "..");
  const built = buildFromRepository(dir, commit);
  mkdirSync(join(root, "guides"), { recursive: true });
  mkdirSync(join(root, "LICENSES"), { recursive: true });
  for (const [name, content] of Object.entries(built.files)) writeFileSync(join(root, "guides", name), content);
  writeFileSync(join(root, "LICENSES", "Apache-2.0.txt"), built.license);
  console.log(`Wrote ${Object.keys(built.files).length} files to guides/ and LICENSES/Apache-2.0.txt from ${commit}.`);
}

if (import.meta.main) main();
