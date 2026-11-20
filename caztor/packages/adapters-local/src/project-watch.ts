import type { ContentHash, FileChange, FileEntry, RelPath } from "@caztor/core";
import type { Clock, DirectoryWatcher } from "./infra.ts";

/** Pause that merges a burst of file system events into one look at the files. */
export const WATCH_DEBOUNCE_MS = 100;

/**
 * Period of the rescan that backs up a working event watcher. It is a backstop for events the platform dropped, so it
 * is long: on a large project one rescan costs well over a second.
 */
export const RESCAN_INTERVAL_MS = 30_000;

/** Period of the rescan while the event watcher is missing or has failed: then the rescan is the only source of changes. */
export const FALLBACK_RESCAN_INTERVAL_MS = 5000;

/** What the watcher needs to know about the project; the project store provides it with all its containment rules. */
export interface WatchHost {
  /** Real path of the project folder, the folder to watch. */
  root(): Promise<string>;
  /** Identifies the project folder itself, so that a folder removed and created again can be told from the old one. */
  rootId(): Promise<string>;
  /** The visible files and folders: no hidden or reserved entries, no links. */
  list(): Promise<FileEntry[]>;
  /**
   * Identifies the current version of the entry at a path given by the file system, or null when there is nothing
   * to report there: it is missing, hidden, reserved, outside the project, a link or a temporary file. A file is
   * identified by its size and modification time, a folder by `"dir"`.
   */
  signature(path: string): Promise<string | null>;
  /** The content hash of a visible file, or null when it cannot be read as one. */
  hash(path: string): Promise<ContentHash | null>;
}

export interface ProjectWatchOptions {
  host: WatchHost;
  watcher: DirectoryWatcher;
  clock: Clock;
  debounceMs?: number;
  /** Period of the backstop rescan while the event watcher works. */
  rescanMs?: number;
  /** Period of the rescan while the event watcher is not working. */
  fallbackRescanMs?: number;
}

export interface ProjectWatch {
  /**
   * Starts watching with the first listener and stops with the last. Each change names a path with the hash of its
   * new content, or a null hash when the file is gone (or the path is a folder).
   */
  watch(onChange: (change: FileChange) => void): () => void;
  /** Compares every visible file with what was last seen and reports the differences. Does nothing while nobody watches. */
  rescan(): Promise<void>;
}

/** Everything that belongs to one period of watching; a stopped run can never report again. */
interface Run {
  active: boolean;
  /** Version identity of every known file, and the folders known to exist. */
  files: Map<string, string>;
  dirs: Set<string>;
  pending: Set<string>;
  /** An event named no file, so the whole project must be looked at. */
  everything: boolean;
  cancelFlush: (() => void) | null;
  cancelRescan: (() => void) | null;
  closeWatcher: (() => void) | null;
  /** The event watcher is open and has not reported a failure. */
  healthy: boolean;
  /** Identity of the project folder the event watcher was opened on. */
  watchedRootId: string | null;
  queue: Promise<void>;
}

