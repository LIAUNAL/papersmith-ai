import { MAX_LOGIN_INPUT, REDACTION_MASK, type LoginInputError, type LoginKey, type LoginSessionState, type Result } from "@caztor/core";
import type { ChildHandle, Clock, ProcessSpawner, SpawnSpec } from "../infra.ts";
import { createTerminalText } from "./terminal-text.ts";

/** A sign-in ends after this long, whatever it is waiting for. */
export const LOGIN_TIMEOUT_MS = 10 * 60_000;
/** A sign-in nobody looked at for this long is ended: the person left. */
export const LOGIN_IDLE_MS = 60_000;
/** After SIGTERM, the process group gets this long before SIGKILL. */
export const KILL_GRACE_MS = 2_000;
const CHECK_EVERY_MS = 3_000;
/** A pasted line this short (a menu choice) is not masked; anything longer may be a code. */
const MIN_MASKED_INPUT = 6;

/** Values a CLI may print that must never reach the browser: API keys, OAuth tokens, JWTs. */
const SECRET_PATTERNS: readonly RegExp[] = [
  /sk-ant-[A-Za-z0-9_-]{8,}/g,
  /sk-[A-Za-z0-9_-]{20,}/g,
  /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g,
  /ya29\.[A-Za-z0-9_-]{8,}/g,
  /1\/\/[A-Za-z0-9_-]{20,}/g,
  /gh[pousr]_[A-Za-z0-9]{20,}/g,
  /((?:access|refresh|id)_token|api_key|apiKey)(["']?\s*[:=]\s*["']?)[^\s"',}]{8,}/g,
];
/** A one-time device code such as `XZIF-17WOH` or `ABCD-1234`. */
const DEVICE_CODE = /\b(?=[A-Z0-9-]*[A-Z])[A-Z0-9]{4,5}-[A-Z0-9]{4,6}\b/g;

const TERMINAL_KEYS: Readonly<Record<LoginKey, string>> = { enter: "\r", up: "\u001b[A", down: "\u001b[B", escape: "\u001b", tab: "\t" };

export interface LoginSessionOptions {
  spawner: ProcessSpawner;
  clock: Clock;
  /** What runs: already placed (sandboxed or not) by the caller. */
  spec: SpawnSpec;
  /** The program runs in a pseudo-terminal: keys are sent as a terminal sends them, and Enter is a carriage return. */
  terminal: boolean;
  /** Typed once, after the program's first output has been quiet this long (a TUI's sign-in command). */
  autoInput?: { text: string; quietMs: number };
  /**
   * Whether the sign-in is done, for a program that does not exit when it is (a TUI). Asked after every input and then
   * every `checkEveryMs`; when it holds the program is ended. With a check, an exit is a sign-in only when the check holds.
   */
  check?: () => Promise<boolean>;
  checkEveryMs?: number;
  onSignedIn(): void;
}

export interface LoginSessionView {
  state: LoginSessionState;
  text: string;
  code?: string;
  message?: string;
}

export interface LoginSession {
  /** What to show; looking keeps the session alive. */
  view(): LoginSessionView;
  send(input: { line: string } | { key: LoginKey }): Result<LoginSessionView, LoginInputError>;
  cancel(message?: string): void;
  /** Resolves once the program has exited (or could not start). */
  ended: Promise<void>;
}

const CONTROL = /[\u0000-\u001f\u007f]/;

