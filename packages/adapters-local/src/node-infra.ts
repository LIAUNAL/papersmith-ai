import { type ChildProcessWithoutNullStreams, spawn as nodeSpawn } from "node:child_process";
import { type Dirent, type FSWatcher, lstatSync, readdirSync, watch as nodeWatch, type Stats } from "node:fs";
import * as fsp from "node:fs/promises";
import { join } from "node:path";
import { RESERVED_ROOTS } from "@caztor/core";
import type { ChildHandle, Clock, DirectoryWatcher, FileSystem, FsDirent, FsStats, ProcessSpawner, SpawnSpec } from "./infra.ts";

export interface NodeSpawnerDeps {
  spawn?: typeof nodeSpawn;
  kill?: (pid: number, signal: NodeJS.Signals) => void;
}

const emptyOutput: AsyncIterable<Uint8Array> = {
  [Symbol.asyncIterator]: () => ({ next: () => Promise.resolve({ value: undefined, done: true }) }),
};

function failedHandle(error: unknown): ChildHandle {
  const exit = Promise.reject<{ code: number | null; signal: string | null }>(error);
  exit.catch(() => {});
  return { stdout: emptyOutput, stderr: emptyOutput, exit, killGroup() {} };
}

/**
 * Real process spawner. Never uses a shell, runs every child in its own process group and
 * hands it exactly `spec.env`, so nothing from the server environment leaks through.
 */
export function createNodeSpawner(deps: NodeSpawnerDeps = {}): ProcessSpawner {
  const spawnProcess = deps.spawn ?? nodeSpawn;
  const kill = deps.kill ?? ((pid: number, signal: NodeJS.Signals) => process.kill(pid, signal));

  return {
    spawn(spec: SpawnSpec): ChildHandle {
      let child: ChildProcessWithoutNullStreams;
      try {
        child = spawnProcess(spec.file, [...spec.args], {
          cwd: spec.cwd,
          env: { ...spec.env },
          shell: false,
          detached: true,
          stdio: ["pipe", "pipe", "pipe"],
        });
      } catch (error) {
        // Node throws synchronously for invalid arguments (for example a NUL byte); report it like any other start failure.
        return failedHandle(error);
      }

      // The child may exit before reading its input; that is reported through `exit`, not here.
      child.stdin.on("error", () => {});
      if (spec.stdin !== undefined) child.stdin.write(spec.stdin);
      if (spec.interactive !== true) child.stdin.end();

      const exit = new Promise<{ code: number | null; signal: string | null }>((resolve, reject) => {
        child.once("error", reject);
        child.once("close", (code: number | null, signal: string | null) => resolve({ code, signal }));
      });
      exit.catch(() => {});

      // Once the child has been reaped its pid may be reused, so the group must not be signalled any more.
      let exited = false;
      child.once("exit", () => (exited = true));
      child.once("close", () => (exited = true));

      return {
        stdout: child.stdout,
        stderr: child.stderr,
        exit,
        write(text) {
          if (spec.interactive === true && !exited && child.stdin.writable) child.stdin.write(text);
        },
        killGroup(signal) {
          if (child.pid === undefined || exited) return;
          try {
            kill(-child.pid, signal);
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
          }
        },
      };
    },
  };
}

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimeout(fn, ms) {
    const timer = setTimeout(fn, ms);
    return () => clearTimeout(timer);
  },
};

/** Node reports the file type in `mode`; the interface exposes the permission bits only. */
function withPermissionBits(stats: Stats): FsStats {
  return {
    size: stats.size,
    mtimeMs: stats.mtimeMs,
    ctimeMs: stats.ctimeMs,
    mode: stats.mode & 0o7777,
    uid: stats.uid,
    id: `${stats.dev}:${stats.ino}`,
    isFile: () => stats.isFile(),
    isDirectory: () => stats.isDirectory(),
    isSymbolicLink: () => stats.isSymbolicLink(),
  };
}

