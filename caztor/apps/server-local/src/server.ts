import { createHash, createHmac, randomBytes, randomUUID } from "node:crypto";
import { isIP } from "node:net";
import { basename } from "node:path";
import {
  createNodeSpawner,
  createProjectStore,
  createUserWriteLog,
  createStateStore,
  createAgentSandbox,
  createSandbox,
  createTectonicCompiler,
  withBuildRecipe,
  signedInProviders,
  nodeDirectoryWatcher,
  systemClock,
  type DirectoryWatcher,
  type FileSystem,
  type ProcessSpawner,
  createAgentsMdVisibility,
  createCredentialStore,
  createProjectCatalog,
  credentialConfigHome,
  papersDirOf,
  scaffoldPaper,
  createAntigravityRunner,
  createClaudeRunner,
  createOpencodeRunner,
  createPiRunner,
  createCodexRunner,
  createUserStore,
  INVITE_DEFAULT_MINUTES,
  createLoginRelay,
  createTrustKey,
  createTrustSeal,
  ensureUserHome,
  type TrustSeal,
  type UserStore,
} from "@caztor/adapters-local";
import {
  createApp,
  createEventHub,
  createRateLimiter,
  resolveLaunchToken,
  sessionCookieOf,
  timingSafeEqual,
  type ApiDeps,
  type EventHub,
  type ProjectOpenError,
  type RateLimiter,
  type SessionLookup,
} from "@caztor/api";
import type { Context } from "hono";
import { createCompileCoordinator, PAPERSMITH_MAIN, type AgentRunnerPort, type CredentialStorePort, type ProjectEntry, type ProviderId, type RelPath, type Result } from "@caztor/core";
import { createAgentServices } from "./agents.ts";
import { createCredentialStores, createPeople, createTurnOwners } from "./people.ts";
import { bindWithFallback, DEFAULT_PORT, LOOPBACK, type ListenFn } from "./listen.ts";
import { registerStatic } from "./static.ts";

export interface ServerOptions {
  /** The project folder, as given on the command line. */
  projectDir: string;
  /** Absolute path of the built web app. */
  webRoot: string;
  env: Readonly<Record<string, string | undefined>>;
  fs: FileSystem;
  listen: ListenFn;
  startPort?: number;
  /** Reports file system changes in the project folder. Tests replace it; the default is recursive `fs.watch`. */
  watcher?: DirectoryWatcher;
  /** Starts the LaTeX engine. Tests replace it; the default spawns real processes without a shell. */
  spawner?: ProcessSpawner;
  /** The provider adapters. Tests pass fakes; no real adapter exists yet, so by default every provider is listed as unavailable. */
  runners?: Partial<Record<ProviderId, AgentRunnerPort>>;
  /** Where the shipped agent definitions are; defaults to the repository's `agents` folder. */
  agentsDir?: string;
  /** The address to bind; loopback by default. Anything else needs at least one public name. */
  host?: string;
  /** The names collaborators reach this server by (`name` or `name:port`), allowed in Host and Origin besides loopback. */
  publicNames?: readonly string[];
  /** A TLS proxy fronts the server: session cookies get `Secure` and public links and origins use https. */
  secure?: boolean;
  /** The clock for invite expiry and rate limits. Tests replace it. */
  now?: () => number;
  /**
   * The origin of the page that shows Caztor in a frame (a PaperSmith dashboard). Only that origin may frame the pages,
   * and the server stays on its one project: the navigator is hidden and switching or creating projects is refused.
   */
  embedOrigin?: string;
}

/** An embedding origin is a plain `http(s)://host[:port]`, written exactly as browsers send it. */
function checkEmbedOrigin(origin: string): string {
  let parsed: URL;
  try {
    parsed = new URL(origin);
  } catch {
    throw new Error(`The embedding origin is not a valid origin: ${origin}`);
  }
  if ((parsed.protocol !== "http:" && parsed.protocol !== "https:") || parsed.origin !== origin) {
    throw new Error(`The embedding origin must be a plain http(s) origin such as http://127.0.0.1:8765: ${origin}`);
  }
  return origin;
}

export interface RunningServer {
  port: number;
  url: string;
  token: string;
  /** Set when the server is exposed: the one-time link that signs the host's browser in. */
  hostLink?: string;
  /** Real path of the open project folder. */
  readonly root: string;
  close(): Promise<void>;
}