export function createProjectWatch(options: ProjectWatchOptions): ProjectWatch {
  const { host, watcher, clock } = options;
  const debounceMs = options.debounceMs ?? WATCH_DEBOUNCE_MS;
  const rescanMs = options.rescanMs ?? RESCAN_INTERVAL_MS;
  const fallbackRescanMs = options.fallbackRescanMs ?? FALLBACK_RESCAN_INTERVAL_MS;
  const listeners = new Set<(change: FileChange) => void>();
  let run: Run | null = null;

  function emit(current: Run, path: string, hash: ContentHash | null): void {
    if (!current.active) return;
    const change: FileChange = { path: path as RelPath, hash };
    for (const listener of [...listeners]) {
      try {
        listener(change);
      } catch {
        // One failing listener must not stop the others or the watch.
      }
    }
  }

  /** Tasks of one run never overlap, so the known state is only ever changed by one of them at a time. */
  function enqueue(current: Run, task: () => Promise<void>): Promise<void> {
    const next = current.queue.then(() => (current.active ? task() : undefined)).catch(() => {});
    current.queue = next;
    return next;
  }

  /** Looks at every visible entry. With `report` off it only learns what exists. */
  async function scan(current: Run, report: boolean): Promise<void> {
    const entries = await host.list();
    const seenFiles = new Set<string>();
    const seenDirs = new Set<string>();
    const changed: Array<[string, ContentHash | null]> = [];
    for (const entry of entries) {
      if (!current.active) return;
      if (entry.kind === "dir") {
        seenDirs.add(entry.path);
        if (report && !current.dirs.has(entry.path)) changed.push([entry.path, null]);
        continue;
      }
      const signature = await host.signature(entry.path);
      if (signature === null) continue;
      seenFiles.add(entry.path);
      if (current.files.get(entry.path) === signature) continue;
      current.files.set(entry.path, signature);
      if (!report) continue;
      const hash = await host.hash(entry.path);
      if (hash !== null) changed.push([entry.path, hash]);
    }
    if (!current.active) return;
    for (const path of [...current.files.keys()]) {
      if (seenFiles.has(path)) continue;
      current.files.delete(path);
      if (report) changed.push([path, null]);
    }
    for (const path of current.dirs) {
      if (!seenDirs.has(path) && report) changed.push([path, null]);
    }
    current.dirs = seenDirs;
    for (const [path, hash] of changed) emit(current, path, hash);
  }

  /** Looks at one path named by an event. Returns true when the whole project has to be scanned to find what changed. */
  async function refresh(current: Run, path: string): Promise<boolean> {
    const signature = await host.signature(path);
    if (!current.active) return false;
    if (signature === null) {
      // Gone, or never something to report. A folder that went away takes the files known below it along.
      const prefix = `${path}/`;
      for (const known of [...current.files.keys()]) {
        if (known !== path && !known.startsWith(prefix)) continue;
        current.files.delete(known);
        emit(current, known, null);
      }
      for (const known of [...current.dirs]) {
        if (known !== path && !known.startsWith(prefix)) continue;
        current.dirs.delete(known);
        emit(current, known, null);
      }
      return false;
    }
    if (signature === "dir") return !current.dirs.has(path);
    if (current.files.get(path) === signature) return false;
    const hash = await host.hash(path);
    current.files.set(path, signature);
    if (hash !== null) emit(current, path, hash);
    return false;
  }

  function flush(current: Run): void {
    current.cancelFlush = null;
    const paths = [...current.pending];
    current.pending.clear();
    let everything = current.everything;
    current.everything = false;
    void enqueue(current, async () => {
      for (const path of paths) everything = (await refresh(current, path)) || everything;
      if (everything) await scan(current, true);
    });
  }

  function onEvent(current: Run, path: string | null): void {
    if (!current.active) return;
    // An event without a file name could be anything: look at the whole project.
    if (path === null) current.everything = true;
    else current.pending.add(path);
    current.cancelFlush ??= clock.setTimeout(() => flush(current), debounceMs);
  }

  /** Opens the event watcher on the project folder as it is now. A folder that is missing or cannot be watched leaves it closed. */
  async function openWatcher(current: Run): Promise<void> {
    current.closeWatcher?.();
    current.closeWatcher = null;
    current.healthy = false;
    current.watchedRootId = null;
    // A failure reported while the watcher is still being opened must not be overwritten by the success below.
    let failedWhileOpening = false;
    try {
      const root = await host.root();
      const rootId = await host.rootId();
      if (!current.active) return;
      current.closeWatcher = watcher.watch(
        root,
        (path) => onEvent(current, path),
        // A watcher that fails while running leaves the rescan as the only source of changes until it is opened again.
        () => {
          failedWhileOpening = true;
          current.healthy = false;
          // The backstop may be waiting for its long period. Look again now, which also opens a watcher on the folder as it is, so
          // the next edit is seen at once instead of after the next rescan.
          if (current.cancelRescan === null) return;
          current.cancelRescan();
          current.cancelRescan = null;
          void enqueue(current, () => backstop(current))
            .catch(() => {})
            .then(() => armRescan(current));
        },
      );
      current.watchedRootId = rootId;
      current.healthy = !failedWhileOpening;
    } catch {
      // The folder is gone or recursive watching is not available here; the rescan covers it and tries again.
    }
  }

  /** True when the project folder is not the one the event watcher was opened on: it was removed and created again. */
  async function rootReplaced(current: Run): Promise<boolean> {
    if (!current.healthy) return false;
    try {
      return (await host.rootId()) !== current.watchedRootId;
    } catch {
      return true;
    }
  }

  /** One backstop pass: reopens a watcher that is not working or sits on a replaced folder, then compares every file. A vanished folder only closes the watcher. */
  async function backstop(current: Run): Promise<void> {
    if (!current.healthy || (await rootReplaced(current))) await openWatcher(current);
    try {
      await scan(current, true);
    } catch (error) {
      current.closeWatcher?.();
      current.closeWatcher = null;
      current.healthy = false;
      throw error;
    }
  }

  function armRescan(current: Run): void {
    if (!current.active) return;
    current.cancelRescan = clock.setTimeout(() => {
      current.cancelRescan = null;
      void enqueue(current, () => backstop(current)).then(() => armRescan(current));
    }, current.healthy ? rescanMs : fallbackRescanMs);
  }

  function start(): Run {
    const current: Run = {
      active: true,
      files: new Map(),
      dirs: new Set(),
      pending: new Set(),
      everything: false,
      cancelFlush: null,
      cancelRescan: null,
      closeWatcher: null,
      healthy: false,
      watchedRootId: null,
      queue: Promise.resolve(),
    };
    void enqueue(current, async () => {
      await openWatcher(current);
      if (!current.active) return;
      await scan(current, false);
      armRescan(current);
    });
    return current;
  }

  function stop(current: Run): void {
    current.active = false;
    current.cancelFlush?.();
    current.cancelRescan?.();
    current.closeWatcher?.();
    current.pending.clear();
    current.files.clear();
    current.dirs.clear();
  }

  return {
    watch(onChange) {
      listeners.add(onChange);
      run ??= start();
      return () => {
        if (!listeners.delete(onChange) || listeners.size > 0 || run === null) return;
        stop(run);
        run = null;
      };
    },
    async rescan() {
      const current = run;
      if (current === null) return;
      await enqueue(current, () => scan(current, true));
    },
  };
}