export const nodeFileSystem: FileSystem = {
  async readFile(path) {
    return new Uint8Array(await fsp.readFile(path));
  },
  async readRange(path, start, length) {
    const handle = await fsp.open(path, "r");
    try {
      const buffer = new Uint8Array(length);
      const { bytesRead } = await handle.read(buffer, 0, length, start);
      return buffer.subarray(0, bytesRead);
    } finally {
      await handle.close();
    }
  },
  async writeFile(path, data, opts) {
    await fsp.writeFile(path, data, {
      ...(opts?.exclusive ? { flag: "wx" } : {}),
      ...(opts?.mode !== undefined ? { mode: opts.mode } : {}),
    });
  },
  async mkdir(path, opts) {
    await fsp.mkdir(path, { ...(opts?.recursive ? { recursive: true } : {}), ...(opts?.mode !== undefined ? { mode: opts.mode } : {}) });
  },
  async readdir(path): Promise<FsDirent[]> {
    return fsp.readdir(path, { withFileTypes: true });
  },
  async stat(path): Promise<FsStats> {
    return withPermissionBits(await fsp.stat(path));
  },
  async lstat(path): Promise<FsStats> {
    return withPermissionBits(await fsp.lstat(path));
  },
  realpath: (path) => fsp.realpath(path),
  rename: (from, to) => fsp.rename(from, to),
  async rm(path, opts) {
    await fsp.rm(path, { recursive: opts?.recursive ?? false, force: opts?.force ?? false });
  },
  copyFile: (from, to) => fsp.copyFile(from, to),
  chmod: (path, mode) => fsp.chmod(path, mode),
  async mkdtemp(prefix) {
    const dir = await fsp.mkdtemp(prefix);
    await fsp.chmod(dir, 0o700);
    return dir;
  },
};

/** Top-level folders the store never shows or touches: no watcher is opened inside them. */
const UNWATCHED_ROOTS: ReadonlySet<string> = new Set(RESERVED_ROOTS);

/**
 * Watches a folder tree with one non-recursive `fs.watch` per folder, added as folders appear and removed as they
 * disappear. Reserved top-level folders and symbolic links are never entered.
 *
 * A single recursive watch is not used because on Node 26 for Linux it stops reporting in-place writes to a path after
 * that path was replaced by a rename, which is exactly how the project store saves a file. A watch on the parent
 * folder keeps seeing the name whatever happens to the file behind it. Does not keep the process alive.
 */
/** Device and inode of a folder, or null when it cannot be looked at. */
function identityOf(path: string): string | null {
  try {
    const stats = lstatSync(path);
    return `${stats.dev}:${stats.ino}`;
  } catch {
    return null;
  }
}

const isGone = (error: unknown) => (error as NodeJS.ErrnoException).code === "ENOENT";

function watchTree(root: string, listener: (relativePath: string | null) => void, onError: (error: Error) => void): () => void {
  const handles = new Map<string, FSWatcher>();
  let closed = false;
  let rootId = identityOf(root);
  const child = (rel: string, name: string) => (rel === "" ? name : `${rel}/${name}`);
  const absolute = (rel: string) => (rel === "" ? root : join(root, ...rel.split("/")));

  function drop(rel: string): void {
    for (const [key, handle] of [...handles]) {
      if (key !== rel && !key.startsWith(`${rel}/`)) continue;
      handle.close();
      handles.delete(key);
    }
  }

  function arm(rel: string): void {
    if (closed || handles.has(rel)) return;
    let handle: FSWatcher;
    try {
      handle = nodeWatch(absolute(rel), { persistent: false }, (_event, name) => onEntry(rel, name === null ? null : String(name)));
    } catch (error) {
      if (rel === "") throw error;
      // A folder that vanished is not a failure; one that cannot be watched leaves its files to the rescans.
      if (!isGone(error)) onError(error as Error);
      return;
    }
    handle.on("error", (error) => {
      if (rel !== "") drop(rel);
      if (rel === "" || !isGone(error)) onError(error);
    });
    handles.set(rel, handle);
    let entries: Dirent[];
    try {
      entries = readdirSync(absolute(rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.isDirectory() && !(rel === "" && UNWATCHED_ROOTS.has(entry.name))) arm(child(rel, entry.name));
    }
  }

  function onEntry(rel: string, name: string | null): void {
    if (closed) return;
    if (rel === "" && identityOf(root) !== rootId) {
      // The project folder was removed or replaced: this watch follows the old one and will never report again.
      rootId = null;
      onError(new Error("The project folder was replaced"));
      return;
    }
    if (name === null) {
      listener(null);
      return;
    }
    if (rel === "" && UNWATCHED_ROOTS.has(name)) return;
    const path = child(rel, name);
    listener(path);
    let isFolder = false;
    try {
      isFolder = lstatSync(absolute(path)).isDirectory();
    } catch {
      // Gone: nothing below it can be watched any more.
    }
    if (isFolder) arm(path);
    else drop(path);
  }

  arm("");
  return () => {
    closed = true;
    for (const handle of handles.values()) handle.close();
    handles.clear();
  };
}

export const nodeDirectoryWatcher: DirectoryWatcher = {
  watch: watchTree,
};