/** The project folder's real path, or a readable error. */
async function resolveProjectRoot(fs: FileSystem, projectDir: string): Promise<string> {
  let root: string;
  try {
    root = await fs.realpath(projectDir);
  } catch {
    throw new Error(`The project folder does not exist: ${projectDir}`);
  }
  if (!(await fs.stat(root)).isDirectory()) throw new Error(`The project path is not a folder: ${projectDir}`);
  return root;
}

/** A plain folder name: nothing that could leave the papers folder, hide it, or read as an option. */
const PROJECT_NAME = /^[\p{L}\p{N}][\p{L}\p{N} ._-]{0,99}$/u;
const STARTER_TEX = "\\documentclass{article}\n\\begin{document}\nStart writing here.\n\\end{document}\n";

interface ProjectRuntime {
  root: string;
  app: { fetch(request: Request, env?: unknown): Response | Promise<Response> };
  turnRunning(): boolean;
  /** Stops what runs for this project. The listener and the open event streams belong to the server. */
  close(): Promise<void>;
}

/** How requests are told apart, shared by every project runtime. */
interface Access {
  /** At least one public name is set, so collaborators can sign in. */
  collaboratorMode: boolean;
  allowedHosts: string[];
  allowedOrigins: string[];
  sessions: SessionLookup;
  failedSessions: RateLimiter;
  users: NonNullable<ApiDeps["users"]>;
  pageToken(c: Context): Promise<string | null>;
}

interface Shared {
  options: ServerOptions;
  token: string;
  access: Access;
  events: EventHub;
  credentials: CredentialStorePort | undefined;
  /** Where collaborators' private folders and key stores live; undefined without a configuration folder. */
  personal: { configHome: string; uid: number | null; credentialsOf: (userId: string) => CredentialStorePort } | undefined;
  projects: NonNullable<ApiDeps["projects"]>;
  /** The key of every project's trust seal, one per server. */
  trustKey: () => Promise<Uint8Array | null>;
  isWorkspace(root: string): Promise<boolean>;
  titleOf(root: string): Promise<string | undefined>;
}

