import { parseModel } from "@caztor/core";
import type { AgentEvent, AgentRunnerPort, AuthMode, CredentialReaderPort, ProviderStatus, TurnRequest } from "@caztor/core";
import { AGENT_NAME } from "../../agent-definition.ts";
import type { ChildHandle, Clock, FileSystem, ProcessSpawner } from "../../infra.ts";
import { placeTurn, type AgentSandbox } from "../../agent-sandbox.ts";
import { drive, failed, probe, STOP_ESCALATION_MS } from "../drive.ts";
import { isOlder, versionOf } from "../version.ts";
import { configRefusal, scanClaudeProjectConfig } from "../project-config.ts";
import { resolveBinary } from "../resolve-binary.ts";
import { readStoredKey } from "../stored-key.ts";
import { createClaudeMapper } from "./mapper.ts";
import type { ClaudeInit } from "./mapper.ts";

/** The tools the agent may have: reading and editing files, nothing that runs a command or reaches the network. */
export const ALLOWED_TOOLS: readonly string[] = ["Read", "Edit", "Write", "Glob", "Grep"];

export type ClaudeIsolationTier = "I1" | "I2" | "I3";
/**
 * The tier is a constant chosen after verifying the flags against the installed CLI, not probed at runtime.
 * I1: no on-disk setting source, no MCP server, no slash commands or skills, and the agent passed inline.
 */
export const CLAUDE_ISOLATION_TIER: ClaudeIsolationTier = "I1";

/** The CLI version the flags and the stream were checked against; an older one gets a warning. */
export const CLAUDE_TESTED_VERSION = "2.1.296";

export { STOP_ESCALATION_MS };
const MAX_AGENT_JSON_CHARS = 100_000;
const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,99}$/;

/** Variables the CLI inherits: where to find itself and its credentials, the locale, the network and certificates. */
export const CLAUDE_ENV_NAMES: readonly string[] = [
  "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
];
/**
 * Variables that point the CLI at the user's own login. The design lists the whole `ANTHROPIC_` and `CLAUDE_` prefixes,
 * but a server started from inside a Claude Code session also inherits that session's own variables
 * (`CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, ...), which must not reach a new session. A turn on the subscription login
 * needs none of them (observed: only PATH, HOME and the locale), so only these are passed, and only in account mode.
 */
export const CLAUDE_ACCOUNT_NAMES: readonly string[] = ["CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"];

/**
 * The environment of a turn. Account mode passes the user's login and never an Anthropic key, token or base URL, even when
 * the server was started with one exported, so a subscription is not silently overridden. Api mode passes the stored key
 * and neither the OAuth token nor the server's Anthropic variables.
 */
/**
 * Claude Code has no command that lists its models. The list is the full names of the current and recent models, as
 * Claude Code 2.1.317 knows them. A model the account cannot use fails its turn as an unavailable model; any other name
 * can still be set with `/model <name>`.
 */
export const CLAUDE_MODELS = [
  "claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5",
  "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5",
] as const;

/** The model a turn uses when the user chose none, so it does not depend on the account's own default. */
export const CLAUDE_DEFAULT_MODEL = "claude-sonnet-5-5";

export function buildClaudeEnv(parent: Readonly<Record<string, string | undefined>>, mode: AuthMode = "account", key?: string): Record<string, string> {
  const env: Record<string, string> = {};
  const names = mode === "api" ? [...CLAUDE_ENV_NAMES, "CLAUDE_CONFIG_DIR"] : [...CLAUDE_ENV_NAMES, ...CLAUDE_ACCOUNT_NAMES];
  for (const name of names) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  if (mode === "api" && key !== undefined) env["ANTHROPIC_API_KEY"] = key;
  // The user's own memory for this folder from earlier interactive sessions is not part of the isolated agent.
  env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1";
  env["NO_COLOR"] = "1";
  return env;
}

export interface ClaudeRunnerOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder; the CLI runs there. */
  root: string;
  /** The server's environment; only `buildClaudeEnv` of it reaches the CLI. */
  env: Readonly<Record<string, string | undefined>>;
  /** Where a stored API key is read from, only for a turn in api mode. */
  credentials?: CredentialReaderPort;
  tier?: ClaudeIsolationTier;
  /** Whether the user trusted the project's own Claude Code configuration, as it is now (its fingerprint). Without it nothing is trusted. */
  projectConfigConfirmed?: (fingerprint: string) => Promise<boolean>;
  /** Runs collaborators' turns inside bubblewrap. Without it a collaborator's turn is refused. */
  sandbox?: AgentSandbox;
  /** Receives every raw line of the CLI's output; for diagnostics and the opt-in real-CLI test. */
  tap?: (line: string) => void;
}

const BASE_ARGS = ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--permission-mode", "acceptEdits"];

/**
 * The Claude Code adapter: starts `claude -p` without a shell, with the prompt on stdin and only an allowlisted
 * environment, and turns its stream into normalized events. The agent runs without the user's hooks, MCP servers and
 * instruction files; what `system/init` reports is checked, and a violation ends the turn before the agent acts.
 */
