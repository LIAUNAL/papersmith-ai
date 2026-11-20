import type { AgentEvent, AgentRunnerPort, CredentialReaderPort, ProviderStatus, TurnRequest } from "@caztor/core";
import { credentialSlot, parseModel, type OPENCODE_API_VENDORS } from "@caztor/core";
import { AGENT_NAME, parseOpencodePermissions } from "../../agent-definition.ts";
import type { ChildHandle, Clock, FileSystem, FsDirent, ProcessSpawner } from "../../infra.ts";
import { placeTurn, type AgentSandbox } from "../../agent-sandbox.ts";
import { drive, failed, probe, STOP_ESCALATION_MS } from "../drive.ts";
import { configRefusal, runsSomething, scanOpencodeProjectConfig } from "../project-config.ts";
import { resolveBinary } from "../resolve-binary.ts";
import { readStoredKey } from "../stored-key.ts";
import { isOlder, versionOf } from "../version.ts";
import { createOpencodeMapper, type OpencodeMapOutcome } from "./mapper.ts";

export { STOP_ESCALATION_MS };

export type OpencodeIsolationTier = "I1" | "I2";
/**
 * The tier is a constant chosen after verifying the flags against the installed CLI, not probed at runtime.
 * I1: the configuration folder is empty (no user agents, plugins, MCP servers, instruction files or custom providers),
 * plugins are off, and the other global sources are switched off. The login lives elsewhere and stays usable.
 */
export const OPENCODE_ISOLATION_TIER: OpencodeIsolationTier = "I1";

/** The CLI version the flags and the stream were checked against; an older one gets a warning. */
export const OPENCODE_TESTED_VERSION = "1.19.0";

/**
 * The tools the agent may use: reading, searching and editing files, and the planning list, which touches nothing.
 * `invalid` is what the CLI reports when the model names a tool that does not exist; it does nothing.
 */
export const OPENCODE_ALLOWED_TOOLS: readonly string[] = ["read", "edit", "write", "apply_patch", "multiedit", "patch", "glob", "grep", "list", "todowrite", "todoread", "invalid"];
/** Tools opencode has itself. When the agent definition denies one and the model tries it, the call fails; that is not a breach. */
const BUILTIN_TOOLS: readonly string[] = ["bash", "webfetch", "websearch", "codesearch", "task", "skill", "question", "lsp", "batch", "external_directory"];
/** What the agent definition must deny. A key the file does not mention is allowed by opencode. */
const REQUIRED_DENIES: readonly string[] = ["bash", "webfetch", "external_directory"];

const MODEL_SHAPE = /^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._:-]*(?:\/[A-Za-z0-9][A-Za-z0-9._:-]*)*$/;
const MODEL_LINE = /^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._:\/-]*$/;
const SESSION_ID = /^ses_[A-Za-z0-9]{6,100}$/;

/** Variables the CLI inherits: where to find itself and its login, the locale, the network and certificates. */
export const OPENCODE_ENV_NAMES: readonly string[] = [
  "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
];
/**
 * The variable each model vendor's key goes in. A vendor not listed has no key route: opencode must be signed in through
 * `opencode providers login` for it.
 */
export const OPENCODE_VENDOR_ENV: Readonly<Record<(typeof OPENCODE_API_VENDORS)[number], string>> = {
  openai: "OPENAI_API_KEY",
  anthropic: "ANTHROPIC_API_KEY",
  google: "GOOGLE_GENERATIVE_AI_API_KEY",
  openrouter: "OPENROUTER_API_KEY",
  groq: "GROQ_API_KEY",
  xai: "XAI_API_KEY",
  mistral: "MISTRAL_API_KEY",
  deepseek: "DEEPSEEK_API_KEY",
  opencode: "OPENCODE_API_KEY",
};

const pick = (parent: Readonly<Record<string, string | undefined>>, names: readonly string[]): Record<string, string> => {
  const env: Record<string, string> = {};
  for (const name of names) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  return env;
};

/** Where api mode keeps the CLI's data (its own login file), apart from the user's, so a saved login cannot win over the key. */
export const OPENCODE_API_DATA_DIR = ".caztor/opencode-data-api";

const trimmed = (root: string) => root.replace(/\/+$/, "");