/** Everything bound to one project folder. */
function createProjectRuntime(root: string, shared: Shared): ProjectRuntime {
  const { options, token, access, events, credentials } = shared;
  const state = createStateStore({ fs: options.fs, root });
  // AGENTS.md is hidden from the tree, the file API and the watcher only while the project state says Caztor created it.
  const agentsMdCreatedByCaztor = createAgentsMdVisibility({ fs: options.fs, root, state });
  // The store tells this log about every save made through the file API, so a turn can tell the user's edits from the agent's.
  const userWrites = createUserWriteLog();
  const store = createProjectStore({
    fs: options.fs,
    root,
    userWrites,
    watcher: options.watcher ?? nodeDirectoryWatcher,
    clock: systemClock,
    agentsMdCreatedByCaztor,
  });
  // The engine receives only the allowlisted part of this environment; nothing else leaves the server process.
  const spawner = options.spawner ?? createNodeSpawner();
  // The opt-in bubblewrap sandbox: probed on demand, used only for projects that turned it on.
  const sandbox = createSandbox({ spawner, clock: systemClock, fs: options.fs, root, env: options.env });
  // A project whose source is not itself a document declares its build step in .caztor/build.json.
  const compiler = withBuildRecipe(
    createTectonicCompiler({
      spawner,
      sandbox,
      clock: systemClock,
      fs: options.fs,
      root,
      store,
      parentEnv: options.env,
    }),
    { spawner, clock: systemClock, fs: options.fs, root, parentEnv: options.env, trustKey: shared.trustKey },
  );
  const coordinator = createCompileCoordinator({ compiler });
  // Every collaborator's agent turn runs inside bubblewrap; the host's turns never do. Probed per CLI and person on first use.
  // Caztor's config folder (every person's private folder and the users store) is never mounted, beyond the person's own home.
  const agentSandbox = createAgentSandbox({
    spawner,
    clock: systemClock,
    fs: options.fs,
    root,
    env: options.env,
    ...(shared.personal === undefined ? {} : { protectedFolders: [`${shared.personal.configHome.replace(/\/+$/, "")}/caztor`] }),
  });
  // The host's confirmation of the project's CLI configuration, sealed with a key outside every project.
  const trust: TrustSeal = createTrustSeal({ fs: options.fs, configHome: shared.personal?.configHome ?? null, uid: shared.personal?.uid ?? null, root, key: shared.trustKey });
  const people = shared.personal === undefined ? undefined : createPeople({ fs: options.fs, root, state, env: options.env, ...shared.personal });
  const agents = createAgentServices({
    fs: options.fs,
    root,
    store,
    state,
    clock: systemClock,
    userWrites,
    ...(credentials === undefined ? {} : { credentials }),
    ...(people === undefined ? {} : { people }),
    ...(shared.personal === undefined ? {} : { turnOwner: createTurnOwners({ fs: options.fs, root, configHome: shared.personal.configHome }) }),
    runners: options.runners ?? {
      opencode: createOpencodeRunner({
        fs: options.fs,
        spawner,
        clock: systemClock,
        root,
        env: options.env,
        sandbox: agentSandbox,
        ...(credentials === undefined ? {} : { credentials }),
        projectConfigConfirmed: async (fingerprint) => trust.holds("opencode", fingerprint, (await state.load()).projectCliConfigTrusted.opencode),
      }),
      codex: createCodexRunner({ fs: options.fs, spawner, clock: systemClock, root, env: options.env, sandbox: agentSandbox, ...(credentials === undefined ? {} : { credentials }) }),
      claude: createClaudeRunner({
        fs: options.fs,
        spawner,
        clock: systemClock,
        root,
        env: options.env,
        sandbox: agentSandbox,
        ...(credentials === undefined ? {} : { credentials }),
        projectConfigConfirmed: async (fingerprint) => trust.holds("claude", fingerprint, (await state.load()).projectCliConfigTrusted.claude),
      }),
      antigravity: createAntigravityRunner({
        fs: options.fs,
        spawner,
        clock: systemClock,
        root,
        env: options.env,
        sandbox: agentSandbox,
        ...(credentials === undefined ? {} : { credentials }),
        projectConfigConfirmed: async (fingerprint) => trust.holds("antigravity", fingerprint, (await state.load()).projectCliConfigTrusted.antigravity),
      }),
      // Pi needs no trust gate: `-na` keeps it from loading the project's `.pi/`, which belongs to PaperSmith.
      pi: createPiRunner({ fs: options.fs, spawner, clock: systemClock, root, env: options.env, sandbox: agentSandbox, ...(credentials === undefined ? {} : { credentials }) }),
    },
    ...(options.agentsDir === undefined ? {} : { agentsDir: options.agentsDir }),
  });
  // Sign-ins from the browser: a collaborator's in the same sandbox as their turns, with their private home.
  const logins = createLoginRelay({
    fs: options.fs,
    spawner,
    clock: systemClock,
    env: options.env,
    sandbox: agentSandbox,
    homeOf: async (user) =>
      shared.personal === undefined
        ? { ok: false, error: { message: "This server has no configuration folder for private folders." } }
        : ensureUserHome({ fs: options.fs, configHome: shared.personal.configHome, uid: shared.personal.uid, userId: user.id, projectRoot: root }),
    onSignedIn: (user, provider) => agents.turns.noteLogin(provider, "signed_in", user),
  });
  // The host's own CLI sign-ins serve this project too: say so instead of offering a sign-in that already happened.
  void signedInProviders(options.fs, options.env).then((providers) => {
    for (const provider of providers) if (agents.turns.loginOf(provider) === "unknown") agents.turns.noteLogin(provider, "signed_in");
  }, () => {});
  const projectId = randomUUID();
  const built = createApp(
    {
      projectName: basename(root),
      projectId,
      ...(access.collaboratorMode ? { collaboratorMode: true } : {}),
      store,
      state,
      events,
      clock: systemClock,
      engine: () => compiler.available(),
      sandbox: () => sandbox.probe(),
      compile: { coordinator, compiler },
      agents,
      // Embedded, the server stays on its one project: the project routes answer 503.
      ...(options.embedOrigin === undefined ? { projects: shared.projects } : { embed: { origin: options.embedOrigin } }),
      papersmith: {
        status: async () =>
          (await shared.isWorkspace(root))
            ? { main: PAPERSMITH_MAIN as RelPath, exists: await options.fs.stat(`${root}/${PAPERSMITH_MAIN}`).then((stats) => !stats.isDirectory(), () => false) }
            : null,
        scaffold: async () => scaffoldPaper(options.fs, root, await shared.titleOf(root)),
      },
      ...(credentials === undefined ? {} : { credentials }),
      ...(people === undefined ? {} : { people }),
      trust,
      logins,
      users: access.users,
    },
    {
      token,
      allowedHosts: access.allowedHosts,
      allowedOrigins: access.allowedOrigins,
      projectId,
      sessions: access.sessions,
      failedSessions: access.failedSessions,
      ...(options.embedOrigin === undefined ? {} : { frameAncestors: [options.embedOrigin] }),
    },
  );
  registerStatic(built, { webRoot: options.webRoot, fs: options.fs, token: access.pageToken });
  // Changes made outside the editor (an agent, another program) reach the browser as `file_changed` events.
  const stopWatching = store.watch((change) => void events.publish("file_changed", change));

  return {
    root,
    app: built,
    turnRunning: () => agents.turns.busy(),
    close: async () => {
      stopWatching();
      await logins.close();
      // A running turn is stopped (its process group killed) before the project goes away.
      await agents.turns.shutdown();
      // A running compile is stopped (its process group killed) before the project goes away.
      await coordinator.shutdown();
    },
  };
}