export function createClaudeRunner(options: ClaudeRunnerOptions): AgentRunnerPort {
  const { fs, spawner, clock, root } = options;
  const tier = options.tier ?? CLAUDE_ISOLATION_TIER;
  const detectEnv = buildClaudeEnv(options.env);
  let binary: string | null = null;
  let current: ChildHandle | null = null;

  async function locate(): Promise<string | null> {
    binary ??= await resolveBinary(fs, "claude", options.env["PATH"]);
    return binary;
  }

  /** The argument list and the notices that go before the turn, or the events that end it at once. */
  async function prepare(req: TurnRequest): Promise<{ args: string[]; notices: AgentEvent[] } | { stop: AgentEvent[] }> {
    const model = parseModel(req.model);
    if (!model.ok) return { stop: failed("model_unavailable", model.message) };

    const notices: AgentEvent[] = [];
    const tools = req.agent.tools.filter((tool) => ALLOWED_TOOLS.includes(tool));
    const left = req.agent.tools.filter((tool) => !ALLOWED_TOOLS.includes(tool));
    if (left.length > 0) {
      notices.push({ type: "notice", level: "warning", message: `The agent definition lists tools other than file reading and editing (${left.join(", ")}). Caztor left them out.` });
    }
    if (tools.length === 0) return { stop: failed("isolation_failed", "The agent definition has no file reading or editing tool, so the turn was not started.") };

    // The flags below keep the project's settings and MCP servers out under tier I1, but `--help` documents that and
    // only a model call would show it, so the gate applies to every tier.
    const found = await scanClaudeProjectConfig(fs, root);
    if (found !== null && !(await (options.projectConfigConfirmed?.(found.fingerprint) ?? Promise.resolve(false)))) {
      return { stop: failed("isolation_failed", configRefusal("Claude Code", found.files)) };
    }

    const args = [...BASE_ARGS];
    if (tier === "I1") {
      const agents = JSON.stringify({ [AGENT_NAME]: { description: req.agent.description, prompt: req.agent.prompt, tools } });
      if (agents.length > MAX_AGENT_JSON_CHARS) return { stop: failed("provider_error", "The agent definition is too large to pass to Claude Code.") };
      args.push("--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands", "--tools", tools.join(","), "--agents", agents, "--agent", AGENT_NAME);
    } else if (tier === "I2") {
      args.push("--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands", "--agent", AGENT_NAME);
    } else {
      args.push("--agent", AGENT_NAME);
      notices.push({
        type: "notice",
        level: "warning",
        message: "Isolation from your Claude Code configuration is unavailable here, so your hooks and servers may run and a turn costs more.",
      });
    }
    args.push("--model", model.value ?? CLAUDE_DEFAULT_MODEL);
    if (req.sessionId !== null && SESSION_ID.test(req.sessionId)) args.push("--resume", req.sessionId);
    return { args, notices };
  }

  function isolationProblem(init: ClaudeInit): string | null {
    const extra = init.tools.filter((tool) => !ALLOWED_TOOLS.includes(tool));
    if (extra.length > 0) return `Claude Code started with tools that Caztor does not allow (${extra.join(", ")}), so the turn was stopped before the agent acted.`;
    if (tier !== "I3" && init.mcpServers.length > 0) {
      return `Claude Code connected MCP servers (${init.mcpServers.map((server) => server.name).join(", ")}), so the turn was stopped before the agent acted.`;
    }
    return null;
  }

  async function* run(req: TurnRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    if (signal.aborted) {
      yield { type: "done", reason: "cancelled" };
      return;
    }
    const prepared = await prepare(req);
    if ("stop" in prepared) {
      yield* prepared.stop;
      return;
    }
    const file = await locate();
    if (file === null) {
      yield* failed("not_installed", "Claude Code was not found on the PATH.");
      return;
    }
    let env: Record<string, string>;
    let secrets: string[] = [];
    if (req.authMode === "api") {
      const stored = await readStoredKey(req.credentials ?? options.credentials, "claude", "Claude");
      if ("stop" in stored) {
        yield* stored.stop;
        return;
      }
      env = buildClaudeEnv(req.env ?? options.env, "api", stored.key);
      secrets = [stored.key];
    } else {
      env = buildClaudeEnv(req.env ?? options.env);
    }
    yield* prepared.notices;

    const placed = await placeTurn(options.sandbox, req, { file, args: prepared.args, cwd: root, env, stdin: req.prompt });
    if ("stop" in placed) {
      yield* placed.stop;
      return;
    }
    yield* drive({
      spawner,
      clock,
      spec: placed.spec,
      signal,
      mapper: createClaudeMapper({ root }),
      notStarted: "Claude Code could not be started. Is it installed?",
      tap: options.tap,
      secrets,
      check: (outcome) => (outcome.init === undefined ? null : isolationProblem(outcome.init)),
      onChild: (child) => void (current = child),
    });
  }

  return {
    provider: "claude",
    isolation: tier,
    projectConfig: () => scanClaudeProjectConfig(fs, root),
    runTurn: (req, signal) => run(req, signal),
    forceStop() {
      current?.killGroup("SIGKILL");
    },
    async detect(): Promise<ProviderStatus> {
      binary = null;
      const unavailable = (unavailableReason: string): ProviderStatus => ({ provider: "claude", installed: false, unavailableReason, requiresModel: false });
      const file = await locate();
      if (file === null) return unavailable("Claude Code was not found on the PATH.");
      const probed = await probe({ spawner, clock, file, args: ["--version"], cwd: root, env: detectEnv, label: "Claude Code" });
      if (!probed.ok) return unavailable(probed.reason);
      const version = versionOf(probed.output);
      if (version === null) return unavailable(`Claude Code answered --version with output that was not recognised: "${probed.output.trim().split("\n")[0]?.slice(0, 100) ?? ""}"`);
      return {
        provider: "claude",
        installed: true,
        version: version.join("."),
        requiresModel: false,
        models: [...CLAUDE_MODELS],
        defaultModel: CLAUDE_DEFAULT_MODEL,
        ...(isOlder(version, CLAUDE_TESTED_VERSION) ? { versionWarning: `Caztor was tested with Claude Code ${CLAUDE_TESTED_VERSION} or newer; this version may behave differently.` } : {}),
      };
    },
  };
}
