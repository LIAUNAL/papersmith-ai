import { GUIDES_DIR, isGuideTarget } from "./agent-targets.ts";
import { authModeOf, credentialSlot } from "./auth.ts";
import { compactEvents, type ChatHistoryPort } from "./chat-history.ts";
import { createReplayBuffer, validateAgentEvent, type ReplayBuffer } from "./turn-events.ts";
import { buildPrompt, expandAgentCommand } from "./prompt.ts";
import { MAX_NAMED_UNPROTECTED, PROVIDER_IDS } from "./ports.ts";
import { HOST_TURN_USER, type PeoplePort, type PersonalPorts, type TurnUser } from "./people.ts";
import type {
  ProjectAgentsPort,
  AgentDefinition,
  AgentRunnerPort,
  AuthMode,
  ChangedFile,
  CredentialStorePort,
  ProviderId,
  ProvisionerPort,
  ProvisionOutcome,
  RelPath,
  RestoreResult,
  Result,
  SnapshotPort,
  StatePort,
  TurnEvent,
  TurnRequest,
  UserWrite,
} from "./ports.ts";

/** Turns kept undoable, as the design says. */
export const KEEP_TURNS = 20;
/** Longest message the chat accepts. */
export const MAX_PROMPT_CHARS = 100_000;

/** Why a turn did not start. Nothing was provisioned, captured or spawned. */
export type StartRefusal =
  | { code: "busy"; message: string }
  | { code: "invalid_prompt"; message: string }
  | { code: "unknown_provider"; message: string }
  | { code: "not_installed"; message: string }
  | { code: "model_required"; message: string }
  /** The provider is in api mode and no usable key is stored for it. */
  | { code: "api_key_missing"; message: string }
  /** The provider has no api mode, or Caztor has no key route for the model's vendor. */
  | { code: "mode_unsupported"; message: string }
  /** The requesting collaborator's own state or private folder cannot be used. */
  | { code: "person_unavailable"; message: string };

export interface UserWriteRecording {
  /** Starts recording what the user saves through the file API. */
  begin(): void;
  /** What was saved so far, without stopping. */
  peek(): ReadonlyMap<RelPath, UserWrite>;
  /** Waits for the saves still in flight, stops recording and returns what was saved. */
  end(): Promise<ReadonlyMap<RelPath, UserWrite>>;
}

const sameWrites = (a: ReadonlyMap<RelPath, UserWrite>, b: ReadonlyMap<RelPath, UserWrite>): boolean =>
  a.size === b.size && [...b].every(([path, write]) => a.get(path)?.first === write.first && a.get(path)?.last === write.last && a.has(path));

export interface TurnServiceDeps {
  runners: Partial<Record<ProviderId, AgentRunnerPort>>;
  provisioner: ProvisionerPort;
  snapshots: SnapshotPort;
  state: StatePort;
  userWrites: UserWriteRecording;
  /** Makes the project store look at the disk now, so the editor learns what the agent changed. */
  rescan(): Promise<void>;
  history?: ChatHistoryPort;
  /** The project's own agents, which a message can name with `/<name>`. */
  projectAgents?: ProjectAgentsPort;
  /** Tells whether an API key is stored; without it a turn in api mode is refused. The key itself never reaches the service. */
  credentials?: Pick<CredentialStorePort, "status">;
  /** Each collaborator's own state, history, keys and run environment. Without it a collaborator's turn is refused. */
  people?: PeoplePort;
  /**
   * The collaborator who ran a turn, as their own kept history shows it, or null when no collaborator did. It is what
   * keeps the turn theirs after a restart, when the memory of who ran what is gone.
   */
  turnOwner?: (turnId: string) => Promise<{ id: string; name?: string } | null>;
  newId?: () => string;
  now?: () => number;
  keepTurns?: number;
  /** Starts a timer and returns the function that cancels it. Defaults to the platform timer. */
  setTimeout?: (fn: () => void, ms: number) => () => void;
}

/** How long a runner gets to end after a stop before the turn is cut off and the adapter kills its processes. */
export const STOP_GRACE_MS = 5000;

const platformTimer = (fn: () => void, ms: number): (() => void) => {
  const handle = globalThis.setTimeout(fn, ms);
  return () => globalThis.clearTimeout(handle);
};

