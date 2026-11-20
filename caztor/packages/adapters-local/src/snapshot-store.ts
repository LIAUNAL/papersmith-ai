import { hashBytes, isSecretPath, parseSnapshotPath } from "@caztor/core";
import type { ChangedFile, ContentHash, RelPath, RestoreResult, Result, SnapshotPort, UserWrite } from "@caztor/core";
import { codeOf, joinPath } from "./containment.ts";
import type { Clock, FileSystem, FsStats } from "./infra.ts";
import { createKeyedLock } from "./keyed-lock.ts";
import { MAX_FILE_BYTES, TEMP_PREFIX, UNLISTED_FOLDERS } from "./project-store.ts";
import type { ProjectStore } from "./project-store.ts";
import { blobName, isTurnId, parseManifest, serializeManifest } from "./snapshot-manifest.ts";
import type { Manifest, ManifestFile, StoredChange } from "./snapshot-manifest.ts";

export interface SnapshotLimits {
  /** A larger file is tracked by size and modification time only, with no copy, so it cannot be undone. */
  maxFileBytes: number;
  /** Once this much new content was copied, further new content is not protected. */
  maxNewBytes: number;
  /** Once this many files were copied, further files are not protected. */
  maxFiles: number;
}

export const DEFAULT_SNAPSHOT_LIMITS: SnapshotLimits = {
  maxFileBytes: 5 * 1024 * 1024,
  maxNewBytes: 200 * 1024 * 1024,
  maxFiles: 5000,
};

/** Newest safety snapshots kept; an older one is deleted together with the copies only it used. */
export const SAFETY_SNAPSHOTS_KEPT = 5;

/** A timestamp this close to the snapshot time may not have moved when the file changed again, so it is not trusted. */
const RACY_WINDOW_MS = 2000;

/** Folders left out wherever they appear. */
const EXCLUDED_ANYWHERE = [".git", "node_modules"];
/** Folders left out at the top of the project: internal state and the provisioned agent folders. */
const EXCLUDED_AT_ROOT = [".caztor", ".claude", ".opencode", ".agents", ".papersmith", ".pi"];

/** A restored file never gets setuid, setgid or sticky from a manifest, whatever it says. */
const PERMISSION_BITS = 0o777;

const STORAGE_PARTS = [".caztor", "snapshots"] as const;

export interface SnapshotStoreOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  /** Every restore goes through the store, so it shares the store's containment rules and per-path locks. */
  store: ProjectStore;
  clock: Clock;
  limits?: Partial<SnapshotLimits>;
  /** True while the top-level AGENTS.md is the one Caztor created: it is hidden from the file API and left out here too. */
  skipAgentsMd?: () => boolean | Promise<boolean>;
}

/** Serializes snapshot operations of one project, also across several store instances in this process. */
const projectLock = createKeyedLock();

class SnapshotError extends Error {}

const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));

interface Walked {
  files: Array<{ path: RelPath; full: string }>;
  dirs: RelPath[];
  /** Names the disk lists but cannot open (not valid UTF-8): they are skipped everywhere and reported as not protected. */
  unreadable: RelPath[];
}

const signatureOf = (stats: FsStats): string => `${stats.size}:${stats.mtimeMs}:${stats.ctimeMs}:${stats.mode}`;

const byPath = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/**
 * Size and modification time can be set back (`touch -r`, `cp -p`), so a recorded hash is reused only when the change
 * time and the object identity agree too, and none of the times is close to the moment the snapshot was taken.
 */
function unchangedSince(before: ManifestFile, stats: FsStats): boolean {
  return (
    before.ctimeMs !== null &&
    before.id !== null &&
    before.size === stats.size &&
    before.mtimeMs === stats.mtimeMs &&
    before.ctimeMs === stats.ctimeMs &&
    before.id === stats.id
  );
}

const settledBefore = (stats: FsStats, createdAt: number): boolean => Math.max(stats.mtimeMs, stats.ctimeMs) < createdAt - RACY_WINDOW_MS;

/**
 * Turn snapshots without git: content-addressed copies under `.caztor/snapshots`. A capture before the turn, a diff
 * after it, and (once restore exists) an undo that works as a last-in-first-out stack over the retained turns.
 */
