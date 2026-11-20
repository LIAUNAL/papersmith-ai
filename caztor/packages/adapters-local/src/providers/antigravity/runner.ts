import type { AgentEvent, AgentRunnerPort, CredentialReaderPort, ProviderStatus, TurnRequest } from "@caztor/core";
import { parseModel, PROVIDER_IDS, providerSlots } from "@caztor/core";
import type { ChildHandle, Clock, FileSystem, ProcessSpawner } from "../../infra.ts";
import { placeTurn, type AgentSandbox } from "../../agent-sandbox.ts";
import { drive, failed, probe, STOP_ESCALATION_MS } from "../drive.ts";
import { configRefusal, scanAntigravityProjectConfig, antigravityDefinitionProblem } from "../project-config.ts";
import { resolveBinary } from "../resolve-binary.ts";
import { isOlder, versionOf } from "../version.ts";
import {
  ANTIGRAVITY_ALLOWED_TOOLS,
  ANTIGRAVITY_ISOLATION_TIER,
  ANTIGRAVITY_LOGIN_HINT,
  ANTIGRAVITY_TESTED_VERSION,
  createAntigravityMapper,
  type AntigravityAllowedTool,
  type AntigravityMapOutcome,
} from "./mapper.ts";

export {
  ANTIGRAVITY_ALLOWED_TOOLS,
  ANTIGRAVITY_ISOLATION_TIER,
  ANTIGRAVITY_LOGIN_HINT,
  ANTIGRAVITY_TESTED_VERSION,
  STOP_ESCALATION_MS,
};

export const ANTIGRAVITY_PARTIAL_ISOLATION_NOTICE =
  "Antigravity runs with partial isolation: your global Antigravity settings, skills, agents and MCP servers in ~/.gemini/ may load, conversation transcripts and state are written there, and Caztor cannot turn them off. Caztor allows only file reading and editing tools and stops the turn when another tool appears, though that tool may already have started.";

export const ANTIGRAVITY_ENV_NAMES: readonly string[] = [
  "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
  "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
];

const SESSION_ID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MODELS_CACHE_MS = 30_000;
const MODELS_LIMIT_MS = 15_000;

const pick = (parent: Readonly<Record<string, string | undefined>>, names: readonly string[]): Record<string, string> => {
  const env: Record<string, string> = {};
  for (const name of names) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  return env;
};

export function buildAntigravityEnv(parent: Readonly<Record<string, string | undefined>>): Record<string, string> {
  return {
    ...pick(parent, ANTIGRAVITY_ENV_NAMES),
    NO_COLOR: "1",
  };
}

export interface AntigravityRunnerOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  root: string;
  env: Readonly<Record<string, string | undefined>>;
  credentials?: CredentialReaderPort;
  projectConfigConfirmed?: (fingerprint: string) => Promise<boolean>;
  /** Runs collaborators' turns inside bubblewrap. Without it a collaborator's turn is refused. */
  sandbox?: AgentSandbox;
  tap?: (line: string) => void;
}

function violation(outcome: AntigravityMapOutcome): string | null {
  const tool = outcome.tool;
  if (tool === undefined) return null;
  if (
    !tool.name ||
    !ANTIGRAVITY_ALLOWED_TOOLS.includes(tool.name as AntigravityAllowedTool) ||
    tool.name.includes(":") ||
    tool.name.includes("/") ||
    tool.name.startsWith("mcp")
  ) {
    return `Antigravity used a tool that Caztor does not allow (${tool.name || "unnamed"}), so the turn was stopped.`;
  }
  return null;
}

const SECRET_ENV_NAME = /(^|_)(api_?key|key|token|secret|password|credentials?)$/i;
/** The mask replaces plain text everywhere, so a short value or a path, which ordinary output also holds, must not count as a key. */
const MIN_ENV_SECRET_LENGTH = 16;
const looksLikeKey = (value: string) => value.length >= MIN_ENV_SECRET_LENGTH && !value.startsWith("/") && !/\s/.test(value);

/** The keys `agy` must not show in the chat. It receives none of them, so this only guards against what it finds and prints by itself. */
async function knownSecrets(options: AntigravityRunnerOptions, own?: CredentialReaderPort): Promise<string[]> {
  const fromEnv = Object.entries(options.env).flatMap(([name, value]) => (value !== undefined && SECRET_ENV_NAME.test(name) && looksLikeKey(value) ? [value] : []));
  const slots = PROVIDER_IDS.flatMap((provider) => providerSlots(provider));
  // A collaborator's turn masks their own keys as well as the host's, which it never receives either.
  const readers = [options.credentials, own].filter((reader): reader is CredentialReaderPort => reader !== undefined);
  const stored = await Promise.all(readers.flatMap((reader) => slots.map((slot) => reader.read(slot).catch(() => null))));
  return [...fromEnv, ...stored.flatMap((found) => (found?.ok === true && found.value !== null ? [found.value] : []))];
}

