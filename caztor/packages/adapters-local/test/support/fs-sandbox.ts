import { mkdtempSync, realpathSync, rmSync, symlinkSync, utimesSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach } from "vitest";
import type { FileSystem } from "../../src/infra.ts";
import { nodeFileSystem } from "../../src/node-infra.ts";
import { MemoryFileSystem } from "../fakes/memory-fs.ts";

export interface Sandbox {
  fs: FileSystem;
  /** Absolute path of an empty, existing directory. */
  root: string;
  /** Creates a symbolic link at `path` (absolute) pointing at the absolute `target`. */
  symlink(target: string, path: string): void;
  /** Sets the modification time like `touch -d`: the change time moves to now, as on a real disk. */
  setMtime(path: string, mtimeMs: number): void;
  /** Creates a file that is neither regular, a directory nor a link (a socket on disk, a marker in memory). */
  special(path: string): Promise<void>;
}

const tempDirs: string[] = [];
const servers: Server[] = [];

/** Call once at the top of a test file that uses `implementations`. */
export function cleanupSandboxes(): void {
  afterEach(() => {
    for (const server of servers.splice(0)) server.close();
    for (const dir of tempDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });
}

/** The same sandbox over the in-memory fake and the real Node file system in a temporary directory. */
export const implementations: [string, () => Sandbox][] = [
  [
    "MemoryFileSystem",
    () => {
      const fs = new MemoryFileSystem();
      return {
        fs,
        root: "/work",
        symlink: (target, path) => fs.symlink(target, path),
        setMtime: (path, mtimeMs) => fs.setMtime(path, mtimeMs),
        special: async (path) => fs.special(path),
      };
    },
  ],
  [
    "nodeFileSystem",
    () => {
      const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-sandbox-")));
      tempDirs.push(root);
      return {
        fs: nodeFileSystem,
        root,
        symlink: (target, path) => symlinkSync(target, path),
        setMtime: (path, mtimeMs) => utimesSync(path, mtimeMs / 1000, mtimeMs / 1000),
        special: (path) =>
          new Promise<void>((resolve, reject) => {
            const server = createServer();
            servers.push(server);
            server.once("error", reject);
            server.listen(path, () => resolve());
          }),
      };
    },
  ],
];
