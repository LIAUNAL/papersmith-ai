import { hashBytes, parseRelPath, RESERVED_ROOTS, secretFoldersBelow } from "@caztor/core";
import type { ContentHash, FileChange, FileEntry, RelPath, Result, StoreError } from "@caztor/core";
import { basename, codeOf, createLocator, dirname, failure, fromFsError, joinPath } from "./containment.ts";
import type { Clock, DirectoryWatcher, FileSystem } from "./infra.ts";
import { createKeyedLock } from "./keyed-lock.ts";
import { createProjectWatch } from "./project-watch.ts";
import type { UserWriteRecorder } from "./user-writes.ts";

/** Largest file the editor opens. Bigger files are listed but refused by `readText`. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;

/** Largest payload accepted by `write` (uploads are limited to 20 MB). */
export const MAX_FILE_BYTES = 20 * 1024 * 1024;

/** Prefix of the temporary files used for atomic writes; they are never listed. */
export const TEMP_PREFIX = ".caztor-tmp-";
/**
 * Folders that tools fill with thousands of files nobody edits in a LaTeX project: environments, dependencies, git data
 * and caches. Listing never walks into them, at any depth, so the tree and every compile stay fast in a project that
 * holds code (a PaperSmith workspace with its Python environments). They can still be read by path.
 */
