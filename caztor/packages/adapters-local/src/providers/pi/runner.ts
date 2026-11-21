import type { AgentEvent, AgentRunnerPort, CredentialReaderPort, ProviderStatus, TurnRequest } from "@caztor/core";
import { AGENT_TARGETS, credentialSlot, parseModel, PROVIDER_IDS, providerSlots, type PI_API_VENDORS } from "@caztor/core";
import type { ChildHandle, Clock, FileSystem, ProcessSpawner } from "../../infra.ts";
import { placeTurn, type AgentSandbox } from "../../agent-sandbox.ts";
import { drive, failed, probe, STOP_ESCALATION_MS } from "../drive.ts";
import { resolveBinary } from "../resolve-binary.ts";
import { readStoredKey } from "../stored-key.ts";
import { isOlder, versionOf } from "../version.ts";
import { createPiMapper, PI_ALLOWED_TOOLS, PI_ISOLATION_TIER, PI_LOGIN_HINT, PI_TESTED_VERSION, type PiAllowedTool, type PiMapOutcome } from "./mapper.ts";

export { PI_ALLOWED_TOOLS, PI_ISOLATION_TIER, PI_LOGIN_HINT, PI_TESTED_VERSION, STOP_ESCALATION_MS };

/**
 * What Pi's partial isolation means. The chat panel shows it for as long as Pi is chosen (and the first-run notice
 * covers it), so a turn does not repeat it in the conversation.
 */
export const PI_PARTIAL_ISOLATION_NOTICE =
  "Pi runs with partial isolation: your global Pi settings and sign-in in ~/.pi/agent/ still load, and Caztor cannot turn them off. The project's own .pi/ folder, extensions, skills, MCP servers and context files are switched off. Caztor allows only file reading and editing tools and stops the turn when another tool appears, though that tool may already have started.";

/** Variables the CLI inherits: where to find itself and its login, the locale, the network and certificates. No provider key passes. */
export const PI_ENV_NAMES: readonly string[] = [
  "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "PI_CODING_AGENT_DIR",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
];

/** The variable each vendor's key goes in, as Pi reads it (its `docs/providers.md`). */
export const PI_VENDOR_ENV: Readonly<Record<(typeof PI_API_VENDORS)[number], string>> = {
  anthropic: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  google: "GEMINI_API_KEY",
  openrouter: "OPENROUTER_API_KEY",
  groq: "GROQ_API_KEY",
  xai: "XAI_API_KEY",
  mistral: "MISTRAL_API_KEY",
  deepseek: "DEEPSEEK_API_KEY",
  cerebras: "CEREBRAS_API_KEY",
  opencode: "OPENCODE_API_KEY",
};

/** Where Pi keeps the sessions of this project's chats. */
export const PI_SESSIONS_DIR = ".caztor/pi-sessions";
/** In api mode Pi's agent folder is this empty one, so a saved login or global setting cannot win over the key. */
export const PI_API_AGENT_DIR = ".caztor/pi-agent-api";

const SESSION_ID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** A row of `pi --list-models`: the provider and the model id, then the other columns. */
const MODEL_ROW = /^([a-z0-9][a-z0-9._-]*)\s+([A-Za-z0-9][A-Za-z0-9._:\/-]*)(?:\s|$)/;
const MODELS_CACHE_MS = 30_000;
const MODELS_LIMIT_MS = 15_000;
/** Turns off what Pi would otherwise load from the project, the network and its own folders. */
const ISOLATION_FLAGS = ["-na", "-ne", "--no-mcp", "-ns", "-np", "--no-themes", "-nc", "--offline"];

const pick = (parent: Readonly<Record<string, string | undefined>>, names: readonly string[]): Record<string, string> => {
  const env: Record<string, string> = {};
  for (const name of names) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  return env;
};

const trimmed = (root: string) => root.replace(/\/+$/, "");

