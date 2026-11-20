import type { LoginMethod, LoginRelayPort, LoginStartError, LoginView, ProviderId, Result, TurnUser } from "@caztor/core";
import { terminalArgs, terminalProgram, type AgentSandbox } from "../agent-sandbox.ts";
import type { Clock, FileSystem, ProcessSpawner, SpawnSpec } from "../infra.ts";
import { resolveBinary } from "../providers/resolve-binary.ts";
import { run } from "../sandbox.ts";
import { collaboratorEnv } from "../user-home.ts";
import { createLoginSession, type LoginSession } from "./session.ts";

/** How a sign-in is told to be done when the CLI does not exit after it. */
type Check = "pi_auth_file" | "agy_models";

interface Method extends LoginMethod {
  binary: string;
  args: readonly string[];
  terminal: boolean;
  autoInput?: string;
  check?: Check;
}

/** Pi's flags that keep it from loading anything of the project or its own extensions while it only signs in. */
const PI_QUIET = ["-na", "-ne", "--no-mcp", "-ns", "-np", "--no-themes", "-nc"];

/**
 * The sign-in of each CLI, as observed with an empty home: claude prints a URL with a public redirect and reads the
 * pasted code from stdin; codex and opencode (headless ChatGPT) print a link and a device code and poll; Pi signs in
 * only from its TUI (`/login`); agy prints its OAuth menu when it starts signed out and reads the code from /dev/tty.
 */
const METHODS: Readonly<Record<ProviderId, readonly Method[]>> = {
  claude: [{ id: "subscription", label: "Claude subscription (Pro or Max)", binary: "claude", args: ["auth", "login", "--claudeai"], terminal: false }],
  codex: [{ id: "device", label: "ChatGPT account (device code)", binary: "codex", args: ["login", "--device-auth"], terminal: false }],
  opencode: [
    { id: "chatgpt", label: "ChatGPT Pro/Plus (device code)", binary: "opencode", args: ["auth", "login", "-p", "openai", "-m", "ChatGPT Pro/Plus (headless)"], terminal: false },
    { id: "menu", label: "Another provider (opencode's own menu)", binary: "opencode", args: ["auth", "login"], terminal: true },
  ],
  pi: [{ id: "login", label: "Pi's /login", binary: "pi", args: PI_QUIET, terminal: true, autoInput: "/login\r", check: "pi_auth_file" }],
  antigravity: [{ id: "google", label: "Google account", binary: "agy", args: [], terminal: true, check: "agy_models" }],
};

/** How long `agy models` may take to say whether the sign-in worked. */
const CHECK_LIMIT_MS = 20_000;
/** How long the program must be quiet before the opening command is typed. */
const AUTO_INPUT_QUIET_MS = 1_500;

export interface LoginRelayOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** The server's environment: the host's sign-in gets it as it is; a collaborator's only its harmless part. */
  env: Readonly<Record<string, string | undefined>>;
  /** Runs collaborators' sign-ins. Without it they are refused. */
  sandbox?: AgentSandbox;
  /** The collaborator's private folder, made when missing. */
  homeOf(user: TurnUser): Promise<Result<string, { message: string }>>;
  onSignedIn(user: TurnUser, provider: ProviderId): void;
}

interface Placed {
  spec: SpawnSpec;
  release(): Promise<void>;
}

interface Entry {
  provider: ProviderId;
  method: Method;
  session: LoginSession;
}

const keyOf = (user: TurnUser) => (user.role === "host" ? "\u0000host" : user.id);
const defined = (env: Readonly<Record<string, string | undefined>>) => Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));