export const UNLISTED_FOLDERS: ReadonlySet<string> = new Set([".micromamba", ".venv", ".conda", "__pycache__", "node_modules", ".git", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache"]);

/** Permission bits of a temporary file while it holds content, before the original's bits are applied. */
const TEMP_MODE = 0o600;

export interface ProjectStoreOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  /** Whether the top-level `AGENTS.md` was created by Caztor; only then is it hidden from the tree. */
  agentsMdCreatedByCaztor?: boolean | (() => boolean | Promise<boolean>);
  /** Needed by `watch`: reports file system changes below the project folder. */
  watcher?: DirectoryWatcher;
  /** Needed by `watch`: times the merging of events and the periodic rescan. */
  clock?: Clock;
  /** Told about every change made through this store while a turn runs, so a file only the user changed can be told apart. */
  userWrites?: UserWriteRecorder;
}

/** The file operations of the local project store. */
export interface ProjectStore {
  list(): Promise<FileEntry[]>;
  read(path: RelPath): Promise<Result<{ bytes: Uint8Array; hash: ContentHash }, StoreError>>;
  /** Like `read`, but only for UTF-8 text up to 2 MB: `too_large` and `not_text` otherwise. */
  readText(path: RelPath): Promise<Result<{ bytes: Uint8Array; hash: ContentHash }, StoreError>>;
  /**
   * expect: a hash = must match; null = must not exist; "any" = unconditional. Replaces the file atomically.
   * `mode` sets the permission bits of the written file; without it a replaced file keeps its bits.
   */
  write(
    path: RelPath,
    bytes: Uint8Array,
    expect: ContentHash | null | "any",
    opts?: { mode?: number },
  ): Promise<Result<{ hash: ContentHash }, StoreError>>;
  /** Creates one folder; the parent must exist. */
  mkdir(path: RelPath): Promise<Result<void, StoreError>>;
  /** Files and folders. Never replaces an existing entry. */
  rename(from: RelPath, to: RelPath): Promise<Result<void, StoreError>>;
  /**
   * A folder with content needs `recursive: true`. A link is removed itself, never its target. With `expect`, a file
   * is removed only when its content hash matches (a conflict otherwise, with the current hash).
   */
  remove(path: RelPath, opts?: { recursive?: boolean; expect?: ContentHash }): Promise<Result<void, StoreError>>;
  /**
   * Reports changes made to the project by anyone (the user's editor, an agent, this store). Each change names a
   * file with its new content hash, or a null hash when it is gone. Needs the `watcher` and `clock` options.
   * Events from the operating system are hints that are confirmed against the files, and a periodic rescan backs
   * them up. Hidden and reserved paths and temporary files are never reported. Returns the function that stops it.
   */
  watch(onChange: (change: FileChange) => void): () => void;
  /** Looks at every file now and reports what changed since it was last seen. Does nothing while nobody watches. */
  rescan(): Promise<void>;
}

const reservedRoots: readonly string[] = RESERVED_ROOTS;

/**
 * Project files on disk, confined to one root. Every path is validated, then resolved with `realpath`
 * (links included); a location whose real path leaves the root or enters a reserved folder is refused.
 */
export function createProjectStore(options: ProjectStoreOptions): ProjectStore {
  const { fs, root } = options;
  const recorder = options.userWrites;
  const withLocks = createKeyedLock();

  async function hidesAgentsMd(): Promise<boolean> {
    const flag = options.agentsMdCreatedByCaztor;
    return typeof flag === "function" ? flag() : (flag ?? false);
  }

  const locateInside = createLocator({ fs, root, hiddenSegmentPrefix: TEMP_PREFIX });

  /** Like the reserved folders, the AGENTS.md that Caztor created is out of reach of the file operations. */
  async function locate(input: string, followFinal = true): Promise<Result<string, StoreError>> {
    if (input === "AGENTS.md" && (await hidesAgentsMd())) return failure("hidden", input);
    return locateInside(input, followFinal);
  }

  async function readRegular(path: RelPath, textOnly: boolean) {
    const located = await locate(path);
    if (!located.ok) return located;
    try {
      const stats = await fs.stat(located.value);
      if (!stats.isFile()) return failure("invalid_path", path);
      if (stats.size > (textOnly ? MAX_TEXT_BYTES : MAX_FILE_BYTES)) return failure("too_large", path);
      const bytes = await fs.readFile(located.value);
      if (textOnly && !isUtf8Text(bytes)) return failure("not_text", path);
      return { ok: true as const, value: { bytes, hash: await hashBytes(bytes) } };
    } catch (error) {
      return fromFsError(error, path);
    }
  }

  async function exists(path: string): Promise<boolean> {
    try {
      await fs.lstat(path);
      return true;
    } catch (error) {
      if (codeOf(error) === "ENOENT") return false;
      throw error;
    }
  }

  /** Moving or deleting a folder would take along any hidden secrets it holds, which the user cannot see. */
  async function holdsSecrets(path: string, real: string): Promise<boolean> {
    for (const below of secretFoldersBelow(path)) {
      if (await fs.lstat(`${real}/${below}`).then(() => true, () => false)) return true;
    }
    return false;
  }

  async function walk(dir: string, prefix: string, hideAgents: boolean, out: FileEntry[]): Promise<void> {
    const entries = (await fs.readdir(dir)).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const entry of entries) {
      const path = prefix + entry.name;
      if (entry.name.startsWith(TEMP_PREFIX)) continue;
      if (prefix === "") {
        if (reservedRoots.includes(entry.name.toLowerCase())) continue;
        if (hideAgents && entry.name === "AGENTS.md") continue;
      }
      if (entry.isSymbolicLink() || !parseRelPath(path).ok) continue;
      if (entry.isDirectory() && UNLISTED_FOLDERS.has(entry.name)) continue;
      const full = joinPath(dir, entry.name);
      // A name that is not valid UTF-8 comes back with replacement characters and cannot be opened: leave it out.
      if (entry.name.includes("\uFFFD") && !(await exists(full))) continue;
      if (entry.isDirectory()) {
        out.push({ path: path as RelPath, kind: "dir", size: 0 });
        await walk(full, `${path}/`, hideAgents, out);
      } else if (entry.isFile()) {
        out.push({ path: path as RelPath, kind: "file", size: (await fs.lstat(full)).size });
      }
    }
  }

  /** Check and replace for one file; callers hold the lock of `target`. */
  async function replaceFile(
    path: RelPath,
    target: string,
    bytes: Uint8Array,
    expect: ContentHash | null | "any",
    requestedMode?: number,
  ): Promise<Result<{ hash: ContentHash }, StoreError>> {
    let current: ContentHash | null = null;
    let before: ContentHash | null = null;
    let mode: number | null = null;
    try {
      const stats = await fs.stat(target).catch((error: unknown) => {
        if (codeOf(error) === "ENOENT") return null;
        throw error;
      });
      if (stats !== null && !stats.isFile()) return failure("invalid_path", path);
      mode = stats?.mode ?? null;
      if (stats !== null && expect !== null && expect !== "any") {
        if (stats.size > MAX_FILE_BYTES) return failure("too_large", path);
        current = await hashBytes(await fs.readFile(target));
        before = current;
      } else if (stats !== null && recorder?.recording() === true && stats.size <= MAX_FILE_BYTES) {
        before = await hashBytes(await fs.readFile(target));
      }
      if (expect === null && stats !== null) return failure("exists", path);
    } catch (error) {
      return fromFsError(error, path);
    }
    if (typeof expect === "string" && expect !== "any" && expect !== current) {
      return { ok: false, error: { code: "conflict", path, currentHash: current } };
    }

    const parentDir = dirname(target);
    const temp = joinPath(parentDir, `${TEMP_PREFIX}${crypto.randomUUID()}`);
    // Hashed before the rename, so nothing separates the change on disk from its record but the rename itself, and
    // announced before it so ending a recording waits for it.
    const hash = await hashBytes(bytes);
    const settled = recorder?.inflight() ?? (() => {});
    try {
      // Created owner-only when a file is replaced: the content is never readable by others while the original was not.
      const finalMode = requestedMode ?? mode;
      await fs.writeFile(temp, bytes, finalMode === null ? { exclusive: true } : { exclusive: true, mode: TEMP_MODE });
      // The parent may have been swapped for a link since `locate`; this narrows that window to the gap before the rename.
      if ((await fs.realpath(parentDir)) !== parentDir) {
        await fs.rm(temp, { force: true });
        return failure("outside_root", path);
      }
      // A file created by another process since the check above must not be replaced when the caller asked for a create.
      if (expect === null && (await exists(target))) {
        await fs.rm(temp, { force: true });
        return failure("exists", path);
      }
      // The replacement must not change who may read, write or run the file.
      if (finalMode !== null) await fs.chmod(temp, finalMode);
      await fs.rename(temp, target);
      recorder?.record(path, before, hash);
    } catch (error) {
      await fs.rm(temp, { force: true }).catch(() => {});
      return fromFsError(error, path);
    } finally {
      settled();
    }
    return { ok: true, value: { hash } };
  }

  /** Content hashes of the file at `real`, or of every file below it; links and temporary files are skipped. */
  async function hashesUnder(real: string, path: string): Promise<Map<RelPath, ContentHash>> {
    const found = new Map<RelPath, ContentHash>();
    const stats = await fs.lstat(real);
    if (stats.isFile()) {
      if (stats.size <= MAX_FILE_BYTES) found.set(path as RelPath, await hashBytes(await fs.readFile(real)));
      return found;
    }
    if (!stats.isDirectory()) return found;
    for (const entry of await fs.readdir(real)) {
      if (entry.name.startsWith(TEMP_PREFIX) || entry.isSymbolicLink()) continue;
      if (entry.name.includes("\uFFFD") && !(await exists(joinPath(real, entry.name)))) continue;
      for (const [file, hash] of await hashesUnder(joinPath(real, entry.name), `${path}/${entry.name}`)) found.set(file, hash);
    }
    return found;
  }

  const projectWatch =
    options.watcher === undefined || options.clock === undefined
      ? null
      : createProjectWatch({
          watcher: options.watcher,
          clock: options.clock,
          host: {
            root: () => fs.realpath(root),
            async rootId() {
              return (await fs.stat(await fs.realpath(root))).id;
            },
            list: () => store.list(),
            async signature(path) {
              const located = await locate(path, false);
              if (!located.ok) return null;
              if (path === "AGENTS.md" && (await hidesAgentsMd())) return null;
              try {
                const stats = await fs.lstat(located.value);
                if (stats.isSymbolicLink()) return null;
                if (stats.isDirectory()) return "dir";
                return stats.isFile() ? `${stats.size}:${stats.mtimeMs}` : null;
              } catch {
                return null;
              }
            },
            async hash(path) {
              const read = await readRegular(path as RelPath, false);
              return read.ok ? read.value.hash : null;
            },
          },
        });

  const store: ProjectStore = {
    async list() {
      const out: FileEntry[] = [];
      await walk(await fs.realpath(root), "", await hidesAgentsMd(), out);
      return out;
    },
    read: (path) => readRegular(path, false),
    readText: (path) => readRegular(path, true),

    async write(path, bytes, expect, opts) {
      if (bytes.length > MAX_FILE_BYTES) return failure("too_large", path);
      const located = await locate(path);
      if (!located.ok) return located;
      const target = located.value;
      return withLocks([target], () => replaceFile(path, target, bytes, expect, opts?.mode));
    },

    async mkdir(path) {
      const located = await locate(path);
      if (!located.ok) return located;
      try {
        await fs.mkdir(located.value);
        return { ok: true, value: undefined };
      } catch (error) {
        return fromFsError(error, path);
      }
    },

    async rename(from, to) {
      const source = await locate(from, false);
      if (!source.ok) return source;
      if (await holdsSecrets(from, source.value)) return failure("hidden", from);
      const destination = await locate(to, false);
      if (!destination.ok) return destination;
      if (to.startsWith(`${from}/`)) return failure("invalid_path", to);
      return withLocks([source.value, destination.value], async () => {
        try {
          await fs.lstat(source.value);
          if (await exists(destination.value)) return failure("exists", to);
          const moved = recorder?.recording() === true ? await hashesUnder(source.value, from) : null;
          const settled = moved === null ? () => {} : (recorder?.inflight() ?? (() => {}));
          try {
            await fs.rename(source.value, destination.value);
            if (moved !== null) {
              for (const [path, hash] of moved) {
                recorder?.record(path, hash, null);
                recorder?.record((to + path.slice(from.length)) as RelPath, null, hash);
              }
            }
          } finally {
            settled();
          }
          return { ok: true as const, value: undefined };
        } catch (error) {
          return fromFsError(error, from);
        }
      });
    },

    async remove(path, opts) {
      const located = await locate(path, false);
      if (!located.ok) return located;
      if (await holdsSecrets(path, located.value)) return failure("hidden", path);
      const target = located.value;
      return withLocks([target], async () => {
        try {
          const stats = await fs.lstat(target);
          const recursive = opts?.recursive ?? false;
          if (stats.isDirectory() && !recursive && (await fs.readdir(target)).length > 0) {
            return failure("invalid_path", path);
          }
          if (opts?.expect !== undefined) {
            const current = stats.isFile() ? await hashBytes(await fs.readFile(target)) : null;
            if (current !== opts.expect) return { ok: false as const, error: { code: "conflict" as const, path, currentHash: current } };
          }
          const removed = recorder?.recording() === true ? await hashesUnder(target, path) : null;
          const settled = removed === null ? () => {} : (recorder?.inflight() ?? (() => {}));
          try {
            await fs.rm(target, { recursive: stats.isDirectory() });
            if (removed !== null) for (const [file, hash] of removed) recorder?.record(file, hash, null);
          } finally {
            settled();
          }
          return { ok: true as const, value: undefined };
        } catch (error) {
          if (opts?.expect !== undefined && codeOf(error) === "ENOENT") {
            return { ok: false as const, error: { code: "conflict" as const, path, currentHash: null } };
          }
          return fromFsError(error, path);
        }
      });
    },

    watch(onChange) {
      if (projectWatch === null) throw new Error("Watching the project needs a watcher and a clock in the store options.");
      return projectWatch.watch(onChange);
    },

    async rescan() {
      await projectWatch?.rescan();
    },
  };
  return store;
}

function isUtf8Text(bytes: Uint8Array): boolean {
  if (bytes.includes(0)) return false;
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return true;
  } catch {
    return false;
  }
}