export interface TurnSubscriber {
  /** `seq` counts from 1 within the turn. */
  onEvent(event: TurnEvent, seq: number): void;
  /** Called once, after the last event. */
  onEnd(): void;
}

export interface TurnSummary {
  turnId: string;
  provider: ProviderId;
  running: boolean;
  /** Who started the turn. */
  owner: { id: string; name: string };
}

/** `not_yours`: someone else ran the turn; only they can undo it. */
export type UndoOutcome = RestoreResult | { status: "busy" } | { status: "not_yours"; message: string };

/** What the turns so far show about a provider's CLI login. It is kept in memory, because a login can end at any time. */
export type ProviderLogin = "signed_in" | "signed_out" | "unknown";

export interface TurnService {
  /** What the person's account-mode turns since the server started show about the provider's CLI login. The host when `user` is missing. */
  loginOf(provider: ProviderId, user?: TurnUser): ProviderLogin;
  /** Records what a sign-in outside a turn (the browser login relay) showed about the person's (the host when missing) CLI login. */
  noteLogin(provider: ProviderId, login: ProviderLogin, user?: TurnUser): void;
  /**
   * Accepts the turn and runs it in the background; the answer comes before the agent starts. The turn uses the
   * requesting person's history, session, choices and keys; the host when `user` is missing.
   */
  start(req: { provider: ProviderId; prompt: string; user?: TurnUser }): Promise<Result<{ turnId: string }, StartRefusal>>;
  /** Asks the running turn to stop. False when `turnId` is not the running turn or `user` (the host when missing) did not start it. */
  stop(turnId: string, user?: TurnUser): boolean;
  /**
   * Replays the events after `after` and then follows the turn. A dropped subscriber costs the turn nothing: it runs
   * on the server. Null when `turnId` is not the current or the last turn.
   */
  subscribe(turnId: string, subscriber: TurnSubscriber, after?: number): (() => void) | null;
  /** The running turn, or the last one that ended; null before the first. */
  current(): TurnSummary | null;
  /** A turn is starting or running. */
  busy(): boolean;
  /** Whether `user` (the host when missing) may undo the turn: they ran it, or it is of unknown origin and they are the host. */
  mayUndo(turnId: string, user?: TurnUser): Promise<boolean>;
  /** Undoes the turn's changes, when `user` (the host when missing) ran it. */
  undo(turnId: string, mode: "strict" | "skip_conflicts" | "force", user?: TurnUser): Promise<UndoOutcome>;
  /** Starts a new chat for the provider and the person (the host when missing). False while a turn runs. */
  resetSession(provider: ProviderId, user?: TurnUser): Promise<boolean>;
  /** Writes Caztor's definition over the one the user changed. Refused while a turn runs. */
  replaceDefinition(provider: ProviderId): Promise<Result<{ outcomes: ProvisionOutcome[] }, { code: "busy" | "provision_failed"; message: string }>>;
  /** Resolves when no turn runs. */
  idle(): Promise<void>;
  /** Stops the running turn and waits for it to end. */
  shutdown(): Promise<void>;
}

interface Turn {
  id: string;
  provider: ProviderId;
  user: TurnUser;
  /** The person's state, history and keys this turn uses. */
  person: PersonalPorts;
  /** Set only for a collaborator: the environment and key reader handed to the runner. */
  overrides: Pick<TurnRequest, "env" | "credentials" | "sandbox">;
  prompt: string;
  /** The sign-in method this turn runs under, fixed when it started. */
  authMode: AuthMode;
  startedAt: number;
  buffer: ReplayBuffer;
  /** Set once an invalid event from the runner was reported, so the user hears about it only once. */
  invalidReported: boolean;
  ended: boolean;
  controller: AbortController;
  subscribers: Set<TurnSubscriber>;
  finished: Promise<void>;
}

const CUT_OFF = Symbol("cut off");

/** Lets the runner's own cleanup run after `done` (as leaving a `for await` loop would), without waiting for it forever. */
async function closeIterator(iterator: AsyncIterator<unknown>, startTimer: (fn: () => void, ms: number) => () => void): Promise<void> {
  let cancel = (): void => {};
  const late = new Promise<void>((resolve) => void (cancel = startTimer(resolve, STOP_GRACE_MS)));
  try {
    await Promise.race([Promise.resolve(iterator.return?.()).then(() => undefined), late]);
  } catch {
    // A failing cleanup does not change how the turn went.
  } finally {
    cancel();
  }
}