/**
 * The environment of a turn: the allowed names of the server's and Pi's switches for no network checks or telemetry.
 * In api mode `api` adds only that vendor's variable and points Pi's agent folder at an empty one of the project's.
 */
export function buildPiEnv(parent: Readonly<Record<string, string | undefined>>, root: string, api?: { variable: string; key: string }): Record<string, string> {
  return {
    ...pick(parent, PI_ENV_NAMES),
    ...(api === undefined ? {} : { [api.variable]: api.key, PI_CODING_AGENT_DIR: `${trimmed(root)}/${PI_API_AGENT_DIR}` }),
    NO_COLOR: "1",
    PI_OFFLINE: "1",
    PI_SKIP_VERSION_CHECK: "1",
    PI_TELEMETRY: "0",
  };
}

export interface PiRunnerOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder; the CLI runs there. */
  root: string;
  /** The server's environment; only `buildPiEnv` of it reaches the CLI. */
  env: Readonly<Record<string, string | undefined>>;
  /** Where a stored API key is read from, for a turn in api mode, and the keys that must never be shown. */
  credentials?: CredentialReaderPort;
  /** Makes the id of a new conversation; Pi creates the session under it. */
  newSessionId?: () => string;
  /** Receives every raw line of the CLI's output (keys masked). */
  /** Runs collaborators' turns inside bubblewrap. Without it a collaborator's turn is refused. */
  sandbox?: AgentSandbox;
  tap?: (line: string) => void;
}

/** A tool the agent must not use: outside the allowlist, or a call the stream was unclear about. */
function violation(outcome: PiMapOutcome): string | null {
  const tool = outcome.tool;
  if (tool === undefined) return null;
  if (!tool.name || !PI_ALLOWED_TOOLS.includes(tool.name as PiAllowedTool)) {
    return `Pi used a tool that Caztor does not allow (${tool.name || "unnamed"}), so the turn was stopped.`;
  }
  return null;
}

const SECRET_ENV_NAME = /(^|_)(api_?key|key|token|secret|password|credentials?)$/i;
/** The mask replaces plain text everywhere, so a short value or a path, which ordinary output also holds, must not count as a key. */
const MIN_ENV_SECRET_LENGTH = 16;
const looksLikeKey = (value: string) => value.length >= MIN_ENV_SECRET_LENGTH && !value.startsWith("/") && !/\s/.test(value);

/** Every key Pi must not show in the chat: the server's own and every stored one, also those Pi finds by itself. */
async function knownSecrets(options: PiRunnerOptions, own?: CredentialReaderPort): Promise<string[]> {
  const fromEnv = Object.entries(options.env).flatMap(([name, value]) => (value !== undefined && SECRET_ENV_NAME.test(name) && looksLikeKey(value) ? [value] : []));
  const slots = PROVIDER_IDS.flatMap((provider) => providerSlots(provider));
  // A collaborator's turn masks their own keys as well as the host's, which it never receives either.
  const readers = [options.credentials, own].filter((reader): reader is CredentialReaderPort => reader !== undefined);
  const stored = await Promise.all(readers.flatMap((reader) => slots.map((slot) => reader.read(slot).catch(() => null))));
  return [...fromEnv, ...stored.flatMap((found) => (found?.ok === true && found.value !== null ? [found.value] : []))];
}

/**
 * The Pi adapter: starts `pi -p --mode json` without a shell, with everything Pi would load from the project switched
 * off, only the file tools, Caztor's system prompt from a file in `.caztor/`, and the prompt after `--`.
 */