/** The browser sign-in of every person of one project runtime. */
export function createLoginRelay(options: LoginRelayOptions): LoginRelayPort {
  const { fs, spawner, clock } = options;
  const entries = new Map<string, Entry>();
  /** The start under way per person: a second one waits for it, so the one before is always ended before a new one runs. */
  const starting = new Map<string, Promise<unknown>>();

  /**
   * A fresh empty folder closed to others, for the host's sign-in to run in. Never the project: a collaborator's turn
   * can write it, and a CLI loads project files (an opencode plugin, a Claude setting) from the folder it starts in.
   */
  async function hostFolder(): Promise<Result<string, LoginStartError>> {
    try {
      return { ok: true, value: await fs.mkdtemp(`${(options.env["TMPDIR"] ?? "/tmp").replace(/\/+$/, "")}/caztor-login-`) };
    } catch {
      return { ok: false, error: { code: "unavailable", message: "A private folder for the sign-in could not be made." } };
    }
  }

  /**
   * How to run `args` of the CLI for this person: inside their sandbox, or as the host would from an empty folder of
   * its own. `release` removes what was made for it, once the program has ended.
   */
  async function place(user: TurnUser, provider: ProviderId, binary: string, args: readonly string[], terminal: boolean): Promise<Result<Placed, LoginStartError>> {
    if (user.role === "host") {
      const script = terminal ? await terminalProgram(fs) : undefined;
      if (script === null) return { ok: false, error: { code: "unavailable", message: "The system's script program (util-linux) was not found, so this sign-in cannot get a terminal." } };
      const folder = await hostFolder();
      if (!folder.ok) return folder;
      const cwd = folder.value;
      const release = () => fs.rm(cwd, { recursive: true, force: true }).catch(() => {});
      const env = { ...defined(options.env), PWD: cwd };
      if (script === undefined) return { ok: true, value: { spec: { file: binary, args, cwd, env }, release } };
      return { ok: true, value: { spec: { file: script, args: terminalArgs(binary, args), cwd, env: { ...env, SHELL: "/bin/sh" } }, release } };
    }
    const refuse = (message: string): Result<never, LoginStartError> => ({ ok: false, error: { code: "isolation_failed", message: `Your sign-in was not started because it could not run in the sandbox: ${message}` } });
    if (options.sandbox === undefined) return refuse("this server has no sandbox for collaborators.");
    const home = await options.homeOf(user);
    if (!home.ok) return refuse(home.error.message);
    const wrapper = await options.sandbox.wrapper({ binary, home: home.value, terminal });
    if (!wrapper.ok) return refuse(wrapper.reason);
    const spec = wrapper.value({ file: binary, args, cwd: home.value, env: collaboratorEnv(options.env, home.value, provider) });
    return { ok: true, value: { spec, release: async () => {} } };
  }

  /** The check of a CLI that stays open after signing in. Its starting point is read now, so an older login does not count. */
  async function checkOf(user: TurnUser, provider: ProviderId, binary: string, method: Method): Promise<(() => Promise<boolean>) | undefined> {
    if (method.check === "pi_auth_file") {
      const home = user.role === "host" ? null : await options.homeOf(user);
      const agentDir = home === null ? (options.env["PI_CODING_AGENT_DIR"] ?? `${options.env["HOME"] ?? ""}/.pi/agent`) : home.ok ? `${home.value}/.pi/agent` : null;
      if (agentDir === null) return undefined;
      // Only whether Pi wrote its auth file since the sign-in started; the file itself is never read.
      const changedAt = async () => (await fs.stat(`${agentDir}/auth.json`).catch(() => null))?.ctimeMs ?? null;
      const before = await changedAt();
      return async () => {
        const now = await changedAt();
        return now !== null && now !== before;
      };
    }
    if (method.check === "agy_models") {
      return async () => {
        const placed = await place(user, provider, binary, ["models"], false);
        if (!placed.ok) return false;
        try {
          return (await run(spawner, clock, placed.value.spec, CHECK_LIMIT_MS)).code === 0;
        } finally {
          await placed.value.release();
        }
      };
    }
    return undefined;
  }

  /** Starts a sign-in for this person; `start` runs these one at a time per person. */
  async function begin(user: TurnUser, provider: ProviderId, methodId: string | undefined): Promise<Result<LoginView, LoginStartError>> {
    const method = methodId === undefined ? METHODS[provider][0] : METHODS[provider].find((candidate) => candidate.id === methodId);
    if (method === undefined) return { ok: false, error: { code: "unknown_method", message: `${provider} has no sign-in method "${methodId ?? ""}".` } };
    // One sign-in per person: a new one ends the one before, whichever provider it was for.
    entries.get(keyOf(user))?.session.cancel("Another sign-in was started.");
    entries.delete(keyOf(user));
    const binary = await resolveBinary(fs, method.binary, options.env["PATH"]);
    if (binary === null) return { ok: false, error: { code: "not_installed", message: `${method.binary} was not found on the host. Ask the host to install it.` } };
    const placed = await place(user, provider, binary, method.args, method.terminal);
    if (!placed.ok) return placed;
    let session: LoginSession;
    try {
      const check = await checkOf(user, provider, binary, method);
      session = createLoginSession({
        spawner,
        clock,
        spec: placed.value.spec,
        terminal: method.terminal,
        ...(method.autoInput === undefined ? {} : { autoInput: { text: method.autoInput, quietMs: AUTO_INPUT_QUIET_MS } }),
        ...(check === undefined ? {} : { check }),
        onSignedIn: () => options.onSignedIn(user, provider),
      });
    } catch (error) {
      await placed.value.release();
      throw error;
    }
    void session.ended.finally(() => placed.value.release());
    const entry: Entry = { provider, method, session };
    entries.set(keyOf(user), entry);
    return { ok: true, value: viewOf(entry) };
  }

  function viewOf(entry: Entry): LoginView {
    return { provider: entry.provider, method: entry.method.id, terminal: entry.method.terminal, ...entry.session.view() };
  }

  function own(user: TurnUser, provider: ProviderId): Entry | null {
    const entry = entries.get(keyOf(user));
    return entry !== undefined && entry.provider === provider ? entry : null;
  }

  return {
    methods: (provider) => METHODS[provider].map(({ id, label }) => ({ id, label })),

    start(user, provider, methodId) {
      const key = keyOf(user);
      const started = (starting.get(key) ?? Promise.resolve()).then(() => begin(user, provider, methodId));
      const settled = started.catch(() => {});
      starting.set(key, settled);
      void settled.then(() => {
        if (starting.get(key) === settled) starting.delete(key);
      });
      return started;
    },

    view(user, provider) {
      const entry = own(user, provider);
      return entry === null ? null : viewOf(entry);
    },

    send(user, provider, input) {
      const entry = own(user, provider);
      if (entry === null) return { ok: false, error: { code: "not_found", message: "There is no sign-in of yours to this provider. Start one first." } };
      const sent = entry.session.send(input);
      return sent.ok ? { ok: true, value: viewOf(entry) } : sent;
    },

    cancel(user, provider) {
      const entry = own(user, provider);
      if (entry === null) return false;
      entry.session.cancel();
      return true;
    },

    async close() {
      const all = [...entries.values()];
      entries.clear();
      for (const entry of all) entry.session.cancel("The project was closed.");
      await Promise.all(all.map((entry) => entry.session.ended));
    },
  };
}
