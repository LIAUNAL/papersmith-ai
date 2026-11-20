import {
  collaboratorEnv,
  createChatHistory,
  createCredentialStore,
  ensureUserHome,
  userHomePaths,
  type FileSystem,
} from "@caztor/adapters-local";
import { isSafeUserId, personalStateView, PROVIDER_IDS, type CredentialStorePort, type PeoplePort, type StatePort } from "@caztor/core";

/** One key store per collaborator for the whole server, so two saves of the same person are never interleaved. */
export function createCredentialStores(options: { fs: FileSystem; configHome: string; uid: number | null }): (userId: string) => CredentialStorePort {
  const stores = new Map<string, CredentialStorePort>();
  return (userId) => {
    let store = stores.get(userId);
    if (store === undefined) {
      store = createCredentialStore({ ...options, userId });
      stores.set(userId, store);
    }
    return store;
  };
}

export interface PeopleOptions {
  fs: FileSystem;
  /** Real path of the open project. */
  root: string;
  state: StatePort;
  /** Where every collaborator's private folder and keys live, outside every project. */
  configHome: string;
  uid: number | null;
  /** The server's environment; a collaborator's turn keeps only its harmless part. */
  env: Readonly<Record<string, string | undefined>>;
  credentialsOf: (userId: string) => CredentialStorePort;
}

/**
 * Each collaborator's own ports in one project: their choices in the project state, their conversation in their
 * private folder (outside the project), their key store and a turn environment pointing at their private home.
 */
export function createPeople(options: PeopleOptions): PeoplePort {
  const { fs, root, state, configHome, uid, env } = options;
  return (user) => {
    if (!isSafeUserId(user.id)) return null;
    return {
      state: personalStateView(state, user.id),
      history: createChatHistory({ fs, root, userId: user.id, configHome }),
      credentials: options.credentialsOf(user.id),
      async runEnv(provider) {
        const home = await ensureUserHome({ fs, configHome, uid, userId: user.id, projectRoot: root });
        return home.ok ? { ok: true, value: collaboratorEnv(env, home.value, provider) } : home;
      },
    };
  };
}

/**
 * Finds the collaborator who ran a turn of the project at `root` in the conversations kept in their private folders,
 * so a turn stays theirs after a restart. Null when no collaborator's conversation has it (the host's own turns, and
 * every turn of a project nobody else has used).
 */
export function createTurnOwners(options: { fs: FileSystem; root: string; configHome: string }): (turnId: string) => Promise<{ id: string } | null> {
  const { fs, root, configHome } = options;
  return async (turnId) => {
    let ids: string[];
    try {
      ids = (await fs.readdir(userHomePaths(configHome, "x").users)).filter((entry) => entry.isDirectory() && isSafeUserId(entry.name)).map((entry) => entry.name);
    } catch (error) {
      if ((error as { code?: string }).code === "ENOENT") return null;
      throw error;
    }
    for (const id of ids) {
      const history = createChatHistory({ fs, root, userId: id, configHome });
      for (const provider of PROVIDER_IDS) {
        if ((await history.load(provider)).some((record) => record.turnId === turnId)) return { id };
      }
    }
    return null;
  };
}
