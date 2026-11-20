import { ApiError } from "../api/client.ts";
import type { ApiClient, FileContent, ServerEvent } from "../api/types.ts";

/** Idle time after the last edit before a buffer is saved. */
export const AUTOSAVE_MS = 800;

export type BufferStatus = "saved" | "saving" | "dirty" | "conflict" | "error";

/** The version of a file on disk that differs from what the user's text is based on. */
export interface ConflictView {
  /** The text and hash on disk, or null when the file was deleted (or could not be read yet). */
  readonly disk: { readonly text: string; readonly hash: string } | null;
  /** The file no longer exists on disk. */
  readonly deleted: boolean;
  /** The path of the copy made from the user's text, once there is one. */
  readonly copiedTo: string | null;
  /** A readable message when resolving failed. */
  readonly problem: string | null;
}

/** What the UI may read about an open file. It never changes after it was handed out. */
export interface BufferView {
  readonly path: string;
  /** The text the user sees, including edits that are not saved. */
  readonly text: string;
  readonly status: BufferStatus;
  /** The hash of the version on disk that `text` is based on; null when the file was deleted on disk. */
  readonly baseHash: string | null;
  /** A readable message while the status is `error`. */
  readonly error: string | null;
  /** Set while the status is `conflict`: the disk version the user must decide about. */
  readonly conflict: ConflictView | null;
}

/** A request to put the cursor on a line of a file, for example from a compile error. `id` changes with every request. */
export interface Jump {
  readonly path: string;
  /** 1-based. */
  readonly line: number;
  readonly id: number;
}

export interface SessionSnapshot {
  readonly buffers: ReadonlyMap<string, BufferView>;
  /** The file currently shown in the editor. */
  readonly active: string | null;
  /** The latest request to move the cursor, or null. The editor applies each request once. */
  readonly jump: Jump | null;
}

export interface EditorSessionOptions {
  api: Pick<ApiClient, "writeFile" | "readFile">;
  /** Idle time before autosave; tests keep the default. */
  autosaveMs?: number;
}

interface Buffer {
  path: string;
  text: string;
  /** The text last written to, or read from, disk. */
  savedText: string;
  baseHash: string | null;
  status: BufferStatus;
  error: string | null;
  conflict: ConflictView | null;
  cancelTimer: (() => void) | null;
  inFlight: Promise<void> | null;
  /** The disk check that is running, and whether another was asked for meanwhile. */
  checking: Promise<void> | null;
  recheck: boolean;
}

type DiskVersion = { text: string; hash: string } | "deleted";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `chapters/intro.tex` becomes `chapters/intro-copy.tex`, then `intro-copy-2.tex`, and so on. */
export function copyName(path: string, attempt: number): string {
  const slash = path.lastIndexOf("/") + 1;
  const dot = path.lastIndexOf(".");
  const hasExtension = dot > slash;
  const stem = hasExtension ? path.slice(0, dot) : path;
  const extension = hasExtension ? path.slice(dot) : "";
  return `${stem}-copy${attempt > 1 ? `-${attempt}` : ""}${extension}`;
}

/** How many names are tried for a copy before giving up. */
const COPY_ATTEMPTS = 50;

function messageOf(error: unknown): string {
  return error instanceof Error && error.message !== "" ? error.message : "The file could not be saved.";
}

/**
 * The documents the user has open: text, the disk version each one is based on, and the save state. It holds
 * no UI; a view reads `getSnapshot()` and calls `edit`. Every file keeps its own buffer, so switching files
 * never loses an edit, and each dirty buffer saves on its own after the idle period.
 */
export class EditorSession {
  private readonly api: Pick<ApiClient, "writeFile" | "readFile">;
  private readonly autosaveMs: number;
  private readonly buffers = new Map<string, Buffer>();
  private readonly listeners = new Set<() => void>();
  private readonly savedListeners = new Set<(path: string) => void>();
  private active: string | null = null;
  private snapshot: SessionSnapshot = { buffers: new Map(), active: null, jump: null };
  private jump: Jump | null = null;
  private disposed = false;