const PUBLIC_NAME = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?$/;
const WILDCARD = new Set(["0.0.0.0", "::"]);
/** 20 failed sign-ins (wrong keys, used host links), and 20 failed cookie checks, per remote address and minute. */
const ATTEMPTS_PER_MINUTE = 20;

export function isLoopbackAddress(address: string): boolean {
  return address === "::1" || /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(address);
}

/** The bind address and public names, checked: binding beyond loopback without a public name is refused. */
export function checkExposure(host: string, names: readonly string[]): { host: string; publicNames: string[] } {
  if (isIP(host) === 0) throw new Error(`--host must be an IP address, such as 127.0.0.1, 0.0.0.0 or a Tailscale address; "${host}" is not one.`);
  const publicNames = names.map((name) => name.trim().toLowerCase());
  const bad = publicNames.find((name) => !PUBLIC_NAME.test(name));
  if (bad !== undefined) throw new Error(`--public-name must be a host name with an optional port, such as box.tail1234.ts.net or box.lan:4317; "${bad}" is not one.`);
  if (!isLoopbackAddress(host) && publicNames.length === 0) {
    throw new Error(`Caztor binds ${host} only with at least one --public-name: the names collaborators use to reach it (for example your Tailscale MagicDNS name).`);
  }
  return { host, publicNames };
}

/** The page token of a cookie session: derived from its secret, so nothing more is stored, and different for every session. */
function pageTokenOf(secret: string): string {
  return createHmac("sha256", secret).update("caztor-page-token").digest("base64url");
}

const sha256 = (value: string) => createHash("sha256").update(value, "utf8").digest("hex");

/**
 * Who a page or API request belongs to. The launch token is the host, as before. A cookie session is its user, and its
 * page carries that session's own token. When nothing is exposed the host is whoever opens the page, as before; once a
 * public name is set, a page without a session gets no token, and the host signs in once with the printed host link.
 */