/** One sign-in: a CLI that prints a link or a code and waits, relayed as text, with lines sent back to it. */
export function createLoginSession(options: LoginSessionOptions): LoginSession {
  const { spawner, clock, terminal } = options;
  const screen = createTerminalText();
  const secrets: string[] = [];
  let state: LoginSessionState = "running";
  let message: string | undefined;
  let lastSeen = clock.now();
  let sentInput = false;
  let autoTyped = false;
  let exited = false;
  const cancels: Array<() => void> = [];
  let cancelQuiet: (() => void) | null = null;
  let cancelCheck: (() => void) | null = null;

  const child: ChildHandle = spawner.spawn({ ...options.spec, interactive: true });

  function redacted(text: string): string {
    let out = text;
    for (const secret of [...secrets].sort((a, b) => b.length - a.length)) out = out.split(secret).join(REDACTION_MASK);
    for (const pattern of SECRET_PATTERNS) {
      out = out.replace(pattern, (match, name?: string, separator?: string) =>
        typeof name === "string" && typeof separator === "string" && match.startsWith(name) ? `${name}${separator}${REDACTION_MASK}` : REDACTION_MASK,
      );
    }
    return out;
  }

  function view(): LoginSessionView {
    const text = redacted(screen.text());
    const codes = text.match(DEVICE_CODE);
    return { state, text, ...(codes === null ? {} : { code: codes.at(-1)! }), ...(message === undefined ? {} : { message }) };
  }

  function stopTimers() {
    for (const cancel of cancels.splice(0)) cancel();
    cancelQuiet?.();
    cancelCheck?.();
    cancelQuiet = cancelCheck = null;
  }

  function kill() {
    if (exited) return;
    child.killGroup("SIGTERM");
    cancels.push(clock.setTimeout(() => (exited ? undefined : child.killGroup("SIGKILL")), KILL_GRACE_MS));
  }

  /** Ends the session in `next`; the first end wins. */
  function finish(next: Exclude<LoginSessionState, "running">, why?: string) {
    if (state !== "running") return;
    state = next;
    message = why;
    const killLater = !exited;
    stopTimers();
    if (next === "signed_in") options.onSignedIn();
    if (killLater) kill();
  }

  async function runCheck() {
    if (options.check === undefined || state !== "running") return;
    const done = await options.check().catch(() => false);
    if (done) finish("signed_in");
  }

  function scheduleCheck() {
    if (options.check === undefined || cancelCheck !== null || state !== "running") return;
    cancelCheck = clock.setTimeout(() => {
      cancelCheck = null;
      void runCheck().then(scheduleCheck);
    }, options.checkEveryMs ?? CHECK_EVERY_MS);
  }

  function heard() {
    if (options.autoInput === undefined || autoTyped || state !== "running") return;
    cancelQuiet?.();
    const { text, quietMs } = options.autoInput;
    cancelQuiet = clock.setTimeout(() => {
      cancelQuiet = null;
      if (autoTyped || state !== "running") return;
      autoTyped = true;
      child.write?.(text);
    }, quietMs);
  }

  async function pump(stream: AsyncIterable<Uint8Array>) {
    for await (const chunk of stream) {
      screen.feed(chunk);
      heard();
    }
  }

  const timeout = clock.setTimeout(() => finish("timed_out", "The sign-in took longer than 10 minutes, so it was stopped. Start it again."), LOGIN_TIMEOUT_MS);
  cancels.push(timeout);
  const watchIdle = () => {
    cancels.push(
      clock.setTimeout(() => {
        if (state !== "running") return;
        if (clock.now() - lastSeen >= LOGIN_IDLE_MS) finish("cancelled", "The sign-in was stopped because nobody was following it.");
        else watchIdle();
      }, LOGIN_IDLE_MS / 4),
    );
  };
  watchIdle();

  const ended = (async () => {
    const output = Promise.all([pump(child.stdout), pump(child.stderr)]);
    let exit: { code: number | null; signal: string | null };
    try {
      exit = await child.exit;
    } catch {
      exited = true;
      finish("failed", "The sign-in could not be started.");
      return;
    }
    exited = true;
    await output.catch(() => {});
    if (state !== "running") return;
    if (options.check !== undefined) {
      if (await options.check().catch(() => false)) finish("signed_in");
      else finish("failed", "The program ended without a sign-in.");
      return;
    }
    if (exit.code === 0) finish("signed_in");
    else finish("failed", `The sign-in ended without success (${exit.code === null ? `signal ${exit.signal ?? "unknown"}` : `exit code ${exit.code}`}).`);
  })();

  return {
    view() {
      lastSeen = clock.now();
      return view();
    },
    send(input) {
      lastSeen = clock.now();
      if (state !== "running") return { ok: false, error: { code: "ended", message: "This sign-in has ended. Start it again." } };
      let bytes: string;
      if ("key" in input) {
        if (!terminal && input.key !== "enter") return { ok: false, error: { code: "invalid_input", message: "This sign-in takes only lines of text." } };
        bytes = terminal ? TERMINAL_KEYS[input.key] : "\n";
      } else {
        if (input.line.length > MAX_LOGIN_INPUT) return { ok: false, error: { code: "invalid_input", message: `A line can be at most ${MAX_LOGIN_INPUT} characters.` } };
        if (CONTROL.test(input.line)) return { ok: false, error: { code: "invalid_input", message: "Send one line, without control characters." } };
        if (input.line.trim().length >= MIN_MASKED_INPUT) secrets.push(input.line.trim());
        bytes = `${input.line}${terminal ? "\r" : "\n"}`;
      }
      child.write?.(bytes);
      if (!sentInput) {
        sentInput = true;
        void runCheck().then(scheduleCheck);
      }
      return { ok: true, value: view() };
    },
    cancel(why = "The sign-in was cancelled.") {
      finish("cancelled", why);
    },
    ended,
  };
}
