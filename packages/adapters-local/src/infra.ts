// Infrastructure seams injected into every adapter. Adapters never import node:child_process or node:fs directly.

export interface SpawnSpec {
  file: string;
  args: readonly string[];
  cwd: string;
  /** The complete child environment. Nothing is inherited from the server process. */
  env: Readonly<Record<string, string>>;
  /** Written to the child's stdin, which is then closed. */
  stdin?: string;
  /** Keeps stdin open for `ChildHandle.write` (a sign-in that waits for a pasted code). */
  interactive?: boolean;
}

export interface ChildHandle {
  stdout: AsyncIterable<Uint8Array>;
  stderr: AsyncIterable<Uint8Array>;
  /** Rejects when the process could not be started (for example ENOENT). */
  exit: Promise<{ code: number | null; signal: string | null }>;
  /** Signals the whole process group of the child. Never throws when the group is already gone and does nothing once the child has exited. */
  killGroup(signal: "SIGINT" | "SIGTERM" | "SIGKILL"): void;
  /** Writes to the stdin of a child started with `interactive`; does nothing otherwise or once it has exited. */
  write?(text: string): void;
}

export interface ProcessSpawner {
  /**
   * Never throws for a process that cannot start: invalid arguments (such as a NUL byte) and a missing
   * binary both surface as a rejected `exit` with empty output streams.
   */
  spawn(spec: SpawnSpec): ChildHandle;
}

export interface Clock {
  now(): number;
  /** Returns a function that cancels the timer. */
  setTimeout(fn: () => void, ms: number): () => void;
}

/** Identity, or the bubblewrap wrapper. */
export type CommandWrapper = (spec: SpawnSpec) => SpawnSpec;

export interface FsStats {
  size: number;
  mtimeMs: number;
  /** Last change of the file or of its metadata. Unlike `mtimeMs` it cannot be set back by `touch -r` or `cp -p`. */
  ctimeMs: number;
  /** Permission bits only (for example `0o755`), without the file type. */
  mode: number;
  /** Owner of the object. */
  uid: number;
  /** Identifies the object itself (device and inode): a folder removed and created again gets a different one. */
  id: string;
  isFile(): boolean;
  isDirectory(): boolean;
  isSymbolicLink(): boolean;
}

export interface FsDirent {
  name: string;
  isFile(): boolean;
  isDirectory(): boolean;
  isSymbolicLink(): boolean;
}

/**
 * The narrow subset of `node:fs/promises` used by the store, state, snapshot and provisioner adapters.
 * Failures carry a Node-style `code` property (`ENOENT`, `EEXIST`, `ENOTDIR`, ...).
 */
export interface FileSystem {
  readFile(path: string): Promise<Uint8Array>;
  /** At most `length` bytes starting at byte `start`; shorter when the file ends first. */
  readRange(path: string, start: number, length: number): Promise<Uint8Array>;
  /**
   * `exclusive` fails with EEXIST when the file already exists. `mode` gives the permission bits of a file that
   * is created by this call (the process umask may clear some); an existing file keeps its bits.
   */
  writeFile(path: string, data: Uint8Array, opts?: { exclusive?: boolean; mode?: number }): Promise<void>;
  /** `mode` gives the permission bits of the folder this call creates (the process umask may clear some). */
  mkdir(path: string, opts?: { recursive?: boolean; mode?: number }): Promise<void>;
  readdir(path: string): Promise<FsDirent[]>;
  stat(path: string): Promise<FsStats>;
  /** Like `stat` but does not follow a final symbolic link. */
  lstat(path: string): Promise<FsStats>;
  realpath(path: string): Promise<string>;
  rename(from: string, to: string): Promise<void>;
  rm(path: string, opts?: { recursive?: boolean; force?: boolean }): Promise<void>;
  copyFile(from: string, to: string): Promise<void>;
  /** Sets the permission bits; follows a final symbolic link. */
  chmod(path: string, mode: number): Promise<void>;
  /** Creates a new folder whose name is `prefix` plus a random suffix, readable only by this user (mode 0700), and returns its path. */
  mkdtemp(prefix: string): Promise<string>;
}

/**
 * Reports changes below a folder, including nested ones. Reports are hints: a platform may merge, repeat or
 * drop them, so callers confirm what changed by looking at the files.
 */
export interface DirectoryWatcher {
  /**
   * `listener` receives a path relative to `dir`, or null when the platform did not name the file. Throws when the
   * folder cannot be watched (missing, or recursive watching is unsupported). Runtime failures go to `onError`.
   * Returns a function that stops watching; calling it again does nothing.
   */
  watch(dir: string, listener: (relativePath: string | null) => void, onError: (error: Error) => void): () => void;
}