  constructor(options: EditorSessionOptions) {
    this.api = options.api;
    this.autosaveMs = options.autosaveMs ?? AUTOSAVE_MS;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };

  getSnapshot = (): SessionSnapshot => this.snapshot;

  /** Calls `listener` with the path of every file after the server accepted a save of it. */
  onSaved(listener: (path: string) => void): () => void {
    this.savedListeners.add(listener);
    return () => void this.savedListeners.delete(listener);
  }

  get(path: string): BufferView | undefined {
    return this.snapshot.buffers.get(path);
  }

  /** Opens a file read from the server. A buffer that already exists keeps its text, saved or not. */
  open(file: FileContent): void {
    const existing = this.buffers.get(file.path);
    if (existing === undefined) {
      this.buffers.set(file.path, {
        path: file.path,
        text: file.content,
        savedText: file.content,
        baseHash: file.hash,
        status: "saved",
        error: null,
        conflict: null,
        cancelTimer: null,
        inFlight: null,
        checking: null,
        recheck: false,
      });
      this.publish();
      return;
    }
    // The file was read again: if disk moved on since the buffer was based on it, treat it like an external change.
    if (file.hash !== existing.baseHash && existing.status !== "saving") this.absorb(existing, { text: file.content, hash: file.hash });
  }

  /** Reacts to a server event: a changed file that is open is compared with disk; a reconnect checks every open file. */
  async handleEvent(event: ServerEvent): Promise<void> {
    if (event.event === "stream_resumed") {
      await Promise.all([...this.buffers.keys()].map((path) => this.checkDisk(path)));
      return;
    }
    if (event.event !== "file_changed" || !isRecord(event.data)) return;
    const { path, hash } = event.data;
    if (typeof path !== "string") return;
    const buffer = this.buffers.get(path);
    // The hash of the version the buffer is based on is its own save coming back: nothing to do.
    if (buffer === undefined || (typeof hash === "string" && hash === buffer.baseHash)) return;
    await this.checkDisk(path);
  }

  /** Keeps the user's text and saves it over the disk version, after the user chose to. */
  async keepMine(path: string): Promise<void> {
    const buffer = this.buffers.get(path);
    if (buffer === undefined || buffer.status !== "conflict" || buffer.conflict === null) return;
    const disk = buffer.conflict.disk !== null ? buffer.conflict.disk : buffer.conflict.deleted ? "deleted" : await this.readDisk(buffer);
    if (disk === null) return;
    buffer.baseHash = disk === "deleted" ? null : disk.hash;
    buffer.conflict = null;
    buffer.status = "dirty";
    this.publish();
    await this.saveNow(path);
  }

  /** Replaces the user's text with the disk version, after the user chose to. A deleted file is closed. */
  async takeDisk(path: string): Promise<void> {
    const buffer = this.buffers.get(path);
    if (buffer === undefined || buffer.status !== "conflict" || buffer.conflict === null) return;
    const disk = buffer.conflict.disk !== null ? buffer.conflict.disk : buffer.conflict.deleted ? "deleted" : await this.readDisk(buffer);
    if (disk === null) return;
    if (disk === "deleted") {
      this.forget(path);
      return;
    }
    this.adopt(buffer, disk);
  }

  /** Saves the user's text under a new name next to the file and returns it, or null when that failed. */
  async saveCopy(path: string): Promise<string | null> {
    const buffer = this.buffers.get(path);
    if (buffer === undefined || buffer.status !== "conflict" || buffer.conflict === null) return null;
    for (let attempt = 1; attempt <= COPY_ATTEMPTS; attempt += 1) {
      const name = copyName(path, attempt);
      try {
        await this.api.writeFile(name, buffer.text, null);
        this.setConflict(buffer, { copiedTo: name, problem: null });
        return name;
      } catch (error) {
        if (error instanceof ApiError && (error.code === "exists" || error.code === "conflict")) continue;
        this.setConflict(buffer, { problem: messageOf(error) });
        return null;
      }
    }
    this.setConflict(buffer, { problem: "No free name was found for a copy." });
    return null;
  }

