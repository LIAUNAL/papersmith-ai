import type { ChildHandle, ProcessSpawner, SpawnSpec } from "@caztor/adapters-local";

interface Script {
  stdout?: string[];
  stderr?: string[];
  exit?: { code: number | null; signal: string | null };
}

const stream = (chunks: string[]): AsyncIterable<Uint8Array> => ({
  async *[Symbol.asyncIterator]() {
    for (const chunk of chunks) yield new TextEncoder().encode(chunk);
  },
});

/** Plays one scripted child per spawn, in order, and records every spawn. Output is delivered and the child exits at once. */
export class ScriptedSpawner implements ProcessSpawner {
  readonly calls: SpawnSpec[] = [];
  private scripts: Script[] = [];

  enqueue(script: Script): void {
    this.scripts.push(script);
  }

  spawn(spec: SpawnSpec): ChildHandle {
    this.calls.push(spec);
    const script = this.scripts.shift() ?? { exit: { code: 1, signal: null } };
    return {
      stdout: stream(script.stdout ?? []),
      stderr: stream(script.stderr ?? []),
      exit: Promise.resolve(script.exit ?? { code: 0, signal: null }),
      killGroup: () => {},
    };
  }
}
