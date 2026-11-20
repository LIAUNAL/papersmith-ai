import type { ChatHistoryPort } from "./chat-history.ts";
import type { CredentialStorePort, PersonalState, ProjectState, ProviderId, Result, StatePort } from "./ports.ts";

/** Who asks for a turn or a setting: the host, or a collaborator signed in with a cookie session. */
export interface TurnUser {
  id: string;
  name: string;
  role: "host" | "collaborator";
}

/** The fixed id of the host. The host's state stays where a single-user project keeps it. */
export const HOST_PERSON_ID = "host";

export const HOST_TURN_USER: TurnUser = { id: HOST_PERSON_ID, name: "Host", role: "host" };

/** The fields that belong to each person; every other field of the project state is shared. */
export const PERSONAL_KEYS = ["selectedProvider", "authModes", "models", "sessions"] as const satisfies readonly (keyof ProjectState)[];

const SAFE_USER_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

/** A collaborator id that may name a folder: one plain segment, never the host's. */
export function isSafeUserId(value: unknown): value is string {
  return typeof value === "string" && SAFE_USER_ID.test(value) && value !== HOST_PERSON_ID;
}

export function defaultPersonalState(): PersonalState {
  return { selectedProvider: null, authModes: {}, models: {}, sessions: {} };
}

const isPersonalKey = (key: string): key is (typeof PERSONAL_KEYS)[number] => (PERSONAL_KEYS as readonly string[]).includes(key);

/**
 * The project state as one person sees it. The host's view is the store itself. A collaborator's view reads and writes
 * the personal fields under `users[<id>]` and shares every other field with everyone.
 */
export function personalStateView(state: StatePort, userId: string): StatePort {
  if (userId === HOST_PERSON_ID) return state;
  if (!isSafeUserId(userId)) throw new Error("The user id cannot name a folder.");
  const merge = (full: ProjectState): ProjectState => ({ ...full, ...(full.users?.[userId] ?? defaultPersonalState()) });
  const edit = (current: ProjectState, patch: Partial<ProjectState>): Partial<ProjectState> => {
    const shared: Partial<ProjectState> = {};
    const mine: PersonalState = { ...defaultPersonalState(), ...(current.users?.[userId] ?? {}) };
    let personal = false;
    for (const [key, value] of Object.entries(patch) as Array<[keyof ProjectState, unknown]>) {
      if (key === "users") continue;
      if (isPersonalKey(key)) {
        (mine as unknown as Record<string, unknown>)[key] = value;
        personal = true;
      } else (shared as Record<string, unknown>)[key] = value;
    }
    return personal ? { ...shared, users: { ...(current.users ?? {}), [userId]: mine } } : shared;
  };
  return {
    load: async () => merge(await state.load()),
    async update(patch) {
      // A store that applies an edit atomically keeps two people's writes from losing each other.
      if (state.change !== undefined) return merge(await state.change((current) => edit(current, patch)));
      return merge(await state.update(edit(await state.load(), patch)));
    },
  };
}

/** What a person's turns and settings use. */
export interface PersonalPorts {
  state: StatePort;
  history?: ChatHistoryPort;
  credentials?: CredentialStorePort;
  /** The environment a collaborator's turn of this provider runs with, pointing every CLI at their private folder. */
  runEnv?(provider: ProviderId): Promise<Result<Readonly<Record<string, string | undefined>>, { message: string }>>;
}

/** The ports of a collaborator, or null when theirs cannot be used. Not used for the host, whose ports are the service's own. */
export type PeoplePort = (user: TurnUser) => PersonalPorts | null;
