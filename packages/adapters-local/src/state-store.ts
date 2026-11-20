import { isAgentTarget, isGuideTarget, isSafeUserId, parseAuthMode, PROVIDER_IDS, parseRelPath } from "@caztor/core";
import type { ContentHash, PersonalState, ProjectState, ProviderId, SessionRecord, StatePort } from "@caztor/core";
import type { FileSystem } from "./infra.ts";

export interface StateStoreOptions {
  fs: FileSystem;
  /** Absolute path of the project folder; the state lives in `<root>/.caztor/state.json`. */
  root: string;
}

export function defaultProjectState(): ProjectState {
  return {
    selectedProvider: null,
    authModes: {},
    models: {},
    sessions: {},
    mainFile: null,
    stopOnFirstError: false,
    autoCompile: true,
    sandboxedCompile: false,
    disclosureAcknowledged: false,
    projectCliConfigTrusted: {},
    provisioned: {},
  };
}

const STATE_DIR = ".caztor";
const STATE_FILE = "state.json";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const isProvider = (value: string): value is ProviderId => (PROVIDER_IDS as readonly string[]).includes(value);
const isHash = (value: unknown): value is ContentHash => typeof value === "string" && value.startsWith("sha256:");

function pick<T>(value: unknown, fallback: T, valid: (candidate: unknown) => candidate is T): T {
  return valid(value) ? value : fallback;
}

const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";

function parseSession(value: unknown): SessionRecord | null {
  if (!isRecord(value)) return null;
  const { sessionId, agentHash, isolation } = value;
  if (typeof sessionId !== "string" || !isHash(agentHash) || typeof isolation !== "string") return null;
  const authMode = parseAuthMode(value["authMode"]);
  return { sessionId, agentHash, isolation, ...(authMode === null ? {} : { authMode }) };
}

/** The per-person fields of `raw` (the top level for the host, a `users` entry for a collaborator), each checked. */
function sanitizePersonal(raw: Record<string, unknown>): PersonalState {
  const authModes: ProjectState["authModes"] = {};
  const models: ProjectState["models"] = {};
  const sessions: ProjectState["sessions"] = {};
  if (isRecord(raw["authModes"])) {
    for (const [provider, mode] of Object.entries(raw["authModes"])) {
      const parsed = parseAuthMode(mode);
      if (isProvider(provider) && parsed !== null) authModes[provider] = parsed;
    }
  }
  if (isRecord(raw["models"])) {
    for (const [provider, model] of Object.entries(raw["models"])) {
      if (isProvider(provider) && typeof model === "string") models[provider] = model;
    }
  }
  if (isRecord(raw["sessions"])) {
    for (const [provider, record] of Object.entries(raw["sessions"])) {
      const session = parseSession(record);
      if (isProvider(provider) && session !== null) sessions[provider] = session;
    }
  }
  const provider = raw["selectedProvider"];
  return { selectedProvider: typeof provider === "string" && isProvider(provider) ? provider : null, authModes, models, sessions };
}