/**
 * The environment of a turn: the allowed names of the server's, an empty configuration folder inside the project, and the
 * global sources off. No provider key or base URL of the server's passes in either mode, so an exported key cannot override
 * the CLI's login. In api mode `api` adds only that vendor's variable and moves the data folder out of the user's.
 */
export function buildOpencodeEnv(parent: Readonly<Record<string, string | undefined>>, root: string, api?: { variable: string; key: string }): Record<string, string> {
  return {
    ...pick(parent, OPENCODE_ENV_NAMES),
    ...(api === undefined ? {} : { [api.variable]: api.key, XDG_DATA_HOME: `${trimmed(root)}/${OPENCODE_API_DATA_DIR}` }),
    XDG_CONFIG_HOME: `${trimmed(root)}/.caztor/opencode-xdg`,
    OPENCODE_DISABLE_CLAUDE_CODE: "1",
    OPENCODE_DISABLE_EXTERNAL_SKILLS: "1",
    OPENCODE_DISABLE_AUTOUPDATE: "1",
    NO_COLOR: "1",
  };
}

export interface OpencodeRunnerOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder; the CLI runs there. */
  root: string;
  /** The server's environment; only `buildOpencodeEnv` of it reaches the CLI. */
  env: Readonly<Record<string, string | undefined>>;
  /** Where a stored API key is read from, only for a turn in api mode. */
  credentials?: CredentialReaderPort;
  /** Whether the user trusted the project's own opencode configuration, as it is now (its fingerprint). Without it nothing is trusted. */
  projectConfigConfirmed?: (fingerprint: string) => Promise<boolean>;
  /** Runs collaborators' turns inside bubblewrap. Without it a collaborator's turn is refused. */
  sandbox?: AgentSandbox;
  /** Receives every raw line of the CLI's output; for diagnostics and the opt-in real-CLI test. */
  tap?: (line: string) => void;
}

/** What opencode itself writes in its configuration folder: the folder, its `.gitignore`, its plugin package and a config file. */
const OWN_XDG_ENTRIES = new Set([".gitignore", "node_modules", "opencode.json", "opencode.jsonc"]);

/**
 * Whether the configuration folder holds only what opencode writes there itself: `opencode/` with a config that only
 * changes the display, its `.gitignore` and its `node_modules`. A missing folder counts as clean.
 */
async function opencodeOwnConfigIn(fs: FileSystem, xdg: string): Promise<boolean> {
  let top: FsDirent[];
  try {
    top = await fs.readdir(xdg);
  } catch {
    return true;
  }
  if (top.some((entry) => entry.name !== "opencode" || !entry.isDirectory())) return top.length === 0;
  if (top.length === 0) return true;
  const inner = await fs.readdir(`${xdg}/opencode`).catch(() => null);
  if (inner === null) return false;
  for (const entry of inner) {
    if (!OWN_XDG_ENTRIES.has(entry.name) || entry.isSymbolicLink()) return false;
    if (entry.name === "node_modules" ? !entry.isDirectory() : !entry.isFile()) return false;
    if (entry.name.startsWith("opencode.json") && runsSomething(await fs.readFile(`${xdg}/opencode/${entry.name}`).catch(() => new Uint8Array([0x7b])))) return false;
  }
  return true;
}

/** Listing the models takes seconds and a turn detects first, so the list is kept this long. */
const MODELS_CACHE_MS = 30_000;
/** The listing starts the CLI twice at once, which takes longer on a busy machine than `--version` does. */
const MODELS_LIMIT_MS = 15_000;

/** A tool the agent must not have used: a finished call outside the allowed set, or a name that is not the CLI's own. */
function violation(outcome: OpencodeMapOutcome): string | null {
  const tool = outcome.tool;
  if (tool === undefined || OPENCODE_ALLOWED_TOOLS.includes(tool.name)) return null;
  if (tool.status === "error" && BUILTIN_TOOLS.includes(tool.name)) return null;
  return `opencode used a tool that Caztor does not allow (${tool.name}), so the turn was stopped.`;
}

/**
 * The opencode adapter: starts `opencode run --format json` without a shell, with the prompt on stdin, an environment
 * that points the CLI's configuration at an empty folder, and turns its stream into normalized events. The model is
 * required: the CLI's default (a free model) cannot be used from outside opencode.
 */
