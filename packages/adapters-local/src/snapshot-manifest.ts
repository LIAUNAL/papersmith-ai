import { parseSnapshotPath } from "@caztor/core";
import type { ContentHash, RelPath } from "@caztor/core";

const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/;
const TURN_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_MODE = 0o7777;

export const isTurnId = (value: string): boolean => TURN_ID_PATTERN.test(value);
export const isContentHash = (value: unknown): value is ContentHash => typeof value === "string" && HASH_PATTERN.test(value);

/** The file name of a blob: the hex digest of its content. */
export const blobName = (hash: ContentHash): string => hash.slice("sha256:".length);

/** One file as it was when the snapshot was taken. `hash` is null when the content was not stored. */
export interface ManifestFile {
  hash: ContentHash | null;
  size: number;
  mtimeMs: number;
  /** Change time and object identity (device and inode). Null in a manifest written before they were recorded: never trusted. */
  ctimeMs: number | null;
  id: string | null;
  mode: number;
  /** True only when a blob holds the content, so the file can be restored. */
  undoable: boolean;
}

/** A file the turn changed, as found by the diff; the undo works from these records. */
export interface StoredChange {
  path: RelPath;
  change: "created" | "modified" | "deleted";
  beforeHash: ContentHash | null;
  afterHash: ContentHash | null;
  beforeMode: number | null;
  afterMode: number | null;
  /** Size, modification time and mode of the file after the turn; stands in for the hash of a file too large to hash. */
  afterSignature: string | null;
  undoable: boolean;
  mixed: boolean;
}

export interface Manifest {
  /** A `turn` is on the undo stack; a `safety` snapshot is the copy taken just before an undo writes. */
  kind: "turn" | "safety";
  turnId: string;
  /** Position on the undo stack: higher is more recent. */
  seq: number;
  createdAt: number;
  state: "applied" | "undone";
  files: Map<RelPath, ManifestFile>;
  /** Folders that existed, so an undo can recreate them and remove the ones a turn added. */
  dirs: RelPath[];
  /** The folders found by the diff at the end of the turn; null before that. */
  dirsAfter: RelPath[] | null;
  partial: boolean;
  /** Set by the diff at the end of the turn; null before that. */
  changes: StoredChange[] | null;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isCount = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const isTime = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;
const isMode = (value: unknown): value is number => isCount(value) && value <= MAX_MODE;
const isNullableHash = (value: unknown): value is ContentHash | null => value === null || isContentHash(value);
const isNullableMode = (value: unknown): value is number | null => value === null || isMode(value);

function parseFile(value: unknown): ManifestFile | null {
  if (!isRecord(value)) return null;
  const { hash, size, mtimeMs, mode, undoable } = value;
  const ctimeMs = value["ctimeMs"] ?? null;
  const id = value["id"] ?? null;
  if (!isNullableHash(hash) || !isCount(size) || !isTime(mtimeMs) || !isMode(mode) || typeof undoable !== "boolean") return null;
  if (ctimeMs !== null && !isTime(ctimeMs)) return null;
  if (id !== null && typeof id !== "string") return null;
  if (undoable && hash === null) return null;
  return { hash, size, mtimeMs, ctimeMs, id, mode, undoable };
}

function parseChange(value: unknown): StoredChange | null {
  if (!isRecord(value)) return null;
  const { path, change, beforeHash, afterHash, beforeMode, afterMode, afterSignature, undoable, mixed } = value;
  if (typeof path !== "string" || !parseSnapshotPath(path).ok) return null;
  if (change !== "created" && change !== "modified" && change !== "deleted") return null;
  if (!isNullableHash(beforeHash) || !isNullableHash(afterHash)) return null;
  if (!isNullableMode(beforeMode) || !isNullableMode(afterMode)) return null;
  if (afterSignature !== null && typeof afterSignature !== "string") return null;
  if (typeof undoable !== "boolean" || typeof mixed !== "boolean") return null;
  return { path: path as RelPath, change, beforeHash, afterHash, beforeMode, afterMode, afterSignature, undoable, mixed };
}

/** A list of valid, distinct folder paths, or null. */
function parseFolders(value: unknown): RelPath[] | null {
  if (!Array.isArray(value)) return null;
  const seen = new Set<string>();
  for (const dir of value) {
    if (typeof dir !== "string" || !parseSnapshotPath(dir).ok || seen.has(dir)) return null;
    seen.add(dir);
  }
  return value as RelPath[];
}

/**
 * Reads a manifest from disk. The file is untrusted: every path is validated with `parseSnapshotPath` (so `../`, absolute
 * paths and reserved folders are refused), and one invalid entry rejects the whole manifest rather than being
 * dropped, so a tampered file can never be partly applied. Returns null when anything is wrong.
 */
export function parseManifest(text: string, expectedId: string): Manifest | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(raw) || raw["version"] !== 1) return null;
  const { kind, turnId, seq, createdAt, state, files, dirs, partial, changes } = raw;
  const dirsAfter = raw["dirsAfter"] ?? null;
  if (kind !== "turn" && kind !== "safety") return null;
  if (turnId !== expectedId || !isTurnId(expectedId)) return null;
  if (!isCount(seq) || !isTime(createdAt) || (state !== "applied" && state !== "undone") || typeof partial !== "boolean") return null;
  if (!isRecord(files) || !Array.isArray(dirs)) return null;

  const parsedFiles = new Map<RelPath, ManifestFile>();
  for (const [path, entry] of Object.entries(files)) {
    const file = parseFile(entry);
    if (!parseSnapshotPath(path).ok || file === null) return null;
    parsedFiles.set(path as RelPath, file);
  }
  const parsedDirs = parseFolders(dirs);
  const parsedDirsAfter = dirsAfter === null ? null : parseFolders(dirsAfter);
  if (parsedDirs === null || (dirsAfter !== null && parsedDirsAfter === null)) return null;
  let parsedChanges: StoredChange[] | null = null;
  if (changes !== null) {
    if (!Array.isArray(changes)) return null;
    parsedChanges = [];
    for (const entry of changes) {
      const change = parseChange(entry);
      if (change === null || parsedChanges.some((other) => other.path === change.path)) return null;
      parsedChanges.push(change);
    }
  }
  return { kind, turnId: expectedId, seq, createdAt, state, files: parsedFiles, dirs: parsedDirs, dirsAfter: parsedDirsAfter, partial, changes: parsedChanges };
}

export function serializeManifest(manifest: Manifest): string {
  return `${JSON.stringify({
    version: 1,
    kind: manifest.kind,
    turnId: manifest.turnId,
    seq: manifest.seq,
    createdAt: manifest.createdAt,
    state: manifest.state,
    partial: manifest.partial,
    files: Object.fromEntries(manifest.files),
    dirs: manifest.dirs,
    dirsAfter: manifest.dirsAfter,
    changes: manifest.changes,
  })}\n`;
}