function createAccess(options: {
  serverOptions: ServerOptions;
  token: string;
  port: number;
  publicNames: string[];
  store: UserStore | undefined;
  now: () => number;
  hostLinkCode: string | null;
}): Access {
  const { token, port, publicNames, store, now } = options;
  const secure = options.serverOptions.secure === true;
  const exposed = publicNames.length > 0;
  const loopback = [`${LOOPBACK}:${port}`, `localhost:${port}`];
  const publicScheme = secure ? "https" : "http";
  let hostLinkHash = options.hostLinkCode === null ? null : sha256(options.hostLinkCode);
  const failedSessions = createRateLimiter({ limit: ATTEMPTS_PER_MINUTE, windowMs: 60_000, now });
  const redemptions = createRateLimiter({ limit: ATTEMPTS_PER_MINUTE, windowMs: 60_000, now });
  const noStore = { ok: false as const, error: { code: "io" as const, message: "Caztor has no configuration folder to keep collaborators in." } };

  const sessions: SessionLookup = async (secret) => {
    const user = (await store?.findSession(secret)) ?? null;
    return user === null ? null : { user, token: pageTokenOf(secret) };
  };

  return {
    collaboratorMode: exposed,
    allowedHosts: [...loopback, ...publicNames],
    allowedOrigins: [...loopback.map((host) => `http://${host}`), ...publicNames.map((name) => `${publicScheme}://${name}`)],
    sessions,
    failedSessions,
    users: {
      secureCookies: secure,
      redemptions,
      list: async () => (store === undefined ? noStore : store.list()),
      async invite(name, minutes) {
        if (!exposed) return { ok: false, error: { code: "not_exposed", message: "Start Caztor with --public-name (and --host or a proxy) so collaborators can reach it, then invite them." } };
        if (store === undefined) return noStore;
        const made = await store.createInvite(name, minutes ?? INVITE_DEFAULT_MINUTES);
        if (!made.ok) return made;
        const { user, id, key, expiresAt } = made.value;
        return { ok: true, value: { user, link: `${publicScheme}://${publicNames[0]}/invite/${id}`, key, inviteId: id, expiresAt } };
      },
      revokeInvite: async (id) => (store === undefined ? noStore : store.revokeInvite(id)),
      revoke: async (id) => (store === undefined ? noStore : store.revoke(id)),
      async signIn(inviteId, key) {
        if (store === undefined) return null;
        const opened = await store.signIn(inviteId, key);
        return opened.ok && opened.value !== null ? opened.value.secret : null;
      },
      async redeemHost(code) {
        // The host link works once per launch; its code lives only in memory.
        if (store === undefined || hostLinkHash === null || !timingSafeEqual(sha256(code), hostLinkHash)) return null;
        hostLinkHash = null;
        const opened = await store.createHostSession();
        return opened.ok ? opened.value.secret : null;
      },
    },
    async pageToken(c) {
      const secret = sessionCookieOf(c.req.header("cookie"));
      if (secret !== null) {
        const address = (c.env as { incoming?: { socket?: { remoteAddress?: string } } } | undefined)?.incoming?.socket?.remoteAddress ?? "unknown";
        // A valid session always gets its token; failures are only counted, as the API counts them.
        const session = await sessions(secret);
        if (session !== null) return session.user.role === "host" ? token : session.token;
        failedSessions.hit(address);
      }
      return exposed ? null : token;
    },
  };
}