export function createSnapshotStore(options: SnapshotStoreOptions): Pick<SnapshotPort, "capture" | "diff" | "undoable" | "prune" | "restore" | "notCovered"> {
  const { fs, clock } = options;
  const limits = { ...DEFAULT_SNAPSHOT_LIMITS, ...options.limits };
  const lockKey = `snapshots:${options.root}`;
  const exclusive = <T>(work: () => Promise<T>): Promise<T> => projectLock([lockKey], work);

  async function rootReal(): Promise<string> {
    return fs.realpath(options.root);
  }

  /** Creates the folder when missing; refuses a link or anything that is not a folder, so nothing lands outside the project. */
  async function ensureFolder(path: string): Promise<void> {
    try {
      const stats = await fs.lstat(path);
      if (stats.isSymbolicLink() || !stats.isDirectory()) throw new SnapshotError(`The snapshot folder ${path} is not a plain folder`);
    } catch (error) {
      if (error instanceof SnapshotError) throw error;
      if (codeOf(error) !== "ENOENT") throw error;
      await fs.mkdir(path);
    }
  }

  async function storage(): Promise<{ blobs: string; turns: string; safety: string }> {
    let current = await rootReal();
    for (const part of STORAGE_PARTS) {
      current = joinPath(current, part);
      await ensureFolder(current);
    }
    const [blobs, turns, safety] = ["blobs", "turns", "safety"].map((name) => joinPath(current, name)) as [string, string, string];
    for (const folder of [blobs, turns, safety]) await ensureFolder(folder);
    return { blobs, turns, safety };
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

  /** Writes through a temporary name so a reader never sees half a file. */
  async function writeAtomic(path: string, bytes: Uint8Array): Promise<void> {
    const temp = `${path}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temp, bytes, { exclusive: true, mode: 0o600 });
      await fs.rename(temp, path);
    } catch (error) {
      await fs.rm(temp, { force: true }).catch(() => {});
      throw error;
    }
  }

  async function readManifests(folder: string): Promise<Manifest[]> {
    const found: Manifest[] = [];
    for (const entry of await fs.readdir(folder)) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
      const id = entry.name.slice(0, -".json".length);
      if (!isTurnId(id)) continue;
      const manifest = parseManifest(new TextDecoder().decode(await fs.readFile(joinPath(folder, entry.name))), id);
      if (manifest !== null) found.push(manifest);
    }
    return found;
  }

  async function walk(): Promise<Walked> {
    const base = await rootReal();
    const out: Walked = { files: [], dirs: [], unreadable: [] };
    const skipAgents = (await options.skipAgentsMd?.()) === true;
    async function visit(dir: string, prefix: string): Promise<void> {
      const entries = (await fs.readdir(dir)).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
      for (const entry of entries) {
        const lower = entry.name.toLowerCase();
        if (EXCLUDED_ANYWHERE.includes(lower) || (prefix === "" && EXCLUDED_AT_ROOT.includes(lower))) continue;
        // Environments and caches are not the user's work: walking them made every turn slow and its event huge.
        if (entry.isDirectory() && UNLISTED_FOLDERS.has(entry.name)) continue;
        if (entry.name.startsWith(TEMP_PREFIX) || entry.isSymbolicLink()) continue;
        if (skipAgents && prefix === "" && entry.name === "AGENTS.md") continue;
        const path = prefix + entry.name;
        const full = joinPath(dir, entry.name);
        if (entry.name.includes("\uFFFD") && !(await exists(full))) {
          out.unreadable.push(path as RelPath);
          continue;
        }
        if (!parseSnapshotPath(path).ok || isSecretPath(path)) continue;
        if (entry.isDirectory()) {
          out.dirs.push(path as RelPath);
          await visit(full, `${path}/`);
        } else if (entry.isFile()) {
          out.files.push({ path: path as RelPath, full });
        }
      }
    }
    await visit(base, "");
    return out;
  }

  /** Copies the project into a manifest. Throws a `SnapshotError` or the file system's error when anything fails. */
  async function buildManifest(kind: Manifest["kind"], turnId: string, seq: number, blobs: string, previous: Manifest | null): Promise<{ manifest: Manifest; unprotected: RelPath[] }> {
    const now = clock.now();
    const walked = await walk();
    const files = new Map<RelPath, ManifestFile>();
    const unprotected: RelPath[] = [...walked.unreadable];
    let protectedFiles = 0;
    let newBytes = 0;

    for (const { path, full } of walked.files) {
      const stats = await fs.lstat(full);
      const base = { size: stats.size, mtimeMs: stats.mtimeMs, ctimeMs: stats.ctimeMs, id: stats.id, mode: stats.mode };
      const skip = () => {
        files.set(path, { ...base, hash: null, undoable: false });
        unprotected.push(path);
      };
      if (protectedFiles >= limits.maxFiles || stats.size > limits.maxFileBytes) {
        skip();
        continue;
      }

      let hash: ContentHash | null = null;
      let bytes: Uint8Array | null = null;
      const before = previous?.files.get(path);
      const trusted = before !== undefined && before.hash !== null && unchangedSince(before, stats) && settledBefore(stats, previous!.createdAt);
      if (trusted && before.hash !== null && (await exists(joinPath(blobs, blobName(before.hash))))) {
        hash = before.hash;
      } else {
        try {
          bytes = await fs.readFile(full);
        } catch (error) {
          throw new SnapshotError(`Could not read ${path}: ${errorText(error)}`);
        }
        hash = await hashBytes(bytes);
      }

      const blobPath = joinPath(blobs, blobName(hash));
      if (!(await exists(blobPath))) {
        const content = bytes ?? (await fs.readFile(full));
        if (newBytes + content.length > limits.maxNewBytes) {
          skip();
          continue;
        }
        try {
          await writeAtomic(blobPath, content);
        } catch (error) {
          throw new SnapshotError(`Could not store a copy of ${path}: ${errorText(error)}`);
        }
        newBytes += content.length;
      }
      protectedFiles += 1;
      files.set(path, { ...base, size: bytes?.length ?? stats.size, hash, undoable: true });
    }

    const manifest: Manifest = {
      kind,
      turnId,
      seq,
      createdAt: now,
      state: "applied",
      files,
      dirs: walked.dirs,
      dirsAfter: null,
      partial: unprotected.length > 0,
      changes: null,
    };
    return { manifest, unprotected };
  }

  async function latestTurn(turns: string): Promise<{ previous: Manifest | null; nextSeq: number }> {
    const all = await readManifests(turns);
    const previous = all.reduce<Manifest | null>((best, candidate) => (best === null || candidate.seq > best.seq ? candidate : best), null);
    return { previous, nextSeq: (previous?.seq ?? 0) + 1 };
  }

  async function loadTurn(turns: string, turnId: string): Promise<Manifest | null> {
    if (!isTurnId(turnId)) return null;
    try {
      return parseManifest(new TextDecoder().decode(await fs.readFile(joinPath(turns, `${turnId}.json`))), turnId);
    } catch (error) {
      if (codeOf(error) === "ENOENT") return null;
      throw error;
    }
  }

  const saveManifest = (folder: string, manifest: Manifest) =>
    writeAtomic(joinPath(folder, `${manifest.turnId}.json`), new TextEncoder().encode(serializeManifest(manifest)));

  /** What is on disk now compared with the snapshot, before any attribution to the user. */
  async function compareWithDisk(manifest: Manifest): Promise<{ changes: StoredChange[]; dirs: RelPath[] }> {
    const walked = await walk();
    const seen = new Set<RelPath>();
    const changes: StoredChange[] = [];

    for (const { path, full } of walked.files) {
      seen.add(path);
      const stats = await fs.lstat(full);
      const before = manifest.files.get(path);
      const sameSignature = before !== undefined && unchangedSince(before, stats) && before.mode === stats.mode;
      const trusted = sameSignature && settledBefore(stats, manifest.createdAt);
      if (trusted) continue;
      if (sameSignature && before.hash === null) continue;

      let hash: ContentHash | null = null;
      if (stats.size <= MAX_FILE_BYTES) {
        hash = await fs.readFile(full).then(hashBytes, () => null);
      }
      const after = { afterHash: hash, afterMode: stats.mode, afterSignature: signatureOf(stats) };
      if (before === undefined) {
        changes.push({ path, change: "created", beforeHash: null, beforeMode: null, ...after, undoable: true, mixed: false });
        continue;
      }
      const changed = before.hash !== null ? hash !== before.hash || stats.mode !== before.mode : !sameSignature;
      if (changed) {
        changes.push({ path, change: "modified", beforeHash: before.hash, beforeMode: before.mode, ...after, undoable: before.undoable, mixed: false });
      }
    }
    for (const [path, before] of manifest.files) {
      if (seen.has(path)) continue;
      changes.push({
        path,
        change: "deleted",
        beforeHash: before.hash,
        beforeMode: before.mode,
        afterHash: null,
        afterMode: null,
        afterSignature: null,
        undoable: before.undoable,
        mixed: false,
      });
    }
    return { changes: changes.sort((a, b) => byPath(a.path, b.path)), dirs: walked.dirs };
  }

  /** Drops what only the user changed and flags what both changed. */
  function attribute(changes: StoredChange[], userWrites: ReadonlyMap<RelPath, UserWrite>): StoredChange[] {
    const kept: StoredChange[] = [];
    for (const change of changes) {
      const write = userWrites.get(change.path);
      if (write === undefined) {
        kept.push(change);
      } else if (write.first !== change.beforeHash || write.last !== change.afterHash) {
        kept.push({ ...change, mixed: true });
      }
    }
    return kept;
  }

  /** Folders the turn removed (`missing`) and folders it added (`added`), once the diff has run. */
  function folderChanges(manifest: Manifest, after: readonly RelPath[]): { missing: RelPath[]; added: RelPath[] } {
    const before = new Set(manifest.dirs);
    const now = new Set(after);
    return { missing: manifest.dirs.filter((dir) => !now.has(dir)), added: after.filter((dir) => !before.has(dir)) };
  }

  const nothingChanged = (manifest: Manifest): boolean => {
    if (manifest.changes === null || manifest.changes.length > 0) return false;
    if (manifest.dirsAfter === null) return true;
    const { missing, added } = folderChanges(manifest, manifest.dirsAfter);
    return missing.length === 0 && added.length === 0;
  };

  const isOnStack = (manifest: Manifest) => manifest.state === "applied" && !nothingChanged(manifest);

  const topOfStack = (all: Manifest[]) =>
    all.filter(isOnStack).reduce<Manifest | null>((best, candidate) => (best === null || candidate.seq > best.seq ? candidate : best), null);

  /** True when `path` or a folder above it is a link: nothing may be written or removed through it. */
  async function throughLink(path: string): Promise<boolean> {
    let current = await rootReal();
    for (const part of path.split("/")) {
      current = joinPath(current, part);
      try {
        if ((await fs.lstat(current)).isSymbolicLink()) return true;
      } catch (error) {
        if (codeOf(error) === "ENOENT" || codeOf(error) === "ENOTDIR") return false;
        throw error;
      }
    }
    return false;
  }

  const failure = (error: unknown) => ({ ok: false as const, error: { message: `The project snapshots could not be used: ${errorText(error)}` } });

  function referencedBlobsOf(all: Manifest[]): Set<string> {
    const referenced = new Set<string>();
    for (const manifest of all) {
      for (const file of manifest.files.values()) if (file.hash !== null) referenced.add(blobName(file.hash));
    }
    return referenced;
  }

  /** Removes temporary files and every copy that no manifest names. */
  async function collectBlobs(blobs: string, manifests: Manifest[]): Promise<void> {
    const referenced = referencedBlobsOf(manifests);
    for (const entry of await fs.readdir(blobs)) {
      if (!entry.isFile()) continue;
      if (entry.name.endsWith(".tmp") || (/^[0-9a-f]{64}$/.test(entry.name) && !referenced.has(entry.name))) {
        await fs.rm(joinPath(blobs, entry.name), { force: true });
      }
    }
  }

  /** Keeps the newest safety snapshots; the copies only the others used go too. */
  async function trimSafety(blobs: string, turns: string, safety: string): Promise<void> {
    const newestFirst = (await readManifests(safety)).sort((a, b) => b.seq - a.seq);
    for (const old of newestFirst.slice(SAFETY_SNAPSHOTS_KEPT)) await fs.rm(joinPath(safety, `${old.turnId}.json`), { force: true });
    await collectBlobs(blobs, [...(await readManifests(turns)), ...newestFirst.slice(0, SAFETY_SNAPSHOTS_KEPT)]);
  }

  interface Conflict {
    path: RelPath;
    expected: ContentHash | null;
    actual: ContentHash | null;
  }

  /** What a project file is like now, read through the store so containment and links are handled there. */
  async function currentState(path: RelPath): Promise<{ hash: ContentHash | null; mode: number | null; signature: string | null }> {
    const read = await options.store.read(path);
    const full = joinPath(await rootReal(), path);
    const stats = await fs.stat(full).catch(() => null);
    if (read.ok) return { hash: read.value.hash, mode: stats?.mode ?? null, signature: stats === null ? null : signatureOf(stats) };
    if (read.error.code === "not_found") return { hash: null, mode: null, signature: null };
    return { hash: null, mode: null, signature: stats === null ? null : signatureOf(stats) };
  }

  /** The stored copy, or null when it is missing or its content no longer matches its name. */
  async function readCopy(blobs: string, hash: ContentHash): Promise<Uint8Array | null> {
    try {
      const bytes = await fs.readFile(joinPath(blobs, blobName(hash)));
      return (await hashBytes(bytes)) === hash ? bytes : null;
    } catch {
      return null;
    }
  }

  /** Creates the folders above `path` that are missing. False when one cannot be created inside the project. */
  async function ensureParents(path: RelPath): Promise<boolean> {
    const parts = path.split("/").slice(0, -1);
    for (let length = 1; length <= parts.length; length += 1) {
      const made = await options.store.mkdir(parts.slice(0, length).join("/") as RelPath);
      if (!made.ok && made.error.code !== "exists") return false;
    }
    return true;
  }

  async function putBack(change: StoredChange, blobs: string, force: boolean): Promise<boolean> {
    if (change.beforeHash === null) return false;
    const bytes = await readCopy(blobs, change.beforeHash);
    if (bytes === null || (await throughLink(change.path)) || !(await ensureParents(change.path))) return false;
    const expect = force || (change.change === "modified" && change.afterHash === null) ? "any" : change.change === "deleted" ? null : change.afterHash;
    const written = await options.store.write(change.path, bytes, expect ?? "any", change.beforeMode === null ? undefined : { mode: change.beforeMode & PERMISSION_BITS });
    return written.ok;
  }

  async function removeCreated(change: StoredChange, force: boolean, existingDirs: ReadonlySet<RelPath>): Promise<boolean> {
    if (await throughLink(change.path)) return false;
    const removed =
      force || change.afterHash === null ? await options.store.remove(change.path) : await options.store.remove(change.path, { expect: change.afterHash });
    if (!removed.ok && !(force && removed.error.code === "not_found")) return false;
    // Folders the turn added go with their last file; folders that were there before stay.
    let dir = change.path.slice(0, Math.max(0, change.path.lastIndexOf("/")));
    while (dir !== "" && !existingDirs.has(dir as RelPath)) {
      if (!(await options.store.remove(dir as RelPath)).ok) break;
      dir = dir.slice(0, Math.max(0, dir.lastIndexOf("/")));
    }
    return true;
  }

  return {
    capture(turnId) {
      return exclusive(async (): Promise<Result<{ partial: boolean; unprotected: RelPath[] }, { message: string }>> => {
        try {
          if (!isTurnId(turnId)) throw new SnapshotError(`"${turnId}" is not a valid turn id`);
          const { blobs, turns } = await storage();
          const manifestPath = joinPath(turns, `${turnId}.json`);
          if (await exists(manifestPath)) throw new SnapshotError(`A snapshot for turn ${turnId} already exists`);
          const { previous, nextSeq } = await latestTurn(turns);
          const { manifest, unprotected } = await buildManifest("turn", turnId, nextSeq, blobs, previous);
          await writeAtomic(manifestPath, new TextEncoder().encode(serializeManifest(manifest)));
          return { ok: true, value: { partial: manifest.partial, unprotected } };
        } catch (error) {
          return { ok: false, error: { message: `The project snapshot could not be taken: ${errorText(error)}` } };
        }
      });
    },

    diff(turnId, userWrites) {
      return exclusive(async () => {
        try {
          const { turns } = await storage();
          const manifest = await loadTurn(turns, turnId);
          if (manifest === null) return { ok: true as const, value: [] };
          const found = await compareWithDisk(manifest);
          const changes = attribute(found.changes, userWrites);
          // The undo works from these records. If saving fails the list is still correct; a later undo recomputes it.
          await saveManifest(turns, { ...manifest, changes, dirsAfter: found.dirs }).catch(() => {});
          return {
            ok: true as const,
            value: changes.map(({ path, change, beforeHash, afterHash, undoable, mixed }): ChangedFile => ({ path, change, beforeHash, afterHash, undoable, mixed })),
          };
        } catch (error) {
          return failure(error);
        }
      });
    },

    notCovered() {
      return exclusive(async () => {
        try {
          return { ok: true as const, value: (await walk()).unreadable };
        } catch (error) {
          return failure(error);
        }
      });
    },

    undoable() {
      return exclusive(async () => {
        try {
          const { turns } = await storage();
          return { ok: true as const, value: topOfStack(await readManifests(turns))?.turnId ?? null };
        } catch (error) {
          return failure(error);
        }
      });
    },

    prune(keepTurns) {
      return exclusive(async () => {
        try {
          const { blobs, turns, safety } = await storage();
          const newestFirst = (await readManifests(turns)).sort((a, b) => b.seq - a.seq);
          const keep = Math.max(0, Math.floor(keepTurns));
          const discarded = newestFirst.slice(keep);
          for (const manifest of discarded) await fs.rm(joinPath(turns, `${manifest.turnId}.json`), { force: true });
          await collectBlobs(blobs, [...newestFirst.slice(0, keep), ...(await readManifests(safety))]);
          return { ok: true as const, value: discarded.reverse().map((manifest) => manifest.turnId) };
        } catch (error) {
          return failure(error);
        }
      });
    },

    restore(turnId, mode) {
      return exclusive(async (): Promise<RestoreResult> => {
        try {
          return await restoreTurn(turnId, mode);
        } catch (error) {
          return { status: "failed", message: failure(error).error.message };
        }
      });
    },
  };

  async function restoreTurn(turnId: string, mode: "strict" | "skip_conflicts" | "force"): Promise<RestoreResult> {
    const { blobs, turns, safety } = await storage();
    const manifest = await loadTurn(turns, turnId);
    if (manifest === null) return { status: "unavailable", reason: "discarded" };
    if (manifest.state === "undone") return { status: "unavailable", reason: "already_undone" };
    const found = manifest.changes === null ? await compareWithDisk(manifest) : null;
    const changes = manifest.changes ?? attribute(found!.changes, new Map());
    const dirsAfter = manifest.dirsAfter ?? found?.dirs ?? (await walk()).dirs;
    const folders = folderChanges(manifest, dirsAfter);
    if (changes.length === 0 && folders.missing.length === 0 && folders.added.length === 0) return { status: "restored", files: [], skipped: [] };
    if (topOfStack(await readManifests(turns))?.turnId !== turnId) return { status: "unavailable", reason: "not_latest" };

    // Preflight: nothing is written until every file has been looked at.
    const conflicts: Conflict[] = [];
    const plan: StoredChange[] = [];
    const skipped = new Set<RelPath>();
    for (const change of changes) {
      if (!change.undoable || (change.change !== "created" && change.beforeHash === null) || (await throughLink(change.path))) {
        skipped.add(change.path);
        continue;
      }
      const current = await currentState(change.path);
      const matches =
        change.afterHash !== null ? current.hash === change.afterHash && current.mode === change.afterMode : current.signature === change.afterSignature;
      if (matches && !change.mixed) {
        plan.push(change);
      } else if (mode === "force") {
        plan.push(change);
      } else {
        conflicts.push({ path: change.path, expected: change.afterHash, actual: current.hash });
        if (mode === "skip_conflicts") skipped.add(change.path);
      }
    }
    if (mode === "strict" && conflicts.length > 0) return { status: "conflict", conflicts };

    for (const change of plan) {
      if (change.change === "created" || change.beforeHash === null) continue;
      if ((await readCopy(blobs, change.beforeHash)) === null) {
        return { status: "failed", message: `The saved copy of ${change.path} is missing or damaged, so nothing was undone.` };
      }
    }
    if (plan.length > 0) {
      try {
        const seq = (await latestTurn(safety)).nextSeq;
        const { manifest: before } = await buildManifest("safety", turnId, seq, blobs, (await latestTurn(turns)).previous);
        await saveManifest(safety, before);
        await trimSafety(blobs, turns, safety);
      } catch (error) {
        return { status: "failed", message: `The safety snapshot could not be taken, so nothing was undone: ${errorText(error)}` };
      }
    }

    const known = new Set(manifest.dirs);
    const restored: RelPath[] = [];
    for (const change of plan) {
      const done = change.change === "created" ? await removeCreated(change, mode === "force", known) : await putBack(change, blobs, mode === "force");
      if (done) restored.push(change.path);
      else skipped.add(change.path);
    }
    // Folders: bring back the ones the turn removed, parents first; drop the empty ones it added, deepest first.
    for (const dir of [...folders.missing].sort(byPath)) {
      if (!(await throughLink(dir))) await options.store.mkdir(dir);
    }
    for (const dir of [...folders.added].sort(byPath).reverse()) {
      if (!(await throughLink(dir))) await options.store.remove(dir);
    }
    await saveManifest(turns, { ...manifest, state: "undone" });
    return { status: "restored", files: restored.sort(byPath), skipped: [...skipped].sort(byPath) };
  }
}
