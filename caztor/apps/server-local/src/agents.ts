import { createProjectAgents,
  createBuiltInGuideSource,
  createChatHistory,
  createProvisioner,
  defaultGuidesDir,
  defaultLicensePath,
  createSnapshotStore,
  defaultAgentsDir,
  type FileSystem,
  type ProjectStore,
  type UserWriteLog,
  createAgentsMdVisibility,
} from "@caztor/adapters-local";
import type { ApiDeps } from "@caztor/api";
import { createTurnService, withFallback, type AgentRunnerPort, type CredentialStorePort, type GuideSourcePort, type PeoplePort, type ProviderId, type StatePort } from "@caztor/core";

export interface AgentServicesOptions {
  fs: FileSystem;
  /** Real path of the project folder. */
  root: string;
  /** The same store the file routes use, created with `userWrites`, so a save during a turn is attributed to the user. */
  store: ProjectStore;
  state: StatePort;
  clock: { now(): number; setTimeout(fn: () => void, ms: number): () => void };
  userWrites: UserWriteLog;
  runners: Partial<Record<ProviderId, AgentRunnerPort>>;
  /** Tells the turn service whether an API key is stored; without it a turn in api mode is refused. */
  credentials?: Pick<CredentialStorePort, "status">;
  /** Each collaborator's own state, history, keys and run environment. */
  people?: PeoplePort;
  /** The collaborator who ran a turn, from their kept conversation; keeps undo theirs after a restart. */
  turnOwner?: (turnId: string) => Promise<{ id: string; name?: string } | null>;
  /** Where the shipped agent definitions are; defaults to the repository's `agents` folder. */
  agentsDir?: string;
  /** A different source for the writing guides, tried first; the built-in guides stay the fallback. */
  guides?: GuideSourcePort;
  /** Replaces the built-in guides, which come from the repository's `guides` folder. */
  builtInGuides?: GuideSourcePort;
}

/** Wires the turn service to the real snapshot store, provisioner and chat history of one project. */
export function createAgentServices(options: AgentServicesOptions): NonNullable<ApiDeps["agents"]> {
  const { fs, root, store, state, clock, userWrites, runners } = options;
  const snapshots = createSnapshotStore({
    fs,
    root,
    store,
    clock,
    skipAgentsMd: createAgentsMdVisibility({ fs, root, state }),
  });
  const builtIn = options.builtInGuides ?? createBuiltInGuideSource({ fs, guidesDir: defaultGuidesDir(), licensePath: defaultLicensePath() });
  const guides = options.guides === undefined ? builtIn : withFallback(options.guides, builtIn);
  const provisioner = createProvisioner({ fs, root, state, store, agentsDir: options.agentsDir ?? defaultAgentsDir(), guides });
  const history = createChatHistory({ fs, root });
  const projectAgents = createProjectAgents({ fs, root });
  const turns = createTurnService({
    runners,
    provisioner,
    snapshots,
    state,
    userWrites,
    rescan: () => store.rescan(),
    history,
    projectAgents,
    ...(options.credentials === undefined ? {} : { credentials: options.credentials }),
    ...(options.people === undefined ? {} : { people: options.people }),
    ...(options.turnOwner === undefined ? {} : { turnOwner: options.turnOwner }),
  });
  return { turns, history, runners, undoable: () => snapshots.undoable(), projectAgents };
}
