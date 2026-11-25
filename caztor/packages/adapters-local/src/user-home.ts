import { createHash } from "node:crypto";
import { isSafeUserId } from "@caztor/core";
import type { ProviderId, Result } from "@caztor/core";
import type { FileSystem, FsStats } from "./infra.ts";

const DIR_MODE = 0o700;
const GROUP_OR_OTHER = 0o077;

/** Where a collaborator's own things live: `<configHome>/caztor/users/<userId>`, and their private home folder in it. */
export function userHomePaths(configHome: string, userId: string): { users: string; dir: string; home: string } {
  if (!isSafeUserId(userId)) throw new Error("The user id cannot name a folder.");
  const users = `${configHome.replace(/\/+$/, "")}/caztor/users`;
  const dir = `${users}/${userId}`;
  return { users, dir, home: `${dir}/home` };
}

/**
 * Where a collaborator's conversation in the project at `root` is kept: `<configHome>/caztor/users/<userId>/chat/<key>`,
 * the key a hash of the project's path. It is beside their private home, never inside it or the project, so no agent
 * turn, theirs included, has it mounted.
 */
export function userChatFolder(configHome: string, userId: string, root: string): string {
  const key = createHash("sha256").update(root.replace(/(.)\/+$/, "$1")).digest("hex").slice(0, 32);
  return `${userHomePaths(configHome, userId).dir}/chat/${key}`;
}

export interface UserHomeOptions {
  fs: FileSystem;
  configHome: string;
  /** The user id of this process. Null where the platform has none: the owner check is then skipped. */
  uid: number | null;
  userId: string;
  /** The open project: the private folder must never be inside it, where the project's files are shared. */
  projectRoot: string;
}

const refused = (message: string): Result<never, { message: string }> => ({ ok: false, error: { message } });

/**
 * Makes the collaborator's private folder, used as HOME and every CLI's configuration folder, when it is missing, and
 * checks every level of it: plain folders, no links, owned by this user and closed to everyone else.
 */
export async function ensureUserHome(options: UserHomeOptions): Promise<Result<string, { message: string }>> {
  const { fs, configHome, uid, projectRoot } = options;
  if (!isSafeUserId(options.userId)) return refused("The user id cannot name a folder.");
  const { users, dir, home } = userHomePaths(configHome, options.userId);
  const root = projectRoot.replace(/\/+$/, "");
  if (home === root || home.startsWith(`${root}/`)) return refused("Your private folder would be inside the project, where everyone sees its files, so Caztor does not use it.");
  try {
    await fs.mkdir(configHome, { recursive: true });
  } catch {
    return refused("Your private folder could not be created.");
  }
  for (const folder of [`${configHome.replace(/\/+$/, "")}/caztor`, users, dir, home]) {
    try {
      await fs.mkdir(folder, { mode: DIR_MODE });
    } catch (error) {
      if ((error as { code?: string }).code !== "EEXIST") return refused("Your private folder could not be created.");
    }
    let stats: FsStats;
    try {
      stats = await fs.lstat(folder);
    } catch {
      return refused("Your private folder could not be checked.");
    }
    if (stats.isSymbolicLink()) return refused("A folder of your private folder is a link, so Caztor does not use it.");
    if (!stats.isDirectory()) return refused("A part of your private folder is not a plain folder, so Caztor does not use it.");
    if (uid !== null && stats.uid !== uid) return refused("A folder of your private folder belongs to another user, so Caztor does not use it.");
    // The shared `caztor` folder is the host's; from `users` down, nobody else may reach the folders.
    if (folder !== `${configHome.replace(/\/+$/, "")}/caztor` && (stats.mode & GROUP_OR_OTHER) !== 0) {
      return refused("Your private folder can be reached by other users, so Caztor does not use it.");
    }
  }
  return { ok: true, value: home };
}

/** The host's variables a collaborator's turn keeps: finding programs, the locale, the network and certificates. Nothing that names a login. */
const KEPT_NAMES = [
  "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
  "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
] as const;

/**
 * The environment a collaborator's turn of `provider` starts from, in place of the server's: every CLI looks in the
 * private folder `home` for its login and settings. agy gets HOME alone, and no D-Bus or runtime folder, so its login
 * is written to a file there rather than to the host's keyring. The runner then keeps only the names its CLI needs.
 */
export function collaboratorEnv(parent: Readonly<Record<string, string | undefined>>, home: string, provider: ProviderId): Record<string, string> {
  const env: Record<string, string> = {};
  for (const name of KEPT_NAMES) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  env["HOME"] = home;
  if (provider === "antigravity") return env;
  return {
    ...env,
    CLAUDE_CONFIG_DIR: `${home}/.claude`,
    CODEX_HOME: `${home}/.codex`,
    XDG_CONFIG_HOME: `${home}/.config`,
    XDG_DATA_HOME: `${home}/.local/share`,
    XDG_STATE_HOME: `${home}/.local/state`,
    XDG_CACHE_HOME: `${home}/.cache`,
    PI_CODING_AGENT_DIR: `${home}/.pi/agent`,
  };
}
