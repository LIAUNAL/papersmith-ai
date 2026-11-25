import type { ContentHash, RelPath, UserWrite } from "@caztor/core";

/** What the project store reports to: it only pays for hashing while `recording()` is true. */
export interface UserWriteRecorder {
  recording(): boolean;
  /** One change made through the file API: the file's hash before it and after it (null = absent). */
  record(path: RelPath, before: ContentHash | null, after: ContentHash | null): void;
  /**
   * Announces a change that is about to reach the disk and returns the function to call once its `record` calls are
   * made (or it failed). Ending the recording waits for every announced change, so a save that is already on disk
   * is never dropped because its record had not run yet.
   */
  inflight(): () => void;
}

export interface UserWriteLog extends UserWriteRecorder {
  /** Starts recording for a turn, discarding anything left from before. */
  begin(): void;
  /** The writes so far, without stopping. */
  peek(): ReadonlyMap<RelPath, UserWrite>;
  /** Waits for the changes in flight, stops recording and returns the writes of the turn. */
  end(): Promise<ReadonlyMap<RelPath, UserWrite>>;
}

/**
 * Remembers which files the user changed through the file API during a turn. The agent writes straight to disk,
 * so everything that arrives here is a user change; the snapshot diff uses it to attribute each changed file.
 */
export function createUserWriteLog(): UserWriteLog {
  let writes: Map<RelPath, UserWrite> | null = null;
  let pending = 0;
  let waiting: Array<() => void> = [];
  return {
    recording: () => writes !== null,
    record(path, before, after) {
      if (writes === null) return;
      const known = writes.get(path);
      writes.set(path, { first: known === undefined ? before : known.first, last: after });
    },
    inflight() {
      if (writes === null) return () => {};
      pending += 1;
      let settled = false;
      return () => {
        if (settled) return;
        settled = true;
        pending -= 1;
        if (pending === 0) {
          const wake = waiting;
          waiting = [];
          for (const resolve of wake) resolve();
        }
      };
    },
    begin() {
      writes = new Map();
    },
    peek: () => new Map(writes ?? []),
    async end() {
      while (pending > 0) await new Promise<void>((resolve) => waiting.push(resolve));
      const done = writes ?? new Map<RelPath, UserWrite>();
      writes = null;
      return done;
    },
  };
}
