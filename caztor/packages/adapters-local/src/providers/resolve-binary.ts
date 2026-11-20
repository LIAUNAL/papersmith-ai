import type { FileSystem } from "../infra.ts";

const EXECUTABLE_BITS = 0o111;

/**
 * The absolute path of the first executable regular file called `name` in the `PATH` folders, or null. A relative or
 * empty `PATH` entry is skipped, so a file in the project folder can never be picked up by name.
 */
export async function resolveBinary(fs: FileSystem, name: string, pathEnv: string | undefined): Promise<string | null> {
  for (const folder of (pathEnv ?? "").split(":")) {
    if (!folder.startsWith("/")) continue;
    const candidate = `${folder.replace(/\/+$/, "")}/${name}`;
    try {
      const stats = await fs.stat(candidate);
      if (stats.isFile() && (stats.mode & EXECUTABLE_BITS) !== 0) return candidate;
    } catch {
      // Not here; the next folder.
    }
  }
  return null;
}