/** Keeps every field that has the right shape and falls back to the default for the rest. */
function sanitize(raw: unknown): ProjectState {
  const defaults = defaultProjectState();
  if (!isRecord(raw)) return defaults;

  const { selectedProvider, authModes, models, sessions } = sanitizePersonal(raw);
  const provisioned: ProjectState["provisioned"] = {};
  // Each collaborator's choices, under an id that may name a folder; the key is left out until one exists.
  const users: Record<string, PersonalState> = {};
  if (isRecord(raw["users"])) {
    for (const [id, entry] of Object.entries(raw["users"])) {
      if (isSafeUserId(id) && isRecord(entry)) users[id] = sanitizePersonal(entry);
    }
  }
  const trusted: ProjectState["projectCliConfigTrusted"] = {};
  if (isRecord(raw["projectCliConfigTrusted"])) {
    for (const [provider, fingerprint] of Object.entries(raw["projectCliConfigTrusted"])) {
      // A sealed record (`hmac1:`), or a plain fingerprint of an older version, which no longer counts but is kept.
      if (isProvider(provider) && (isHash(fingerprint) || (typeof fingerprint === "string" && /^hmac1:[A-Za-z0-9_-]{43}$/.test(fingerprint)))) trusted[provider] = fingerprint;
    }
  }
  if (isRecord(raw["provisioned"])) {
    for (const [path, entry] of Object.entries(raw["provisioned"])) {
      // The native definitions and the writing guides live in reserved folders, which `parseRelPath` refuses, so their paths are allowed by name.
      if ((isAgentTarget(path) || isGuideTarget(path) || parseRelPath(path).ok) && isRecord(entry) && isHash(entry["hash"]) && typeof entry["createdByCaztor"] === "boolean") {
        provisioned[path] = { hash: entry["hash"], createdByCaztor: entry["createdByCaztor"] };
      }
    }
  }

  const mainFile = raw["mainFile"];
  return {
    selectedProvider,
    authModes,
    models,
    sessions,
    mainFile: typeof mainFile === "string" && parseRelPath(mainFile).ok ? (mainFile as ProjectState["mainFile"]) : null,
    stopOnFirstError: pick(raw["stopOnFirstError"], defaults.stopOnFirstError, isBoolean),
    autoCompile: pick(raw["autoCompile"], defaults.autoCompile, isBoolean),
    sandboxedCompile: pick(raw["sandboxedCompile"], defaults.sandboxedCompile, isBoolean),
    disclosureAcknowledged: pick(raw["disclosureAcknowledged"], defaults.disclosureAcknowledged, isBoolean),
    projectCliConfigTrusted: trusted,
    provisioned,
    ...(Object.keys(users).length === 0 ? {} : { users }),
  };
}

/** Per-project settings in `.caztor/state.json`: forgiving reads, atomic writes, serialized updates. */
export function createStateStore(options: StateStoreOptions): StatePort {
  const { fs, root } = options;
  let queue: Promise<unknown> = Promise.resolve();

  /** The state directory, unless its real location is outside the project. */
  async function stateDir(): Promise<string | null> {
    const rootReal = await fs.realpath(root);
    const dir = `${rootReal}/${STATE_DIR}`;
    try {
      const real = await fs.realpath(dir);
      return real === dir ? dir : null;
    } catch (error) {
      if ((error as { code?: string }).code === "ENOENT") return dir;
      throw error;
    }
  }

  async function read(dir: string): Promise<ProjectState> {
    try {
      const text = new TextDecoder().decode(await fs.readFile(`${dir}/${STATE_FILE}`));
      return sanitize(JSON.parse(text) as unknown);
    } catch {
      return defaultProjectState();
    }
  }

  async function write(dir: string, state: ProjectState): Promise<void> {
    await fs.mkdir(dir, { recursive: true });
    const temp = `${dir}/${STATE_FILE}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temp, new TextEncoder().encode(`${JSON.stringify(state, null, 2)}\n`), { exclusive: true });
      await fs.rename(temp, `${dir}/${STATE_FILE}`);
    } catch (error) {
      await fs.rm(temp, { force: true }).catch(() => {});
      throw error;
    }
  }

  function serial(edit: (current: ProjectState) => Partial<ProjectState>): Promise<ProjectState> {
    const run = async (): Promise<ProjectState> => {
      const dir = await stateDir();
      if (dir === null) throw new Error("The .caztor folder is a link, so Caztor cannot keep the project's settings in it. Replace the link with a plain folder.");
      const current = await read(dir);
      const next = sanitize({ ...current, ...edit(current) });
      await write(dir, next);
      return next;
    };
    const result = queue.then(run, run);
    queue = result.catch(() => {});
    return result;
  }

  return {
    async load() {
      // A state directory that cannot be inspected (a link loop, no permission) behaves like a corrupt file.
      const dir = await stateDir().catch(() => null);
      return dir === null ? defaultProjectState() : read(dir);
    },
    update: (patch) => serial(() => patch),
    change: (edit) => serial(edit),
  };
}