export function createAntigravityRunner(options: AntigravityRunnerOptions): AgentRunnerPort {
  const { fs, spawner, clock, root } = options;
  const detectEnv = buildAntigravityEnv(options.env);
  let binary: string | null = null;
  let current: ChildHandle | null = null;
  let listed: { at: number; models: string[] | null } | null = null;

  async function locate(): Promise<string | null> {
    binary ??= await resolveBinary(fs, "agy", options.env["PATH"]);
    return binary;
  }

  async function listModels(file: string, cwd: string, listEnv: Record<string, string>): Promise<string[] | null> {
    const result = await probe({
      spawner,
      clock,
      file,
      args: ["models"],
      cwd,
      env: listEnv,
      label: "antigravity",
      limitMs: MODELS_LIMIT_MS,
    });
    if (!result.ok) return null;
    const lines = result.output.split("\n");
    const models: string[] = [];
    for (const raw of lines) {
      const line = raw.trim();
      if (line === "" || line.startsWith("Fetching")) continue;
      const id = line.split("\t")[0]?.trim();
      if (id && /^[A-Za-z0-9._-]+$/.test(id)) {
        models.push(id);
      }
    }
    return [...new Set(models)].sort();
  }

  async function* run(req: TurnRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    if (signal.aborted) {
      yield { type: "done", reason: "cancelled" };
      return;
    }

    if (req.authMode === "api") {
      yield* failed("mode_unsupported", "Antigravity signs in with its account only.");
      return;
    }

    let chosenModel: string | null = null;
    if (req.model && req.model.trim() !== "") {
      const raw = req.model.trim();
      if (raw.startsWith("-")) {
        yield* failed("model_unavailable", "The model name cannot start with a dash.");
        return;
      }
      const parsed = parseModel(raw);
      if (!parsed.ok) {
        yield* failed("model_unavailable", parsed.message);
        return;
      }
      chosenModel = parsed.value;
    }

    const file = await locate();
    if (file === null) {
      yield* failed("not_installed", "agy was not found on the PATH.");
      return;
    }

    const found = await scanAntigravityProjectConfig(fs, root);
    if (found !== null && !(await (options.projectConfigConfirmed?.(found.fingerprint) ?? Promise.resolve(false)))) {
      yield* failed("isolation_failed", configRefusal("antigravity", found.files));
      return;
    }

    const definitionPath = `${root}/.agents/agents/caztor.md`;
    const linked = await fs.lstat(definitionPath).then((stats) => stats.isSymbolicLink(), () => false);
    const definition = linked ? null : await fs.readFile(definitionPath).catch(() => null);
    const definitionProblem = linked ? "The agent definition is a link to another file." : definition === null ? null : antigravityDefinitionProblem(new TextDecoder().decode(definition));
    if (definitionProblem !== null) {
      yield { type: "notice", level: "warning", message: definitionProblem, action: "replace_definition" };
      yield* failed("isolation_failed", `Caztor did not start Antigravity. ${definitionProblem}`);
      return;
    }

    yield {
      type: "notice",
      level: "info",
      message: ANTIGRAVITY_PARTIAL_ISOLATION_NOTICE,
    };

    const env = buildAntigravityEnv(req.env ?? options.env);
    const args = [
      "--output-format", "stream-json",
      "--mode", "accept-edits",
      "--agent", "caztor",
    ];

    if (chosenModel !== null) {
      args.push("--model", chosenModel);
    }

    if (req.sessionId !== null && SESSION_ID_REGEX.test(req.sessionId)) {
      args.push("--conversation", req.sessionId);
    }

    args.push(`-p=${req.prompt}`);

    const placed = await placeTurn(options.sandbox, req, { file, args, cwd: root, env, stdin: "" });
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
      mapper: createAntigravityMapper({ root }),
      notStarted: "agy could not be started. Is it installed?",
      tap: options.tap,
      check: violation,
      dropEventsOnViolation: true,
      onChild: (child) => void (current = child),
    });
  }

  return {
    provider: "antigravity",
    isolation: ANTIGRAVITY_ISOLATION_TIER,
    runTurn: (req, signal) => run(req, signal),
    forceStop() {
      current?.killGroup("SIGKILL");
    },
    projectConfig: () => scanAntigravityProjectConfig(fs, root),
    async detect(): Promise<ProviderStatus> {
      binary = null;
      const unavailable = (unavailableReason: string): ProviderStatus => ({
        provider: "antigravity",
        installed: false,
        unavailableReason,
        requiresModel: false,
      });

      const file = await locate();
      if (file === null) return unavailable("agy was not found on the PATH.");

      const scratch = await fs.mkdtemp(`${(options.env["TMPDIR"] ?? "/tmp").replace(/\/+$/, "")}/caztor-agy-`);
      try {
        const probed = await probe({
          spawner,
          clock,
          file,
          args: ["--version"],
          cwd: scratch,
          env: detectEnv,
          label: "antigravity",
        });
        if (!probed.ok) return unavailable(probed.reason);
        const version = versionOf(probed.output);
        if (version === null) {
          return unavailable(`agy answered --version with output that was not recognised: "${probed.output.trim().split("\n")[0]?.slice(0, 100) ?? ""}"`);
        }

        if (listed === null || clock.now() - listed.at >= MODELS_CACHE_MS) {
          listed = { at: clock.now(), models: await listModels(file, scratch, detectEnv) };
        }
        const { models } = listed;

        return {
          provider: "antigravity",
          installed: true,
          version: version.join("."),
          requiresModel: false,
          ...(models === null || models.length === 0 ? {} : { models }),
          ...(isOlder(version, ANTIGRAVITY_TESTED_VERSION)
            ? { versionWarning: `Caztor was tested with agy ${ANTIGRAVITY_TESTED_VERSION} or newer; this version may behave differently.` }
            : {}),
        };
      } finally {
        await fs.rm(scratch, { recursive: true, force: true }).catch(() => {});
      }
    },
  };
}