export function createPiRunner(options: PiRunnerOptions): AgentRunnerPort {
  const { fs, spawner, clock, root } = options;
  const detectEnv = buildPiEnv(options.env, root);
  const newSessionId = options.newSessionId ?? (() => crypto.randomUUID());
  let binary: string | null = null;
  let current: ChildHandle | null = null;
  let listed: { at: number; models: string[] | null } | null = null;

  async function locate(): Promise<string | null> {
    binary ??= await resolveBinary(fs, "pi", options.env["PATH"]);
    return binary;
  }

  /** Makes a private folder below `.caztor` for Pi. Null when it is ready, else why it is not. */
  async function prepareFolder(relative: string, what: string): Promise<string | null> {
    const base = trimmed(root);
    for (const folder of [`${base}/.caztor`, `${base}/${relative}`]) {
      try {
        if ((await fs.lstat(folder)).isSymbolicLink()) return `${folder.slice(base.length + 1)} is a symbolic link, so the Pi turn was not started. Remove the link and try again.`;
      } catch (error) {
        if ((error as { code?: string }).code !== "ENOENT") return `The Pi ${what} folder could not be checked: ${error instanceof Error ? error.message : String(error)}`;
      }
    }
    try {
      await fs.mkdir(`${base}/${relative}`, { recursive: true });
      await fs.chmod(`${base}/${relative}`, 0o700);
    } catch (error) {
      return `The Pi ${what} folder could not be prepared: ${error instanceof Error ? error.message : String(error)}`;
    }
    return null;
  }

  /** The model to pass (null for Pi's default), or the events that end the turn at once. */
  function modelOf(req: TurnRequest): { model: string | null } | { stop: AgentEvent[] } {
    const raw = req.model?.trim() ?? "";
    if (raw === "") return { model: null };
    if (raw.startsWith("-")) return { stop: failed("model_unavailable", "The model name cannot start with a dash.") };
    const parsed = parseModel(raw);
    if (!parsed.ok) return { stop: failed("model_unavailable", parsed.message) };
    return { model: parsed.value };
  }

  async function* run(req: TurnRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    if (signal.aborted) {
      yield { type: "done", reason: "cancelled" };
      return;
    }
    const chosen = modelOf(req);
    if ("stop" in chosen) {
      yield* chosen.stop;
      return;
    }
    // In api mode the vendor in the model name decides which key is used; without a model there is no vendor.
    let slot = "";
    if (req.authMode === "api") {
      const slotted = credentialSlot("pi", chosen.model);
      if (!slotted.ok) {
        yield* failed(slotted.error.code === "vendor_required" ? "model_required" : "model_unavailable", slotted.error.message);
        return;
      }
      slot = slotted.value;
    }
    const file = await locate();
    if (file === null) {
      yield* failed("not_installed", "pi was not found on the PATH.");
      return;
    }

    // Pi reads `--system-prompt` as text when no file is at the path, so a missing or linked file must stop the turn.
    const promptFile = `${trimmed(root)}/${AGENT_TARGETS.pi}`;
    const regular = await fs.lstat(promptFile).then((stats) => stats.isFile() && !stats.isSymbolicLink(), () => false);
    if (!regular) {
      yield* failed("isolation_failed", "Caztor did not start Pi: its system prompt file is missing or is not a plain file.");
      return;
    }
    const sessionsRefused = await prepareFolder(PI_SESSIONS_DIR, "sessions");
    if (sessionsRefused !== null) {
      yield* failed("isolation_failed", sessionsRefused);
      return;
    }

    let env: Record<string, string>;
    if (req.authMode === "api") {
      const vendor = slot.slice("pi:".length);
      const agentRefused = await prepareFolder(PI_API_AGENT_DIR, "agent");
      if (agentRefused !== null) {
        yield* failed("isolation_failed", agentRefused);
        return;
      }
      const stored = await readStoredKey(req.credentials ?? options.credentials, slot, `Pi (${vendor})`);
      if ("stop" in stored) {
        yield* stored.stop;
        return;
      }
      env = buildPiEnv(req.env ?? options.env, root, { variable: PI_VENDOR_ENV[vendor as keyof typeof PI_VENDOR_ENV], key: stored.key });
    } else {
      env = buildPiEnv(req.env ?? options.env, root);
    }


    const sessionId = req.sessionId !== null && SESSION_ID_REGEX.test(req.sessionId) ? req.sessionId : newSessionId();
    const args = [
      "-p", "--mode", "json",
      ...ISOLATION_FLAGS,
      "--tools", PI_ALLOWED_TOOLS.join(","),
      "-xt", "mcp__*",
      "--system-prompt", promptFile,
      // An empty addition keeps Pi from appending an APPEND_SYSTEM.md of its own folder.
      "--append-system-prompt", "",
      "--session-id", sessionId,
      "--session-dir", `${trimmed(root)}/${PI_SESSIONS_DIR}`,
    ];
    if (chosen.model !== null) args.push("--model", chosen.model);
    // The prompt goes on stdin: Pi reads a positional argument that starts with `@` as a file to include, even after `--`.

    const placed = await placeTurn(options.sandbox, req, { file, args, cwd: root, env, stdin: req.prompt });
    if ("stop" in placed) {
      yield* placed.stop;
      return;
    }
    yield* drive({
      spawner,
      clock,
      spec: placed.spec,
      signal,
      secrets: await knownSecrets(options, req.credentials),
      mapper: createPiMapper({ root }),
      notStarted: "pi could not be started. Is it installed?",
      tap: options.tap,
      check: violation,
      dropEventsOnViolation: true,
      onChild: (child) => void (current = child),
    });
  }

  /** The `provider/model` names `pi --list-models` prints: only the models someone is signed in to. Null when it cannot be read. */
  async function listModels(file: string, cwd: string): Promise<string[] | null> {
    const result = await probe({ spawner, clock, file, args: ["--offline", "-na", "-ne", "--no-mcp", "--list-models"], cwd, env: detectEnv, label: "pi", limitMs: MODELS_LIMIT_MS });
    if (!result.ok) return null;
    const models: string[] = [];
    for (const [index, raw] of result.output.split("\n").entries()) {
      const row = MODEL_ROW.exec(raw.trim());
      if (index === 0 || row === null || row[1] === "provider") continue;
      models.push(`${row[1]}/${row[2]}`);
    }
    return [...new Set(models)].sort();
  }

  return {
    provider: "pi",
    isolation: PI_ISOLATION_TIER,
    runTurn: (req, signal) => run(req, signal),
    forceStop() {
      current?.killGroup("SIGKILL");
    },
    async detect(): Promise<ProviderStatus> {
      binary = null;
      const unavailable = (unavailableReason: string): ProviderStatus => ({ provider: "pi", installed: false, unavailableReason, requiresModel: false });
      const file = await locate();
      if (file === null) return unavailable("pi was not found on the PATH.");
      // Detection runs in a fresh private folder, never in the project, and the folder is removed afterwards.
      const scratch = await fs.mkdtemp(`${(options.env["TMPDIR"] ?? "/tmp").replace(/\/+$/, "")}/caztor-pi-`);
      try {
        const probed = await probe({ spawner, clock, file, args: ["--version"], cwd: scratch, env: detectEnv, label: "pi" });
        if (!probed.ok) return unavailable(probed.reason);
        const version = versionOf(probed.output);
        if (version === null) return unavailable(`pi answered --version with output that was not recognised: "${probed.output.trim().split("\n")[0]?.slice(0, 100) ?? ""}"`);
        if (listed === null || clock.now() - listed.at >= MODELS_CACHE_MS) listed = { at: clock.now(), models: await listModels(file, scratch) };
        const { models } = listed;
        return {
          provider: "pi",
          installed: true,
          version: version.join("."),
          requiresModel: false,
          ...(models === null || models.length === 0 ? {} : { models }),
          ...(isOlder(version, PI_TESTED_VERSION) ? { versionWarning: `Caztor was tested with pi ${PI_TESTED_VERSION} or newer; this version may behave differently.` } : {}),
        };
      } finally {
        await fs.rm(scratch, { recursive: true, force: true }).catch(() => {});
      }
    },
  };
}