  /** Asks the editor to put the cursor at the start of `line` (1-based) of `path`, once that file is shown. */
  reveal(path: string, line: number): void {
    this.jump = { path, line, id: (this.jump?.id ?? 0) + 1 };
    this.publish();
  }

  /** Chooses the file shown in the editor. A previous file with nothing unsaved is let go; any other keeps its buffer. */
  setActive(path: string | null): void {
    const previous = this.active === null ? undefined : this.buffers.get(this.active);
    this.active = path;
    if (previous !== undefined && previous.path !== path && previous.status === "saved") this.buffers.delete(previous.path);
    this.publish();
  }

  edit(path: string, text: string): void {
    const buffer = this.buffers.get(path);
    if (buffer === undefined || buffer.text === text) return;
    buffer.text = text;
    // While a save is in flight, or the user must resolve a conflict, the state does not change on typing.
    if (buffer.status !== "saving" && buffer.status !== "conflict") {
      this.cancel(buffer);
      if (text === buffer.savedText) {
        buffer.status = "saved";
        buffer.error = null;
      } else {
        buffer.status = "dirty";
        buffer.error = null;
        this.schedule(buffer);
      }
    }
    this.publish();
  }

  /** Saves now. A buffer that is saved, or in conflict, is left alone; one that is saving is awaited. */
  async saveNow(path: string): Promise<void> {
    const buffer = this.buffers.get(path);
    if (buffer === undefined) return;
    if (buffer.inFlight !== null) return buffer.inFlight;
    this.cancel(buffer);
    if (buffer.status !== "dirty" && buffer.status !== "error") return;
    buffer.inFlight = this.save(buffer).finally(() => {
      buffer.inFlight = null;
    });
    return buffer.inFlight;
  }

  async flushAll(): Promise<void> {
    await Promise.all([...this.buffers.keys()].map((path) => this.saveNow(path)));
  }

  /** Follows a rename of a file, or of a folder that contains open files. */
  rename(from: string, to: string): void {
    const moved = [...this.buffers.values()].filter((buffer) => buffer.path === from || buffer.path.startsWith(`${from}/`));
    for (const buffer of moved) this.buffers.delete(buffer.path);
    for (const buffer of moved) {
      buffer.path = `${to}${buffer.path.slice(from.length)}`;
      this.buffers.set(buffer.path, buffer);
    }
    if (this.active !== null && (this.active === from || this.active.startsWith(`${from}/`))) this.active = `${to}${this.active.slice(from.length)}`;
    this.publish();
  }

  /** Drops the buffers of a file, or of a folder, that no longer exist. */
  forget(path: string): void {
    for (const buffer of [...this.buffers.values()]) {
      if (buffer.path !== path && !buffer.path.startsWith(`${path}/`)) continue;
      this.cancel(buffer);
      this.buffers.delete(buffer.path);
    }
    if (this.active !== null && (this.active === path || this.active.startsWith(`${path}/`))) this.active = null;
    this.publish();
  }

  dispose(): void {
    this.disposed = true;
    for (const buffer of this.buffers.values()) this.cancel(buffer);
    this.listeners.clear();
  }

  private async readDisk(buffer: Buffer): Promise<DiskVersion | null> {
    try {
      const read = await this.api.readFile(buffer.path);
      return { text: read.content, hash: read.hash };
    } catch (error) {
      if (error instanceof ApiError && error.code === "not_found") return "deleted";
      // A file that cannot be read now (not text, too large, server down) is left as it is.
      if (buffer.status === "conflict") this.setConflict(buffer, { problem: messageOf(error) });
      return null;
    }
  }

  /** Compares one buffer with disk. Checks for the same buffer run one after another, and a burst becomes one more check. */
  private checkDisk(path: string): Promise<void> {
    const buffer = this.buffers.get(path);
    if (buffer === undefined) return Promise.resolve();
    if (buffer.checking !== null) {
      buffer.recheck = true;
      return buffer.checking;
    }
    buffer.checking = (async () => {
      do {
        buffer.recheck = false;
        await this.inspect(buffer);
      } while (buffer.recheck && !this.disposed);
    })().finally(() => {
      buffer.checking = null;
    });
    return buffer.checking;
  }

