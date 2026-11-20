import type { ChildHandle, ProcessSpawner, SpawnSpec } from "../../src/infra.ts";
type Signal = "SIGINT" | "SIGTERM" | "SIGKILL";
type Exit = {
    code: number | null;
    signal: string | null;
};
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
export declare function splitBytes(text: string, offsets: number[]): Uint8Array[];
/** Replays scripted children in spawn order and records every spawn spec and signal. */
export declare class FakeSpawner implements ProcessSpawner {
    readonly calls: SpawnSpec[];
    readonly signals: Signal[];
    private scripts;
    private latest;
    enqueue(script: ChildScript): void;
    /** Delivers more stderr to the most recently spawned child, as if it printed it now. */
    pushStderr(chunk: string | Uint8Array): void;
    pushStdout(chunk: string | Uint8Array): void;
    private requireLatest;
    spawn(spec: SpawnSpec): ChildHandle;
}
export {};
