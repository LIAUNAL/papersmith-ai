import type { ChildHandle, ProcessSpawner, SpawnSpec } from "../../src/infra.ts";

type Signal = "SIGINT" | "SIGTERM" | "SIGKILL";
type Exit = { code: number | null; signal: string | null };

export interface ChildScript {
  /** Chunks delivered verbatim. Strings are UTF-8 encoded; pass bytes to control chunk boundaries. */
  stdout?: (string | Uint8Array)[];
  stderr?: (string | Uint8Array)[];
  /** Exit reported once the output is delivered. Without it the child stays alive until a signal ends it. */
  exit?: Exit;
  /** Signals that do not terminate the child (SIGKILL always does). */
  ignores?: Signal[];
  /** The binary cannot be started: `exit` rejects with an error carrying this code. */
  spawnError?: string;
}

/** Cuts the UTF-8 encoding of `text` at the given byte offsets, which may fall inside a character. */
export function splitBytes(text: string, offsets: number[]): Uint8Array[] {
  const bytes = new TextEncoder().encode(text);
  const parts: Uint8Array[] = [];
  let start = 0;
  for (const offset of offsets) {
    parts.push(bytes.slice(start, offset));
    start = offset;
  }
  parts.push(bytes.slice(start));
  return parts;
}

class Channel implements AsyncIterable<Uint8Array> {
  private queue: Uint8Array[] = [];
  private waiting: ((result: IteratorResult<Uint8Array>) => void)[] = [];
  private closed = false;

  push(chunk: Uint8Array): void {
    const waiter = this.waiting.shift();
    if (waiter) waiter({ value: chunk, done: false });
    else this.queue.push(chunk);
  }

  close(): void {
    this.closed = true;
    for (const waiter of this.waiting.splice(0)) waiter({ value: undefined, done: true });
  }

  [Symbol.asyncIterator](): AsyncIterator<Uint8Array> {
    return {
      next: () => {
        const chunk = this.queue.shift();
        if (chunk !== undefined) return Promise.resolve({ value: chunk, done: false });
        if (this.closed) return Promise.resolve({ value: undefined, done: true });
        return new Promise((resolve) => this.waiting.push(resolve));
      },
    };
  }
}

function toBytes(chunk: string | Uint8Array): Uint8Array {
  return typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk;
}

/** Replays scripted children in spawn order and records every spawn spec and signal. */
export class FakeSpawner implements ProcessSpawner {
  readonly calls: SpawnSpec[] = [];
  readonly signals: Signal[] = [];
  /** Everything written to an interactive child's stdin, in order. */
  readonly written: string[] = [];
  private scripts: ChildScript[] = [];
  private latest: { stdout: Channel; stderr: Channel } | undefined;

  enqueue(script: ChildScript): void {
    this.scripts.push(script);
  }

  /** Delivers more stderr to the most recently spawned child, as if it printed it now. */
  pushStderr(chunk: string | Uint8Array): void {
    this.requireLatest().stderr.push(toBytes(chunk));
  }

  pushStdout(chunk: string | Uint8Array): void {
    this.requireLatest().stdout.push(toBytes(chunk));
  }

  private requireLatest(): { stdout: Channel; stderr: Channel } {
    if (this.latest === undefined) throw new Error("FakeSpawner: no child has been spawned");
    return this.latest;
  }

  spawn(spec: SpawnSpec): ChildHandle {
    this.calls.push(spec);
    const script = this.scripts.shift();
    if (script === undefined) throw new Error(`FakeSpawner: no script queued for spawn #${this.calls.length}`);

    const stdout = new Channel();
    const stderr = new Channel();
    this.latest = { stdout, stderr };
    let finish: (exit: Exit) => void = () => {};
    let fail: (error: Error) => void = () => {};
    const exit = new Promise<Exit>((resolve, reject) => {
      finish = resolve;
      fail = reject;
    });
    exit.catch(() => {});

    const end = (result: Exit): void => {
      stdout.close();
      stderr.close();
      finish(result);
    };

    if (script.spawnError !== undefined) {
      fail(Object.assign(new Error(`spawn ${spec.file} ${script.spawnError}`), { code: script.spawnError }));
      stdout.close();
      stderr.close();
    } else {
      for (const chunk of script.stdout ?? []) stdout.push(toBytes(chunk));
      for (const chunk of script.stderr ?? []) stderr.push(toBytes(chunk));
      if (script.exit !== undefined) end(script.exit);
    }

    return {
      stdout,
      stderr,
      exit,
      write: (text) => {
        if (spec.interactive === true) this.written.push(text);
      },
      killGroup: (signal) => {
        this.signals.push(signal);
        if (script.ignores?.includes(signal) && signal !== "SIGKILL") return;
        end({ code: null, signal });
      },
    };
  }
}
