import { hashBytes, type ContentHash, type RelPath } from "@caztor/core";
import type { FileSystem, FsDirent } from "../../src/infra.ts";
import { createProjectStore, type ProjectStore } from "../../src/project-store.ts";
import { createUserWriteLog } from "../../src/user-writes.ts";
import { createSnapshotStore, type SnapshotStoreOptions } from "../../src/snapshot-store.ts";
import { FakeClock } from "../fakes/fake-clock.ts";
import { implementations, type Sandbox } from "../support/fs-sandbox.ts";

export const encode = (text: string) => new TextEncoder().encode(text);
export const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
export const rel = (path: string) => path as RelPath;
export const hashOf = (text: string): Promise<ContentHash> => hashBytes(encode(text));

export { implementations };

/** A time far enough ahead of every file's modification time that nothing counts as just written. */
export const FAR_FUTURE = Date.now() + 3_600_000;

/** Wraps a file system so tests can watch or break individual operations. */
export interface Hooks {
  readFile?: (path: string) => void | Promise<void>;
  writeFile?: (path: string) => void | Promise<void>;
  /** Replaces what a folder listing returns, for example to add a name the disk cannot open. */
  readdir?: (path: string, entries: FsDirent[]) => FsDirent[];
}
export function hooked(fs: FileSystem, hooks: Hooks): FileSystem {
  return {
    readRange: (path, start, length) => fs.readRange(path, start, length),
    readFile: async (path) => {
      await hooks.readFile?.(path);
      return fs.readFile(path);
    },
    writeFile: async (path, data, opts) => {
      await hooks.writeFile?.(path);
      return fs.writeFile(path, data, opts);
    },
    mkdir: (path, opts) => fs.mkdir(path, opts),
    readdir: async (path) => {
      const entries = await fs.readdir(path);
      return hooks.readdir?.(path, entries) ?? entries;
    },
    stat: (path) => fs.stat(path),
    lstat: (path) => fs.lstat(path),
    realpath: (path) => fs.realpath(path),
    rename: (from, to) => fs.rename(from, to),
    rm: (path, opts) => fs.rm(path, opts),
    copyFile: (from, to) => fs.copyFile(from, to),
    chmod: (path, mode) => fs.chmod(path, mode),
    mkdtemp: (prefix) => fs.mkdtemp(prefix),
  };
}

export async function setupSnapshots(
  create: () => Sandbox,
  options: { hooks?: Hooks; clockStart?: number; limits?: SnapshotStoreOptions["limits"]; skipAgentsMd?: boolean } = {},
) {
  const box = create();
  const project = `${box.root}/project`;
  await box.fs.mkdir(project, { recursive: true });
  const fs = options.hooks === undefined ? box.fs : hooked(box.fs, options.hooks);
  const clock = new FakeClock(options.clockStart ?? FAR_FUTURE);
  const userWrites = createUserWriteLog();
  const store: ProjectStore = createProjectStore({ fs, root: project, userWrites });
  const raw = createSnapshotStore({ fs, root: project, store, clock, ...(options.limits === undefined ? {} : { limits: options.limits }), ...(options.skipAgentsMd === undefined ? {} : { skipAgentsMd: () => options.skipAgentsMd === true }) });

  /** The store as most tests use it: a failure is thrown, so a test reads the happy path without unwrapping. */
  const snapshots = {
    capture: raw.capture,
    restore: raw.restore,
    async diff(...args: Parameters<typeof raw.diff>) {
      const result = await raw.diff(...args);
      if (!result.ok) throw new Error(result.error.message);
      return result.value;
    },
    async undoable() {
      const result = await raw.undoable();
      if (!result.ok) throw new Error(result.error.message);
      return result.value;
    },
    async prune(...args: Parameters<typeof raw.prune>) {
      const result = await raw.prune(...args);
      if (!result.ok) throw new Error(result.error.message);
      return result.value;
    },
  };

  const put = async (path: string, text: string | Uint8Array, mode?: number) => {
    const full = `${project}/${path}`;
    await box.fs.mkdir(full.slice(0, full.lastIndexOf("/")), { recursive: true });
    await box.fs.writeFile(full, typeof text === "string" ? encode(text) : text);
    if (mode !== undefined) await box.fs.chmod(full, mode);
  };
  const text = async (path: string) => decode(await box.fs.readFile(`${project}/${path}`));
  const exists = (path: string) =>
    box.fs.lstat(`${project}/${path}`).then(
      () => true,
      () => false,
    );
  const manifest = async (turnId: string, kind = "turns") =>
    JSON.parse(decode(await box.fs.readFile(`${project}/.caztor/snapshots/${kind}/${turnId}.json`))) as Record<string, unknown>;
  return { ...box, project, store, snapshots, raw, clock, userWrites, put, text, exists, manifest };
}

/** Every file below the project (internal state excluded) as `path -> hash:mode`, for whole-tree comparisons. */
export async function treeOf(t: { fs: FileSystem; project: string }): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  async function visit(dir: string, prefix: string): Promise<void> {
    for (const entry of await t.fs.readdir(dir)) {
      if (prefix === "" && entry.name === ".caztor") continue;
      const full = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        await visit(full, `${prefix}${entry.name}/`);
      } else if (entry.isFile()) {
        const stats = await t.fs.stat(full);
        out[`${prefix}${entry.name}`] = `${await hashBytes(await t.fs.readFile(full))}:${stats.mode.toString(8)}`;
      }
    }
  }
  await visit(t.project, "");
  return out;
}
