import { createProjectStore } from "../../src/project-store.ts";
import type { ChildHandle, FileSystem, ProcessSpawner, SpawnSpec } from "../../src/infra.ts";
import { createTectonicCompiler, type TectonicCompilerOptions } from "../../src/tectonic/compiler.ts";
import { FakeClock } from "../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../fakes/memory-fs.ts";
import type { CompileEvent, CompileRequest, CompilerPort, RelPath } from "@caztor/core";

export const ROOT = "/proj";

export const request = (overrides: Partial<CompileRequest> = {}): CompileRequest => ({
  main: "main.tex" as RelPath,
  stopOnFirstError: false,
  ...overrides,
});

export interface Harness {
  fs: MemoryFileSystem;
  clock: FakeClock;
  fake: FakeSpawner;
  compiler: CompilerPort;
  /** Every spawn spec, in order. */
  calls: SpawnSpec[];
  /** Queues a child. `writes` are files the engine creates (paths relative to the project) when it starts. */
  child(script: ChildScript, writes?: Record<string, string>): void;
}

export function harness(
  files: Record<string, string> = { "/proj/main.tex": "\\documentclass{article}" },
  options: Partial<TectonicCompilerOptions> & { wrapFs?: (fs: FileSystem) => FileSystem } = {},
): Harness {
  const { wrapFs, ...compilerOptions } = options;
  const fs = new MemoryFileSystem(files);
  const clock = new FakeClock(1000);
  const fake = new FakeSpawner();
  const pendingWrites: Record<string, string>[] = [];
  const spawner: ProcessSpawner = {
    spawn(spec): ChildHandle {
      const writes = pendingWrites.shift() ?? {};
      for (const [path, text] of Object.entries(writes)) void fs.writeFile(`${ROOT}/${path}`, new TextEncoder().encode(text));
      return fake.spawn(spec);
    },
  };
  let counter = 0;
  const compiler = createTectonicCompiler({
    spawner,
    clock,
    fs: wrapFs === undefined ? fs : wrapFs(fs),
    root: ROOT,
    store: createProjectStore({ fs, root: ROOT }),
    parentEnv: { PATH: "/usr/bin", HOME: "/home/test", SECRET_TOKEN: "do-not-leak" },
    newCompileId: () => `c${(counter += 1)}`,
    ...compilerOptions,
  });
  return {
    fs,
    clock,
    fake,
    compiler,
    calls: fake.calls,
    child(script, writes = {}) {
      fake.enqueue(script);
      pendingWrites.push(writes);
    },
  };
}

export async function drain(events: AsyncIterable<CompileEvent>): Promise<CompileEvent[]> {
  const all: CompileEvent[] = [];
  for await (const event of events) all.push(event);
  return all;
}

export function finishedOf(events: CompileEvent[]) {
  const finished = events.find((event) => event.type === "finished");
  if (finished === undefined || finished.type !== "finished") throw new Error("the run produced no finished event");
  return finished.result;
}

export const phasesOf = (events: CompileEvent[]) => events.flatMap((event) => (event.type === "phase" ? [event.phase] : []));

export const text = (bytes: Uint8Array | null) => (bytes === null ? null : new TextDecoder().decode(bytes));
