import { redactSecrets, redactValue } from "@caztor/core";
import type { AgentEvent } from "@caztor/core";
import type { ChildHandle, Clock, ProcessSpawner, SpawnSpec } from "../infra.ts";
import { createLineSplitter } from "./lines.ts";

/** After a stop, SIGINT goes first; SIGTERM follows after `term` ms and SIGKILL `kill` ms after that. */
export const STOP_ESCALATION_MS = { term: 3000, kill: 2000 } as const;
export const PROBE_LIMIT_MS = 5000;
/** A process that is still running this long after its last event is ended. */
const LINGER_MS = 2000;
const STDERR_TAIL_CHARS = 4096;
/** The largest secret that can be stored (see `API_KEY_MAX_LENGTH`): the raw window of error output keeps this much extra, so a key cut at the edge is still seen whole. */
const SECRET_WINDOW_CHARS = 512;

export const failed = (code: Extract<AgentEvent, { type: "error" }>["code"], message: string): AgentEvent[] => [
  { type: "error", code, message },
  { type: "done", reason: "failed" },
];

/** What every provider's mapper reports for one line. */
export interface DrivenOutcome {
  events: AgentEvent[];
  /** The stream cannot be trusted; the events already end the turn. */
  fatal: boolean;
  /** Nothing more is expected from the CLI, though it has not exited: a process that lingers is ended. */
  final?: boolean;
}

export interface DrivenMapper<O extends DrivenOutcome> {
  feed(line: string): O;
  oversize(): AgentEvent[];
  finish(how: { cancelled: boolean; exitCode: number | null; stderrTail: string }): AgentEvent[];
}

export interface DriveOptions<O extends DrivenOutcome> {
  spawner: ProcessSpawner;
  clock: Clock;
  spec: SpawnSpec;
  signal: AbortSignal;
  mapper: DrivenMapper<O>;
  /** The message of the error when the CLI cannot be started. */
  notStarted: string;
  /** Receives every raw line of the CLI's output. */
  tap?: ((line: string) => void) | undefined;
  /** Judges what the mapper reported: a text is an isolation violation, which ends the turn at once. */
  check?: ((outcome: O) => string | null) | undefined;
  /** Leaves out the events of the line that broke the isolation. */
  dropEventsOnViolation?: boolean;
  /** Tells the caller which process is running (for a forced stop), and null when it ended. */
  onChild?: ((child: ChildHandle | null) => void) | undefined;
  /**
   * Values that must not leave the adapter (API keys of this turn). They are masked in the tapped lines, in the end of the
   * error output and in every string of every event, including the ones this function builds itself.
   */
  secrets?: readonly string[] | undefined;
}

/**
 * Starts the CLI and turns its output into events, owning what every provider shares: the line reader, the stop
 * escalation (SIGINT, SIGTERM, SIGKILL), ending a process that lingers, the end of the error output and exactly one
 * `done`. What a line means, and which tools are allowed, is the mapper's and the caller's.
 */
export function drive<O extends DrivenOutcome>(options: DriveOptions<O>): AsyncGenerator<AgentEvent> {
  const secrets = options.secrets ?? [];
  if (secrets.length === 0) return driveEvents(options);
  return scrubbed(driveEvents(options), secrets);
}

async function* scrubbed(events: AsyncGenerator<AgentEvent>, secrets: readonly string[]): AsyncGenerator<AgentEvent> {
  for await (const event of events) yield redactValue(event, secrets);
}