  private async inspect(buffer: Buffer): Promise<void> {
    // A save in flight must finish first: its hash becomes the base, so its own echo is recognized.
    if (buffer.inFlight !== null) await buffer.inFlight.catch(() => {});
    if (this.buffers.get(buffer.path) !== buffer) return;
    const disk = await this.readDisk(buffer);
    if (disk === null || this.buffers.get(buffer.path) !== buffer) return;
    if (disk === "deleted" ? buffer.baseHash === null : disk.hash === buffer.baseHash) return;
    if (buffer.status === "saving") {
      buffer.recheck = true;
      return;
    }
    this.absorb(buffer, disk);
  }

  /** A version on disk that differs from the buffer's base: reload a clean buffer, raise a conflict for the others. */
  private absorb(buffer: Buffer, disk: DiskVersion): void {
    if (disk === "deleted") {
      if (buffer.status === "saved") this.forget(buffer.path);
      else this.enterConflict(buffer, "deleted");
      return;
    }
    if (buffer.status === "saved" || buffer.text === disk.text) this.adopt(buffer, disk);
    else this.enterConflict(buffer, disk);
  }

  /** The buffer now shows, and is based on, the disk version. */
  private adopt(buffer: Buffer, disk: { text: string; hash: string }): void {
    this.cancel(buffer);
    buffer.text = disk.text;
    buffer.savedText = disk.text;
    buffer.baseHash = disk.hash;
    buffer.status = "saved";
    buffer.error = null;
    buffer.conflict = null;
    this.publish();
  }

  /** The user's text stays; autosave stops until the user decides. */
  private enterConflict(buffer: Buffer, disk: DiskVersion): void {
    this.cancel(buffer);
    buffer.status = "conflict";
    buffer.conflict = {
      disk: disk === "deleted" ? null : disk,
      deleted: disk === "deleted",
      copiedTo: buffer.conflict?.copiedTo ?? null,
      problem: null,
    };
    this.publish();
  }

  private setConflict(buffer: Buffer, change: Partial<ConflictView>): void {
    if (buffer.conflict === null) return;
    buffer.conflict = { ...buffer.conflict, ...change };
    this.publish();
  }

  private schedule(buffer: Buffer): void {
    const timer = setTimeout(() => void this.saveNow(buffer.path), this.autosaveMs);
    buffer.cancelTimer = () => clearTimeout(timer);
  }

  private cancel(buffer: Buffer): void {
    buffer.cancelTimer?.();
    buffer.cancelTimer = null;
  }

  private async save(buffer: Buffer): Promise<void> {
    const sent = buffer.text;
    buffer.status = "saving";
    this.publish();
    try {
      const saved = await this.api.writeFile(buffer.path, sent, buffer.baseHash);
      buffer.baseHash = saved.hash;
      buffer.savedText = sent;
      buffer.error = null;
      for (const listener of [...this.savedListeners]) {
        try {
          listener(buffer.path);
        } catch {
          // A failing listener must not turn a successful save into a failure.
        }
      }
      if (buffer.text === sent) {
        buffer.status = "saved";
      } else {
        buffer.status = "dirty";
        this.schedule(buffer);
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === "conflict") {
        buffer.status = "conflict";
        buffer.conflict = { disk: null, deleted: false, copiedTo: null, problem: null };
        // Fetch the version on disk so the user can compare it with their own.
        void this.checkDisk(buffer.path);
      } else {
        buffer.status = "error";
        buffer.error = messageOf(error);
      }
    }
    this.publish();
  }

  private publish(): void {
    if (this.disposed) return;
    const buffers = new Map<string, BufferView>();
    for (const buffer of this.buffers.values()) {
      buffers.set(buffer.path, {
        path: buffer.path,
        text: buffer.text,
        status: buffer.status,
        baseHash: buffer.baseHash,
        error: buffer.error,
        conflict: buffer.conflict,
      });
    }
    this.snapshot = { buffers, active: this.active, jump: this.jump };
    for (const listener of this.listeners) listener();
  }
}