const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/**
 * One chat turn at a time per project: provision the definition, start recording the user's saves, take the snapshot,
 * run the agent, then work out which files it changed. The turn runs on the server whether or not anyone listens.
 */
export function createTurnService(deps: TurnServiceDeps): TurnService {
  const { runners, provisioner, snapshots, state, userWrites, history } = deps;
  const newId = deps.newId ?? (() => crypto.randomUUID());
  const now = deps.now ?? (() => Date.now());
  const keepTurns = deps.keepTurns ?? KEEP_TURNS;
  const startTimer = deps.setTimeout ?? platformTimer;
  /** Per person id, then per provider. */
  const logins = new Map<string, Map<ProviderId, ProviderLogin>>();
  /** Who ran each turn since the server started; older turns are found in the person's history. */
  const owners = new Map<string, TurnUser>();

  /** The host's ports are the service's own, so a single-user project works exactly as before. */
  const hostPorts: PersonalPorts = {
    state,
    ...(history === undefined ? {} : { history }),
    // The host's key is read by the runners themselves, so only `status` is ever used here.
    ...(deps.credentials === undefined ? {} : { credentials: deps.credentials as NonNullable<PersonalPorts["credentials"]> }),
  };
  const personOf = (user: TurnUser): PersonalPorts | null => (user.role === "host" ? hostPorts : (deps.people?.(user) ?? null));
  const sameUser = (a: TurnUser, b: TurnUser) => (a.role === "host" && b.role === "host") || a.id === b.id;
  const setLogin = (user: TurnUser, provider: ProviderId, login: ProviderLogin) => {
    const key = user.role === "host" ? HOST_TURN_USER.id : user.id;
    if (!logins.has(key)) logins.set(key, new Map());
    logins.get(key)!.set(provider, login);
  };

  let starting: TurnUser | null = null;
  let last: Turn | null = null;
  /** Files an undo reverted since the agent last worked; the next prompt names them. */
  let reverted: RelPath[] = [];

  const running = () => last !== null && !last.ended;
  /** Why `user` cannot start, stop or undo now, naming whoever else runs a turn. */
  const busyMessage = (user: TurnUser): string => {
    const owner = running() ? last!.user : starting;
    return owner !== null && !sameUser(owner, user) ? `${owner.name} has a turn running. Wait for it to finish.` : "A turn is already running. Wait for it to finish or stop it.";
  };

  function emit(turn: Turn, event: TurnEvent): void {
    const seq = turn.buffer.push(event);
    for (const subscriber of [...turn.subscribers]) {
      try {
        subscriber.onEvent(event, seq);
      } catch {
        // A failing subscriber must not stop the turn or the others.
      }
    }
  }

  async function finish(turn: Turn): Promise<void> {
    const history = turn.person.history;
    if (history !== undefined) {
      try {
        await history.append({
          turnId: turn.id,
          provider: turn.provider,
          prompt: turn.prompt,
          startedAt: turn.startedAt,
          events: compactEvents(turn.buffer.events()),
        });
      } catch (error) {
        // A conversation that cannot be stored is still shown; it is just not restored after a reload.
        emit(turn, { type: "notice", level: "warning", message: `This conversation could not be saved, so it will not be restored after a reload: ${errorText(error)}` });
      }
    }
    turn.ended = true;
    const subscribers = [...turn.subscribers];
    turn.subscribers.clear();
    for (const subscriber of subscribers) {
      try {
        subscriber.onEnd();
      } catch {
        // See above.
      }
    }
  }

  const failTurn = (turn: Turn, code: "snapshot_failed" | "provider_error", message: string, detail?: string): void => {
    emit(turn, { type: "error", code, message, ...(detail === undefined ? {} : { detail }) });
    emit(turn, { type: "done", reason: "failed" });
  };

  /** Chooses between resuming and starting over, and tells the chat when the conversation starts over. */
  async function chooseSession(turn: Turn, runner: AgentRunnerPort, agent: AgentDefinition): Promise<string | null> {
    const record = (await turn.person.state.load()).sessions[turn.provider];
    if (record === undefined) return null;
    if (record.agentHash !== agent.hash) {
      emit(turn, { type: "notice", level: "info", message: "New conversation started because the agent definition changed." });
      return null;
    }
    if (record.isolation !== runner.isolation) {
      emit(turn, { type: "notice", level: "info", message: "New conversation started because the isolation level changed." });
      return null;
    }
    // A conversation saved before sign-in modes existed was an account conversation.
    if ((record.authMode ?? "account") !== turn.authMode) {
      emit(turn, { type: "notice", level: "info", message: "New conversation started because the sign-in method changed." });
      return null;
    }
    return record.sessionId;
  }

  async function rememberSession(turn: Turn, runner: AgentRunnerPort, agent: AgentDefinition, sessionId: string): Promise<void> {
    const current = await turn.person.state.load();
    await turn.person.state.update({
      sessions: { ...current.sessions, [turn.provider]: { sessionId, agentHash: agent.hash, isolation: runner.isolation, authMode: turn.authMode } },
    });
  }

  /** Runs the agent and forwards its events; makes sure the turn gets exactly one `done`. */
  async function runAgent(turn: Turn, runner: AgentRunnerPort, agent: AgentDefinition, model: string | null, sessionId: string | null, prompt: string): Promise<void> {
    const signal = turn.controller.signal;
    let doneSeen = false;
    let failure: unknown;
    let cutOffReported = false;
    // A runner that ignores the abort signal must not keep the turn, or the server's shutdown, waiting forever.
    let cancelGrace = (): void => {};
    let cutOff!: () => void;
    const cutOffSignal = new Promise<typeof CUT_OFF>((resolve) => (cutOff = () => resolve(CUT_OFF)));
    const armGrace = () => void (cancelGrace = startTimer(cutOff, STOP_GRACE_MS));
    if (signal.aborted) armGrace();
    else signal.addEventListener("abort", armGrace, { once: true });
    const iterator = runner.runTurn({ prompt, sessionId, model, agent, authMode: turn.authMode, ...turn.overrides }, signal)[Symbol.asyncIterator]();
    try {
      for (;;) {
        const next = await Promise.race([iterator.next(), cutOffSignal]);
        if (next === CUT_OFF) {
          try {
            runner.forceStop?.();
          } catch {
            // Nothing more can be done about a process that cannot be killed.
          }
          cutOffReported = true;
          void Promise.resolve(iterator.return?.()).catch(() => {});
          emit(turn, { type: "notice", level: "warning", message: "The agent did not stop when asked, so Caztor ended it." });
          emit(turn, { type: "done", reason: "cancelled" });
          doneSeen = true;
          break;
        }
        if (next.done) break;
        const event = validateAgentEvent(next.value);
        if (event === null) {
          if (!turn.invalidReported) {
            turn.invalidReported = true;
            emit(turn, { type: "notice", level: "warning", message: "The agent sent data Caztor does not understand. It was ignored." });
          }
          continue;
        }
        if (event.type === "session") await rememberSession(turn, runner, agent, event.sessionId).catch(() => {});
        if (turn.authMode === "account") {
          if (event.type === "error" && event.code === "auth") setLogin(turn.user, turn.provider, "signed_out");
          if (event.type === "done" && event.reason === "completed") setLogin(turn.user, turn.provider, "signed_in");
        }
        emit(turn, event);
        if (event.type === "done") {
          doneSeen = true;
          break;
        }
      }
    } catch (error) {
      failure = error;
    } finally {
      cancelGrace();
      signal.removeEventListener("abort", armGrace);
    }
    if (doneSeen && !cutOffReported) await closeIterator(iterator, startTimer);
    if (doneSeen) return;
    if (signal.aborted) {
      emit(turn, { type: "done", reason: "cancelled" });
      return;
    }
    if (failure !== undefined) failTurn(turn, "provider_error", "The agent stopped unexpectedly.", errorText(failure));
    else failTurn(turn, "provider_error", "The agent ended without finishing its answer.");
  }

  async function compare(turn: Turn, writes: ReadonlyMap<RelPath, UserWrite>): Promise<ChangedFile[]> {
    try {
      const found = await snapshots.diff(turn.id, writes);
      if (found.ok) return found.value;
      emit(turn, { type: "notice", level: "warning", message: `The list of changed files could not be worked out: ${found.error.message}` });
    } catch (error) {
      emit(turn, { type: "notice", level: "warning", message: `The list of changed files could not be worked out: ${errorText(error)}` });
    }
    return [];
  }

  /** Names Caztor cannot read; they are not in the changed-files list and undo does not cover them. */
  async function unreadableNames(): Promise<RelPath[]> {
    try {
      const found = await snapshots.notCovered();
      return found.ok ? found.value : [];
    } catch {
      return [];
    }
  }

  /**
   * The recorder keeps running until the comparison is done, so a save that lands between the agent's last event and the
   * list of changes still counts as the user's. If one landed during the comparison, it is made again with the final record.
   */
  async function changedFiles(turn: Turn, endRecording: () => Promise<ReadonlyMap<RelPath, UserWrite>>): Promise<ChangedFile[]> {
    try {
      await deps.rescan();
    } catch {
      // The periodic rescan will catch up.
    }
    const used = userWrites.peek();
    const files = await compare(turn, used);
    const final = await endRecording();
    return sameWrites(used, final) ? files : compare(turn, final);
  }

  /** Why a turn in api mode cannot start (no key route, no key, a store that refuses), or null when it can. */
  async function apiRefusal(provider: ProviderId, model: string | null, credentials: PersonalPorts["credentials"]): Promise<StartRefusal | null> {
    const slot = credentialSlot(provider, model);
    if (!slot.ok) {
      return { code: slot.error.code === "vendor_required" ? "model_required" : "mode_unsupported", message: slot.error.message };
    }
    const label = slot.value.startsWith("opencode:") ? `opencode (${slot.value.slice("opencode:".length)})` : provider;
    const missing: StartRefusal = { code: "api_key_missing", message: `No API key is stored for ${label}. Add one in the chat settings, or switch to account sign-in.` };
    if (credentials === undefined) return missing;
    try {
      const found = await credentials.status(slot.value);
      if (!found.ok) return { code: "api_key_missing", message: found.error.message };
      return found.value.set ? null : missing;
    } catch {
      return { code: "api_key_missing", message: `The stored API key for ${label} could not be checked.` };
    }
  }

  async function execute(turn: Turn, runner: AgentRunnerPort, model: string | null): Promise<void> {
    const signal = turn.controller.signal;
    const provisioned = await provisioner.ensure(turn.provider);
    if (!provisioned.ok) {
      failTurn(turn, "provider_error", `Caztor could not prepare the project for the assistant: ${provisioned.error.message}`);
      return;
    }
    const { outcomes, agent } = provisioned.value;
    for (const outcome of outcomes) {
      if (outcome.status === "unavailable") {
        emit(turn, {
          type: "notice",
          level: "warning",
          message: `The writing guides could not be prepared, so this turn runs without them: ${outcome.detail ?? "the reason is unknown"}`,
        });
        continue;
      }
      if (outcome.status !== "skipped_user_modified") continue;
      emit(turn, {
        type: "notice",
        level: "warning",
        message: isGuideTarget(outcome.target)
          ? `The writing guide \`${outcome.target.slice(GUIDES_DIR.length + 1)}\` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide.`
          : `${outcome.target} was changed by you, so Caztor kept your version. Replace it to use Caztor's definition.`,
        action: "replace_definition",
      });
    }
    const sessionId = await chooseSession(turn, runner, agent);
    if (signal.aborted) {
      emit(turn, { type: "done", reason: "cancelled" });
      return;
    }

    // Recording starts before the snapshot: a save that lands while the snapshot is taken belongs to the user.
    userWrites.begin();
    let recording = true;
    try {
      const captured = await snapshots.capture(turn.id);
      if (!captured.ok) {
        recording = false;
        await userWrites.end();
        failTurn(turn, "snapshot_failed", `The turn did not start because a snapshot of your project could not be taken: ${captured.error.message}`);
        return;
      }
      await snapshots.prune(keepTurns).catch(() => []);
      emit(turn, {
        type: "turn_started",
        turnId: turn.id,
        provider: turn.provider,
        snapshotPartial: captured.value.partial,
        unprotected: captured.value.unprotected.slice(0, MAX_NAMED_UNPROTECTED),
        ...(captured.value.unprotected.length > MAX_NAMED_UNPROTECTED ? { unprotectedCount: captured.value.unprotected.length } : {}),
      });

      if (signal.aborted) emit(turn, { type: "done", reason: "cancelled" });
      else {
        const agents = (await deps.projectAgents?.list().catch(() => [])) ?? [];
        const sources = agents.length === 0 ? [] : ((await deps.projectAgents?.sources?.().catch(() => [])) ?? []);
        const prompt = buildPrompt(expandAgentCommand(turn.prompt, agents, sources), reverted);
        reverted = [];
        await runAgent(turn, runner, agent, model, sessionId, prompt);
      }

      const files = await changedFiles(turn, () => {
        recording = false;
        return userWrites.end();
      });
      const notCovered = await unreadableNames();
      emit(turn, { type: "files_changed", turnId: turn.id, files, ...(notCovered.length > 0 ? { notCovered } : {}) });
    } finally {
      if (recording) await userWrites.end();
    }
  }

  /**
   * Who ran the turn: known since the server started, else found in the person's own history, else in a
   * collaborator's kept history (`turnOwner`); null when unknown.
   */
  async function ranBy(turnId: string, user: TurnUser, person: PersonalPorts | null): Promise<{ mine: boolean | null; name?: string }> {
    const known = owners.get(turnId);
    if (known !== undefined) return { mine: sameUser(known, user), name: known.name };
    if (person?.history !== undefined) {
      for (const provider of PROVIDER_IDS) {
        try {
          if ((await person.history.load(provider)).some((record) => record.turnId === turnId)) return { mine: true };
        } catch {
          // An unreadable history proves nothing.
        }
      }
    }
    if (deps.turnOwner === undefined) return { mine: null };
    let owner: { id: string; name?: string } | null;
    try {
      owner = await deps.turnOwner(turnId);
    } catch {
      // Without an answer the turn may be anyone's: nobody but a proven owner may undo it.
      return { mine: false };
    }
    if (owner === null) return { mine: null };
    return { mine: user.role !== "host" && owner.id === user.id, ...(owner.name === undefined ? {} : { name: owner.name }) };
  }

  /** The host keeps undoing a turn of unknown origin, as before people existed; a collaborator only their own. */
  const allowed = (mine: boolean | null, user: TurnUser) => mine === true || (mine === null && user.role === "host");

  return {
    noteLogin: (provider, login, user = HOST_TURN_USER) => setLogin(user, provider, login),
    loginOf: (provider, user = HOST_TURN_USER) => logins.get(user.role === "host" ? HOST_TURN_USER.id : user.id)?.get(provider) ?? "unknown",
    busy: () => starting !== null || running(),
    async start({ provider, prompt, user = HOST_TURN_USER }) {
      if (starting !== null || running()) return { ok: false, error: { code: "busy", message: busyMessage(user) } };
      const person = personOf(user);
      if (person === null) return { ok: false, error: { code: "person_unavailable", message: "Collaborator turns are not set up in this server." } };
      starting = user;
      let runner: AgentRunnerPort;
      let model: string | null;
      let authMode: AuthMode = "account";
      let overrides: Turn["overrides"] = {};
      try {
        if (prompt.trim() === "") return { ok: false, error: { code: "invalid_prompt", message: "Write a message first." } };
        if (prompt.length > MAX_PROMPT_CHARS) {
          return { ok: false, error: { code: "invalid_prompt", message: `The message is too long (the limit is ${MAX_PROMPT_CHARS.toLocaleString("en-US")} characters).` } };
        }
        const found = runners[provider];
        if (found === undefined) return { ok: false, error: { code: "unknown_provider", message: `There is no adapter for ${provider}.` } };
        runner = found;
        let status;
        try {
          status = await runner.detect();
        } catch (error) {
          return { ok: false, error: { code: "not_installed", message: `${provider} could not be checked: ${errorText(error)}` } };
        }
        if (!status.installed) {
          return { ok: false, error: { code: "not_installed", message: status.unavailableReason ?? `${provider} is not installed.` } };
        }
        const saved = await person.state.load();
        model = saved.models[provider] ?? null;
        if (status.requiresModel && model === null) {
          return { ok: false, error: { code: "model_required", message: `Choose a model for ${provider} before sending a message.` } };
        }
        authMode = authModeOf(saved.authModes, provider);
        if (authMode === "api") {
          const refusal = await apiRefusal(provider, model, person.credentials);
          if (refusal !== null) return { ok: false, error: refusal };
        }
        if (user.role !== "host") {
          if (person.runEnv === undefined) return { ok: false, error: { code: "person_unavailable", message: "Collaborator turns are not set up in this server." } };
          let env;
          try {
            env = await person.runEnv(provider);
          } catch (error) {
            return { ok: false, error: { code: "person_unavailable", message: `Your private folder could not be prepared: ${errorText(error)}` } };
          }
          if (!env.ok) return { ok: false, error: { code: "person_unavailable", message: env.error.message } };
          const home = env.value["HOME"];
          if (home === undefined || !home.startsWith("/")) {
            return { ok: false, error: { code: "person_unavailable", message: "Your private folder could not be located, so your turn cannot run sandboxed." } };
          }
          overrides = { env: env.value, sandbox: { home }, ...(person.credentials === undefined ? {} : { credentials: person.credentials }) };
        }
      } finally {
        starting = null;
      }

      const turn: Turn = {
        id: newId(),
        provider,
        user,
        person,
        overrides,
        prompt,
        authMode,
        startedAt: now(),
        buffer: createReplayBuffer(),
        invalidReported: false,
        ended: false,
        controller: new AbortController(),
        subscribers: new Set(),
        finished: Promise.resolve(),
      };
      last = turn;
      owners.set(turn.id, user);
      turn.finished = execute(turn, runner, model)
        .catch((error: unknown) => {
          // Anything unforeseen still ends the turn with an error and a done.
          if (!turn.buffer.hasDone()) failTurn(turn, "provider_error", "The turn failed unexpectedly.", errorText(error));
        })
        .then(() => finish(turn));
      return { ok: true, value: { turnId: turn.id } };
    },

    stop(turnId, user = HOST_TURN_USER) {
      if (last === null || last.id !== turnId || last.ended || last.controller.signal.aborted || !sameUser(last.user, user)) return false;
      last.controller.abort();
      return true;
    },

    subscribe(turnId, subscriber, after = 0) {
      const turn = last;
      if (turn === null || turn.id !== turnId) return null;
      for (const entry of turn.buffer.after(after)) subscriber.onEvent(entry.event, entry.seq);
      if (turn.ended) {
        subscriber.onEnd();
        return () => {};
      }
      turn.subscribers.add(subscriber);
      return () => void turn.subscribers.delete(subscriber);
    },

    current: () => (last === null ? null : { turnId: last.id, provider: last.provider, running: !last.ended, owner: { id: last.user.id, name: last.user.name } }),

    async mayUndo(turnId, user = HOST_TURN_USER) {
      return allowed((await ranBy(turnId, user, personOf(user))).mine, user);
    },

    async undo(turnId, mode, user = HOST_TURN_USER) {
      if (starting !== null || running()) return { status: "busy" };
      const owner = await ranBy(turnId, user, personOf(user));
      if (!allowed(owner.mine, user)) {
        return { status: "not_yours", message: owner.name === undefined ? "Only the person who ran this turn can undo it." : `${owner.name} ran this turn, so only ${owner.name} can undo it.` };
      }
      const result = await snapshots.restore(turnId, mode);
      if (result.status === "restored") {
        for (const file of result.files) if (!reverted.includes(file)) reverted.push(file);
      }
      try {
        await deps.rescan();
      } catch {
        // The periodic rescan will catch up.
      }
      return result;
    },

    async resetSession(provider, user = HOST_TURN_USER) {
      if (starting !== null || running()) return false;
      const person = personOf(user);
      if (person === null) return false;
      const { sessions } = await person.state.load();
      const { [provider]: _forgotten, ...rest } = sessions;
      await person.state.update({ sessions: rest });
      await person.history?.clear(provider);
      return true;
    },

    async replaceDefinition(provider) {
      if (starting !== null || running()) return { ok: false, error: { code: "busy", message: "A turn is running. Try again when it has finished." } };
      const result = await provisioner.ensure(provider, { replace: true });
      if (!result.ok) return { ok: false, error: { code: "provision_failed", message: result.error.message } };
      return { ok: true, value: { outcomes: result.value.outcomes } };
    },

    async idle() {
      while (last !== null && !last.ended) await last.finished;
    },

    async shutdown() {
      if (last !== null && !last.ended) last.controller.abort();
      await this.idle();
    },
  };
}
