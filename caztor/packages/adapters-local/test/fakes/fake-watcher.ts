import type { DirectoryWatcher } from "../../src/infra.ts";

interface Registration {
  dir: string;
  listener: (relativePath: string | null) => void;
  onError: (error: Error) => void;
}

/** A directory watcher driven by hand: tests call `emit` and `fail` instead of touching the file system. */
export class FakeDirectoryWatcher implements DirectoryWatcher {
  private registrations: Registration[] = [];
  /** How many times `watch` was called, closed or not. */
  starts = 0;
  /** Makes the next `watch` call throw this error, as an unsupported recursive watch would. */
  failToStart: Error | null = null;

  watch(dir: string, listener: (relativePath: string | null) => void, onError: (error: Error) => void): () => void {
    this.starts += 1;
    if (this.failToStart !== null) {
      const error = this.failToStart;
      this.failToStart = null;
      throw error;
    }
    const registration: Registration = { dir, listener, onError };
    this.registrations.push(registration);
    return () => {
      this.registrations = this.registrations.filter((candidate) => candidate !== registration);
    };
  }

  /** Watches that are open right now. */
  get active(): number {
    return this.registrations.length;
  }

  /** Directories that are being watched right now. */
  get directories(): string[] {
    return this.registrations.map((registration) => registration.dir);
  }

  emit(relativePath: string | null): void {
    for (const registration of [...this.registrations]) registration.listener(relativePath);
  }

  fail(error: Error): void {
    for (const registration of [...this.registrations]) registration.onError(error);
  }
}