export function createOpencodeRunner(options: OpencodeRunnerOptions): AgentRunnerPort {
  const { fs, spawner, clock, root } = options;
  const detectEnv = buildOpencodeEnv(options.env, root);
  let binary: string | null = null;
  let current: ChildHandle | null = null;
  let listed: { at: number; models: string[] | null } | null = null;

  async function locate(): Promise<string | null> {
    binary ??= await resolveBinary(fs, "opencode", options.env["PATH"]);
    return binary;
  }

  /**
   * Makes a private folder the CLI is pointed at, below `.caztor`: created here, readable only by this user. Null when it
   * is ready, else why it is not (a symbolic link in `.caztor` could send the CLI's files outside the project).
   */
  const opencodeOwnConfig = (xdg: string) => opencodeOwnConfigIn(fs, xdg);

  async function prepareHome(name: string, what: string, empty = false): Promise<string | null> {
    const base = root.replace(/\/+$/, "");
    for (const folder of [`${base}/.caztor`, `${base}/.caztor/${name}`]) {
      try {
        if ((await fs.lstat(folder)).isSymbolicLink()) {
          return `${folder.slice(base.length + 1)} is a symbolic link, so the opencode turn was not started. Remove the link and try again.`;
        }
      } catch (error) {
        if ((error as { code?: string }).code !== "ENOENT") return `The opencode ${what} folder could not be checked: ${error instanceof Error ? error.message : String(error)}`;
      }
    }
    try {
      // The configuration folder holds only what opencode writes itself (a schema-only config and its plugin package).
      // Anything else was planted (an MCP server, a plugin), so the folder is emptied before the turn. `rm` removes
      // links inside without following them.
      if (empty && !(await opencodeOwnConfig(`${base}/.caztor/${name}`))) await fs.rm(`${base}/.caztor/${name}`, { recursive: true, force: true });
      await fs.mkdir(`${base}/.caztor/${name}`, { recursive: true });
      await fs.chmod(`${base}/.caztor/${name}`, 0o700);
    } catch (error) {
      return `The opencode ${what} folder could not be prepared: ${error instanceof Error ? error.message : String(error)}`;
    }
    return null;
  }

  /** A warning when the definition file lets the agent do more than Caztor intends; null when it denies all of it or is not there. */
  async function definitionWarning(): Promise<AgentEvent | null> {
    let text: string;
    try {
      text = new TextDecoder().decode(await fs.readFile(`${root}/.opencode/agents/${AGENT_NAME}.md`));
    } catch {
      return null;
    }
    const permissions = parseOpencodePermissions(text);
    if (permissions === null) {
      return { type: "notice", level: "warning", message: "The agent definition cannot be read, so Caztor cannot tell what opencode may do. Restore Caztor's definition to turn this off.", action: "replace_definition" };
    }
    const open = REQUIRED_DENIES.filter((key) => permissions[key] !== "deny");
    if (open.length === 0) return null;
    return { type: "notice", level: "warning", message: `The agent definition no longer denies ${open.join(", ")}, so opencode could use it. Restore Caztor's definition to turn this off.`, action: "replace_definition" };
  }

  /** The model to pass, or the events that end the turn at once. */
  function modelOf(req: TurnRequest): { model: string } | { stop: AgentEvent[] } {
    const raw = req.model?.trim() ?? "";
    if (raw === "") return { stop: failed("model_required", "Choose a model for opencode before sending a message. Write it as provider/model.") };
    if (raw.startsWith("-")) {
      const parsed = parseModel(raw);
      return { stop: failed("model_unavailable", parsed.ok ? "The model name cannot start with a dash." : parsed.message) };
    }
    if (!MODEL_SHAPE.test(raw)) return { stop: failed("model_unavailable", "opencode needs the model as provider/model, for example openai/gpt-5.5.") };
    return { model: raw };
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
    // In api mode the vendor in the model name decides which key is used; a vendor without a variable is refused before anything is read.
    let slot = "";
    let vendor = "";
    if (req.authMode === "api") {
      const slotted = credentialSlot("opencode", chosen.model);
      if (!slotted.ok) {
        yield* failed("model_unavailable", slotted.error.message);
        return;
      }
      slot = slotted.value;
      vendor = slot.slice("opencode:".length);
    }
    const file = await locate();
    if (file === null) {
      yield* failed("not_installed", "opencode was not found on the PATH.");
      return;
    }
    const found = await scanOpencodeProjectConfig(fs, root);
    if (found !== null && !(await (options.projectConfigConfirmed?.(found.fingerprint) ?? Promise.resolve(false)))) {
      yield* failed("isolation_failed", configRefusal("opencode", found.files));
      return;
    }
    const refused = await prepareHome("opencode-xdg", "configuration", true);
    if (refused !== null) {
      yield* failed("isolation_failed", refused);
      return;
    }
    let env: Record<string, string>;
    let secrets: string[] = [];
    if (req.authMode === "api") {
      const variable = OPENCODE_VENDOR_ENV[vendor as keyof typeof OPENCODE_VENDOR_ENV];
      const dataRefused = await prepareHome("opencode-data-api", "data");
      if (dataRefused !== null) {
        yield* failed("isolation_failed", dataRefused);
        return;
      }
      const stored = await readStoredKey(req.credentials ?? options.credentials, slot, `opencode (${vendor})`);
      if ("stop" in stored) {
        yield* stored.stop;
        return;
      }
      env = buildOpencodeEnv(req.env ?? options.env, root, { variable, key: stored.key });
      secrets = [stored.key];
    } else {
      env = buildOpencodeEnv(req.env ?? options.env, root);
    }
    const warning = await definitionWarning();
    if (warning !== null) yield warning;

    const args = ["run", "--format", "json", "--agent", AGENT_NAME, "--pure", "-m", chosen.model, "--dir", root];
    if (req.sessionId !== null && SESSION_ID.test(req.sessionId)) args.push("-s", req.sessionId);
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
      mapper: createOpencodeMapper({ root }),
      notStarted: "opencode could not be started. Is it installed?",
      tap: options.tap,
      secrets,
      check: violation,
      dropEventsOnViolation: true,
      onChild: (child) => void (current = child),
    });
  }

  /** The model names `opencode --pure models` prints, or null when it cannot be read. */
  async function listModels(file: string, cwd: string, listEnv: Record<string, string>): Promise<string[] | null> {
    const result = await probe({ spawner, clock, file, args: ["--pure", "models"], cwd, env: listEnv, label: "opencode", limitMs: MODELS_LIMIT_MS });
    if (!result.ok) return null;
    return [...new Set(result.output.split("\n").map((line) => line.trim()).filter((line) => MODEL_LINE.test(line)))].sort();
  }

  return {
    provider: "opencode",
    isolation: OPENCODE_ISOLATION_TIER,
    runTurn: (req, signal) => run(req, signal),
    forceStop() {
      current?.killGroup("SIGKILL");
    },
    projectConfig: () => scanOpencodeProjectConfig(fs, root),
    async detect(): Promise<ProviderStatus> {
      binary = null;
      const unavailable = (unavailableReason: string): ProviderStatus => ({ provider: "opencode", installed: false, unavailableReason, requiresModel: false });
      const file = await locate();
      if (file === null) return unavailable("opencode was not found on the PATH.");
      // Detection must never run where the project's own files could be loaded (its MCP servers, plugins and tools), so
      // the CLI runs in a fresh private folder that is also its empty configuration home, and is removed afterwards.
      const scratch = await fs.mkdtemp(`${(options.env["TMPDIR"] ?? "/tmp").replace(/\/+$/, "")}/caztor-opencode-`);
      try {
        const bare = { ...detectEnv, XDG_CONFIG_HOME: scratch };
        const probed = await probe({ spawner, clock, file, args: ["--version"], cwd: scratch, env: bare, label: "opencode" });
        if (!probed.ok) return unavailable(probed.reason);
        const version = versionOf(probed.output);
        if (version === null) return unavailable(`opencode answered --version with output that was not recognised: "${probed.output.trim().split("\n")[0]?.slice(0, 100) ?? ""}"`);

        if (listed === null || clock.now() - listed.at >= MODELS_CACHE_MS) {
          listed = { at: clock.now(), models: await listModels(file, scratch, bare) };
        }
        const { models } = listed;
        return {
          provider: "opencode",
          installed: true,
          version: version.join("."),
          requiresModel: true,
          ...(models === null || models.length === 0 ? {} : { models }),
          ...(isOlder(version, OPENCODE_TESTED_VERSION) ? { versionWarning: `Caztor was tested with opencode ${OPENCODE_TESTED_VERSION} or newer; this version may behave differently.` } : {}),
        };
      } finally {
        await fs.rm(scratch, { recursive: true, force: true }).catch(() => {});
      }
    },
  };
}
