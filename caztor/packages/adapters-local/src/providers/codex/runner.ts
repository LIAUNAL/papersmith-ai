import type { AgentEvent, AgentRunnerPort, AuthMode, CredentialReaderPort, ProviderStatus, TurnRequest } from "@caztor/core";
import type { ChildHandle, Clock, FileSystem, ProcessSpawner } from "../../infra.ts";
import { placeTurn, type AgentSandbox } from "../../agent-sandbox.ts";
import { drive, failed, probe, STOP_ESCALATION_MS } from "../drive.ts";
import { resolveBinary } from "../resolve-binary.ts";
import { readStoredKey } from "../stored-key.ts";
import { versionOf } from "../version.ts";
import { createCodexMapper } from "./mapper.ts";

export { STOP_ESCALATION_MS };

/**
 * Codex is the exception to "file tools only": no documented flag turns command execution off, so the turn runs in
 * Codex's own `workspace-write` sandbox and the chat discloses it. The user's own configuration is skipped with the
 * documented `--ignore-user-config`. This is written from the documentation; no `codex` binary was available to check it.
 */
export const CODEX_ISOLATION_TIER = "I1";

const NOT_INSTALLED = "Codex is not installed: the codex command was not found on the PATH.";
const THREAD_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{5,99}$/;

/** Variables the CLI inherits: where to find itself and its login, the locale, the network and certificates. */
export const CODEX_ENV_NAMES: readonly string[] = [
  "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
];
/**
 * `CODEX_HOME` points the CLI at the user's own login folder. The design lists the whole `CODEX_` prefix, but a server
 * started from inside a Codex session also inherits that session's own variables, which must not reach a new one, so
 * only this one is passed.
 */
export const CODEX_HOME_NAME = "CODEX_HOME";

/**
 * The environment of a turn. Account mode never passes an exported `CODEX_API_KEY`, `OPENAI_API_KEY` or `OPENAI_BASE_URL`,
 * so the login is not overridden; api mode passes the stored key as `CODEX_API_KEY` and nothing else of the server's.
 */
export function buildCodexEnv(parent: Readonly<Record<string, string | undefined>>, mode: AuthMode = "account", key?: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const name of [...CODEX_ENV_NAMES, CODEX_HOME_NAME]) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  if (mode === "api" && key !== undefined) env["CODEX_API_KEY"] = key;
  env["NO_COLOR"] = "1";
  return env;
}

const FLAGS = ["exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check", "--ignore-user-config"];

export interface CodexRunnerOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder; the CLI runs there. */
  root: string;
  /** The server's environment; only `buildCodexEnv` of it reaches the CLI. */
  env: Readonly<Record<string, string | undefined>>;
  /** Where a stored API key is read from, only for a turn in api mode. */
  credentials?: CredentialReaderPort;
  /** Receives every raw line of the CLI's output; for diagnostics. */
  /** Runs collaborators' turns inside bubblewrap. Without it a collaborator's turn is refused. */
  sandbox?: AgentSandbox;
  tap?: (line: string) => void;
}

/**
 * The Codex adapter: starts `codex exec --json` without a shell, with the prompt on stdin and only an allowlisted
 * environment, and turns its stream into normalized events. The model is not passed: the flag is not in the
 * documentation this was written from, so the model setting is off for Codex.
 */
export function createCodexRunner(options: CodexRunnerOptions): AgentRunnerPort {
  const { fs, spawner, clock, root } = options;
  const detectEnv = buildCodexEnv(options.env);
  let binary: string | null = null;
  let current: ChildHandle | null = null;

  async function locate(): Promise<string | null> {
    binary ??= await resolveBinary(fs, "codex", options.env["PATH"]);
    return binary;
  }

  async function* run(req: TurnRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    if (signal.aborted) {
      yield { type: "done", reason: "cancelled" };
      return;
    }
    const file = await locate();
    if (file === null) {
      yield* failed("not_installed", NOT_INSTALLED);
      return;
    }
    let env: Record<string, string>;
    let secrets: string[] = [];
    if (req.authMode === "api") {
      const stored = await readStoredKey(req.credentials ?? options.credentials, "codex", "Codex");
      if ("stop" in stored) {
        yield* stored.stop;
        return;
      }
      env = buildCodexEnv(req.env ?? options.env, "api", stored.key);
      secrets = [stored.key];
    } else {
      env = buildCodexEnv(req.env ?? options.env);
    }
    const resume = req.sessionId !== null && THREAD_ID.test(req.sessionId) ? ["resume", req.sessionId] : [];
    const placed = await placeTurn(options.sandbox, req, { file, args: [...FLAGS, ...resume, "-"], cwd: root, env, stdin: req.prompt });
    if ("stop" in placed) {
      yield* placed.stop;
      return;
    }
    yield* drive({
      spawner,
      clock,
      spec: placed.spec,
      signal,
      mapper: createCodexMapper({ root }),
      notStarted: "Codex could not be started. Is it installed?",
      tap: options.tap,
      secrets,
      onChild: (child) => void (current = child),
    });
  }

  return {
    provider: "codex",
    isolation: CODEX_ISOLATION_TIER,
    runTurn: (req, signal) => run(req, signal),
    forceStop() {
      current?.killGroup("SIGKILL");
    },
    async detect(): Promise<ProviderStatus> {
      binary = null;
      const unavailable = (unavailableReason: string): ProviderStatus => ({ provider: "codex", installed: false, unavailableReason, requiresModel: false, supportsModel: false });
      const file = await locate();
      if (file === null) return unavailable(NOT_INSTALLED);
      const probed = await probe({ spawner, clock, file, args: ["--version"], cwd: root, env: detectEnv, label: "Codex" });
      if (!probed.ok) return unavailable(probed.reason);
      const version = versionOf(probed.output);
      if (version === null) return unavailable(`Codex answered --version with output that was not recognised: "${probed.output.trim().split("\n")[0]?.slice(0, 100) ?? ""}"`);
      return { provider: "codex", installed: true, version: version.join("."), requiresModel: false, supportsModel: false };
    },
  };
}