async function* driveEvents<O extends DrivenOutcome>(options: DriveOptions<O>): AsyncGenerator<AgentEvent> {
  const { spawner, clock, signal, mapper } = options;
  const secrets = options.secrets ?? [];
  let child: ChildHandle;
  try {
    child = spawner.spawn(options.spec);
  } catch {
    yield* failed("not_installed", options.notStarted);
    return;
  }
  options.onChild?.(child);

  let exited = false;
  const exit = child.exit.then(
    (result) => ({ result }),
    (error: unknown) => ({ error }),
  );
  const timers: Array<() => void> = [];
  const schedule = (fn: () => void, ms: number) => void timers.push(clock.setTimeout(fn, ms));
  void exit.then(() => {
    exited = true;
    for (const cancel of timers.splice(0)) cancel();
  });
  /** SIGTERM now, SIGKILL later: for a process that must go and has no one waiting on it. */
  const terminate = () => {
    if (exited) return;
    child.killGroup("SIGTERM");
    schedule(() => child.killGroup("SIGKILL"), STOP_ESCALATION_MS.kill);
  };
  const onAbort = () => {
    if (exited) return;
    child.killGroup("SIGINT");
    schedule(() => {
      child.killGroup("SIGTERM");
      schedule(() => child.killGroup("SIGKILL"), STOP_ESCALATION_MS.kill);
    }, STOP_ESCALATION_MS.term);
  };
  signal.addEventListener("abort", onAbort, { once: true });
  if (signal.aborted) onAbort();

  // The raw window is masked only when it is read, so a secret split between two chunks is seen whole.
  let stderrRaw = "";
  const errors = (async () => {
    const decoder = new TextDecoder();
    try {
      for await (const chunk of child.stderr) stderrRaw = (stderrRaw + decoder.decode(chunk, { stream: true })).slice(-(STDERR_TAIL_CHARS + SECRET_WINDOW_CHARS));
    } catch {
      // No error output.
    }
  })();

  const splitter = createLineSplitter();
  let ended = false;
  let lingering = false;
  /** The events to pass on; after a stop the CLI's own error and done are replaced by one cancelled done. */
  const pass = (events: AgentEvent[]): AgentEvent[] => {
    const out: AgentEvent[] = [];
    for (const event of events) {
      if (signal.aborted && (event.type === "error" || event.type === "done")) continue;
      out.push(event);
      if (event.type === "done") ended = true;
    }
    return out;
  };

  try {
    reading: for await (const chunk of child.stdout) {
      const lines = splitter.push(chunk);
      if (splitter.dropped() > 0) yield* pass(mapper.oversize());
      for (const text of lines) {
        options.tap?.(redactSecrets(text, secrets));
        const outcome = mapper.feed(text);
        const problem = options.check?.(outcome) ?? null;
        if (problem === null || options.dropEventsOnViolation !== true) yield* pass(outcome.events);
        if (problem !== null) {
          terminate();
          yield* failed("isolation_failed", problem);
          ended = true;
          return;
        }
        if (outcome.fatal) {
          terminate();
          ended = true;
          return;
        }
        if (ended) {
          // The CLI normally exits at once; one that lingers is ended.
          schedule(terminate, LINGER_MS);
          break reading;
        }
        if (outcome.final === true && !lingering) {
          lingering = true;
          schedule(terminate, LINGER_MS);
        }
      }
    }
    const last = splitter.rest();
    if (!ended && last !== "") {
      const outcome = mapper.feed(last);
      const problem = options.check?.(outcome) ?? null;
      if (problem === null || options.dropEventsOnViolation !== true) yield* pass(outcome.events);
      if (problem !== null) {
        terminate();
        yield* failed("isolation_failed", problem);
        ended = true;
        return;
      }
    }
    if (ended) return;

    const outcome = await exit;
    await errors;
    if ("error" in outcome && !signal.aborted) {
      yield* failed("not_installed", options.notStarted);
      ended = true;
      return;
    }
    const exitCode = "result" in outcome ? outcome.result.code : null;
    yield* pass(mapper.finish({ cancelled: signal.aborted, exitCode, stderrTail: redactSecrets(stderrRaw, secrets).slice(-STDERR_TAIL_CHARS) }));
    if (!ended) yield { type: "done", reason: "cancelled" };
    ended = true;
  } finally {
    signal.removeEventListener("abort", onAbort);
    options.onChild?.(null);
    if (!ended && !exited) terminate();
  }
}

export type ProbeResult = { ok: true; output: string } | { ok: false; reason: string };

/**
 * Runs `file args` to read its output, within a time limit. `label` is the product's name in the reasons given when
 * it cannot run.
 */
export async function probe(options: { spawner: ProcessSpawner; clock: Clock; file: string; args: string[]; cwd: string; env: Readonly<Record<string, string>>; label: string; limitMs?: number }): Promise<ProbeResult> {
  const { clock, label } = options;
  const limit = options.limitMs ?? PROBE_LIMIT_MS;
  const command = options.args[0] ?? "";
  let child: ChildHandle;
  try {
    child = options.spawner.spawn({ file: options.file, args: options.args, cwd: options.cwd, env: options.env });
  } catch (error) {
    return { ok: false, reason: `${label} could not be started${error instanceof Error ? `: ${error.message}` : "."}` };
  }
  let output = "";
  let errorOutput = "";
  const read = async (stream: AsyncIterable<Uint8Array>, add: (text: string) => void) => {
    const decoder = new TextDecoder();
    try {
      for await (const chunk of stream) add(decoder.decode(chunk, { stream: true }));
    } catch {
      // Treated as no output.
    }
  };
  const collected = Promise.all([read(child.stdout, (text) => void (output += text)), read(child.stderr, (text) => void (errorOutput += text))]);
  let timedOut = false;
  const cancelLimit = clock.setTimeout(() => {
    timedOut = true;
    child.killGroup("SIGTERM");
  }, limit);
  const timeout = { ok: false, reason: `${label} did not answer ${command} within ${Math.round(limit / 1000)} seconds.` } as const;
  try {
    const result = await child.exit;
    await collected;
    if (timedOut) return timeout;
    if (result.code !== 0) {
      const detail = errorOutput.trim().split("\n").at(-1)?.slice(0, 200) ?? "";
      return { ok: false, reason: `${label} was found but failed to run (exit code ${result.code ?? "none"})${detail === "" ? "" : `: ${detail}`}` };
    }
    return { ok: true, output };
  } catch (error) {
    if (timedOut) return timeout;
    return { ok: false, reason: `${label} could not be started${error instanceof Error ? `: ${error.message}` : "."}` };
  } finally {
    cancelLimit();
  }
}