/** Starts the local server: loopback unless exposed, one project at a time, token kept in memory. */
export async function startServer(options: ServerOptions): Promise<RunningServer> {
  const root = await resolveProjectRoot(options.fs, options.projectDir);
  if (options.embedOrigin !== undefined) checkEmbedOrigin(options.embedOrigin);
  const token = resolveLaunchToken(options.env);
  const { host: bindHost, publicNames } = checkExposure(options.host ?? LOOPBACK, options.publicNames ?? []);
  const now = options.now ?? Date.now;

  // The Host allowlist needs the bound port, so the listener starts first and the app is attached right after.
  let runtime: ProjectRuntime | undefined;
  const listener = await bindWithFallback(
    options.listen,
    (request, env) => runtime?.app.fetch(request, env) ?? new Response("starting", { status: 503 }),
    options.startPort ?? DEFAULT_PORT,
    bindHost,
  );
  const events = createEventHub();
  // API keys live outside every project, in the user's configuration area; without a usable home folder there is no store.
  const configHome = credentialConfigHome(options.env);
  const uid = process.getuid?.() ?? null;
  const credentials = configHome === null ? undefined : createCredentialStore({ fs: options.fs, configHome, uid });
  // The people who may use this server live next to the keys, outside every project.
  const userStore = configHome === null ? undefined : createUserStore({ fs: options.fs, configHome, uid, now });
  const hostLinkCode = publicNames.length > 0 ? randomBytes(32).toString("base64url") : null;
  const access = createAccess({ serverOptions: options, token, port: listener.port, publicNames, store: userStore, now, hostLinkCode });
  // The host's own browser reaches the server through loopback unless only one other address is bound.
  const reachableByLoopback = isLoopbackAddress(bindHost) || WILDCARD.has(bindHost);
  const url = reachableByLoopback ? `http://${LOOPBACK}:${listener.port}` : `${options.secure === true ? "https" : "http"}://${publicNames[0]}`;
  const papersDir = papersDirOf(options.env);
  const catalog = createProjectCatalog({ fs: options.fs, papersDir, configHome });
  const home = options.env["HOME"];

  async function openProject(wanted: string): Promise<Result<void, ProjectOpenError>> {
    const path = wanted === "~" || wanted.startsWith("~/") ? `${home ?? ""}${wanted.slice(1)}` : wanted;
    if (!path.startsWith("/")) return { ok: false, error: { code: "invalid_path", message: 'The folder must be a full path, for example "~/papers/my-paper".' } };
    let next: string;
    try {
      next = await resolveProjectRoot(options.fs, path);
    } catch (error) {
      return { ok: false, error: { code: "not_found", message: error instanceof Error ? error.message : "The folder does not exist." } };
    }
    // Caztor writes its own files in a project and shows all of it, so the home folder, what holds it, and its hidden folders are never a project.
    const realHome = home === undefined ? null : await options.fs.realpath(home).catch(() => null);
    const holdsHome = next === "/" || (realHome !== null && (realHome === next || realHome.startsWith(`${next}/`)));
    const hiddenInHome = realHome !== null && next.startsWith(`${realHome}/`) && next.slice(realHome.length + 1).split("/").some((part) => part.startsWith("."));
    if (holdsHome || hiddenInHome) return { ok: false, error: { code: "folder_refused", message: "Open a project folder, not your home, root or a hidden folder." } };
    const current = runtime;
    if (current === undefined || next === current.root) return { ok: true, value: undefined };
    if (current.turnRunning()) return { ok: false, error: { code: "turn_running", message: "Stop the running turn before opening another project." } };
    runtime = createProjectRuntime(next, shared);
    // Pages hear first, so none keeps working on the folder that is closing.
    events.publish("project_changed", { name: basename(next) });
    await catalog.remember(next);
    await current.close().catch(() => {});
    return { ok: true, value: undefined };
  }

  async function createProject(name: string): Promise<Result<void, ProjectOpenError>> {
    if (!PROJECT_NAME.test(name)) return { ok: false, error: { code: "invalid_name", message: "Use a name of up to 100 letters, digits, spaces, dots, dashes or underscores, starting with a letter or digit." } };
    if (papersDir === null) return { ok: false, error: { code: "not_available", message: "Caztor cannot tell where your papers folder is." } };
    if (runtime?.turnRunning() === true) return { ok: false, error: { code: "turn_running", message: "Stop the running turn before creating a project." } };
    const folder = `${papersDir}/${name}`;
    const cannotCreate: Result<void, ProjectOpenError> = { ok: false, error: { code: "not_available", message: `The project could not be created in ${papersDir}.` } };
    try {
      await options.fs.mkdir(papersDir, { recursive: true });
    } catch {
      return cannotCreate;
    }
    try {
      // Not recursive: an existing folder is an error, so nothing of it is touched.
      await options.fs.mkdir(folder);
    } catch (error) {
      return (error as { code?: unknown }).code === "EEXIST" ? { ok: false, error: { code: "exists", message: `A project named "${name}" already exists.` } } : cannotCreate;
    }
    try {
      await options.fs.writeFile(`${folder}/main.tex`, new TextEncoder().encode(STARTER_TEX), { exclusive: true });
    } catch {
      // This call made the folder, so a retry must not find it in the way.
      await options.fs.rm(folder, { recursive: true, force: true }).catch(() => {});
      return cannotCreate;
    }
    return openProject(folder);
  }

  // One switch at a time, so two requests cannot both replace the running project.
  let switching: Promise<unknown> = Promise.resolve();
  const oneAtATime = (step: () => Promise<Result<void, ProjectOpenError>>) => {
    const done = switching.then(step);
    switching = done.catch(() => {});
    return done;
  };
  const shared: Shared = {
    options,
    token,
    access,
    events,
    credentials,
    personal: configHome === null ? undefined : { configHome, uid, credentialsOf: createCredentialStores({ fs: options.fs, configHome, uid }) },
    trustKey: createTrustKey({ fs: options.fs, configHome, uid }),
    isWorkspace: async (folder) => (await catalog.describe(folder))?.kind === "papersmith",
    titleOf: async (folder) => (await catalog.describe(folder))?.title,
    projects: {
      list: async () => {
        const active = runtime?.root ?? root;
        const listed = await catalog.list();
        const self = listed.some((entry) => entry.path === active) ? [] : [await catalog.describe(active)];
        return [...self.filter((entry): entry is ProjectEntry => entry !== null), ...listed]
          .sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path))
          .map((entry) => ({ ...entry, active: entry.path === active }));
      },
      open: (path) => oneAtATime(() => openProject(path)),
      create: (name) => oneAtATime(() => createProject(name)),
    },
  };
  runtime = createProjectRuntime(root, shared);

  return {
    port: listener.port,
    url,
    token,
    ...(hostLinkCode === null ? {} : { hostLink: `${url}/host/${hostLinkCode}` }),
    get root() {
      return runtime?.root ?? root;
    },
    close: async () => {
      await switching.catch(() => {});
      await runtime?.close();
      await listener.close();
    },
  };
}
