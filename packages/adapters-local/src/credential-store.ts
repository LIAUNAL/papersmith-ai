import { isSafeUserId, lastFour, parseApiKey, parseCredentialSlot } from "@caztor/core";
import type { CredentialError, CredentialSlot, CredentialStatus, CredentialStorePort, Result } from "@caztor/core";
import type { FileSystem, FsStats } from "./infra.ts";

const STORE_DIR = "caztor";
const STORE_FILE = "credentials.json";
const DIR_MODE = 0o700;
const FILE_MODE = 0o600;
const GROUP_OR_OTHER = 0o077;
const STORE_VERSION = 1;

export interface CredentialStoreOptions {
  fs: FileSystem;
  /** Absolute path of the user's configuration area; the store lives in `<configHome>/caztor/credentials.json`. */
  configHome: string;
  /** The user id of this process. Null where the platform has none: the owner check is then skipped. */
  uid: number | null;
  /** A collaborator's id: their store is `<configHome>/caztor/users/<userId>/credentials.json`. Missing for the host. */
  userId?: string;
}

/** `$XDG_CONFIG_HOME` when it is absolute, else `$HOME/.config`; null when neither gives an absolute path. */
export function credentialConfigHome(env: Readonly<Record<string, string | undefined>>): string | null {
  const xdg = env["XDG_CONFIG_HOME"];
  if (xdg !== undefined && xdg.startsWith("/")) return xdg.replace(/\/+$/, "") || "/";
  const home = env["HOME"];
  if (home !== undefined && home.startsWith("/")) return `${home.replace(/\/+$/, "")}/.config`;
  return null;
}

/** Where the host's store is, or a collaborator's when `userId` is given. */
export function credentialPaths(configHome: string, userId?: string): { dir: string; file: string } {
  if (userId !== undefined && !isSafeUserId(userId)) throw new Error("The user id cannot name a folder.");
  const base = `${configHome.replace(/\/+$/, "")}/${STORE_DIR}`;
  const dir = userId === undefined ? base : `${base}/users/${userId}`;
  return { dir, file: `${dir}/${STORE_FILE}` };
}

const fail = (code: CredentialError["code"], message: string): Result<never, CredentialError> => ({ ok: false, error: { code, message } });
const isMissing = (error: unknown): boolean => (error as { code?: string }).code === "ENOENT";

type Keys = Record<CredentialSlot, string>;

function parseFile(text: string): Keys | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const { version, keys } = raw as { version?: unknown; keys?: unknown };
  if (version !== STORE_VERSION || typeof keys !== "object" || keys === null || Array.isArray(keys)) return null;
  const out: Keys = {};
  for (const [slot, key] of Object.entries(keys)) {
    if (typeof key !== "string") return null;
    out[slot] = key;
  }
  return out;
}

const statusOf = (slot: CredentialSlot, key: string | undefined): CredentialStatus => {
  if (key === undefined) return { slot, set: false };
  const last4 = lastFour(key);
  return { slot, set: true, ...(last4 === undefined ? {} : { last4 }) };
};

/**
 * The file that holds the API keys, outside every project. It is checked before each use: the folder and the file must
 * be plain (no links), owned by this user and closed to everyone else. A file that cannot be parsed is never overwritten.
 * Failures carry fixed messages, never the text of the system's error, so a key cannot travel with them.
 */
export function createCredentialStore(options: CredentialStoreOptions): CredentialStorePort {
  const { fs, configHome, uid, userId } = options;
  const { dir, file } = credentialPaths(configHome, userId);
  /** The folder of every collaborator's folder: checked like the store's own, since a link there would move it. */
  const usersDir = userId === undefined ? null : `${credentialPaths(configHome).dir}/users`;
  let queue: Promise<unknown> = Promise.resolve();

  /** Runs one operation at a time, so two saves never lose each other's key. */
  const serial = <T>(run: () => Promise<T>): Promise<T> => {
    const result = queue.then(run, run);
    queue = result.catch(() => {});
    return result;
  };

  const ioProblem = (what: string): Result<never, CredentialError> => fail("io", `${what} The stored keys could not be reached.`);

  /** Null when the object is acceptable, else the refusal. */
  function refuse(stats: FsStats, what: "folder" | "file", path: string): Result<never, CredentialError> | null {
    if (stats.isSymbolicLink()) return fail("linked", `The Caztor key ${what} (${path}) is a symbolic link, so Caztor does not use it. Replace the link with a plain ${what}.`);
    if (what === "folder" ? !stats.isDirectory() : !stats.isFile()) return fail("io", `The Caztor key ${what} (${path}) is not a plain ${what}, so Caztor does not use it.`);
    if (uid !== null && stats.uid !== uid) return fail("unsafe_owner", `The Caztor key ${what} (${path}) belongs to another user, so Caztor does not use it.`);
    if ((stats.mode & GROUP_OR_OTHER) !== 0) {
      return fail("unsafe_permissions", `The Caztor key ${what} (${path}) can be reached by other users. Run chmod ${what === "folder" ? "700" : "600"} on it, then try again.`);
    }
    return null;
  }

  /** The stored keys, `null` when there is no store yet, or why they cannot be used. */
  async function load(): Promise<Result<Keys | null, CredentialError>> {
    if (usersDir !== null) {
      let users: FsStats;
      try {
        users = await fs.lstat(usersDir);
      } catch (error) {
        return isMissing(error) ? { ok: true, value: null } : ioProblem("The key folder could not be checked.");
      }
      const usersRefusal = refuse(users, "folder", usersDir);
      if (usersRefusal !== null) return usersRefusal;
    }
    let folder: FsStats;
    try {
      folder = await fs.lstat(dir);
    } catch (error) {
      return isMissing(error) ? { ok: true, value: null } : ioProblem("The key folder could not be checked.");
    }
    const folderRefusal = refuse(folder, "folder", dir);
    if (folderRefusal !== null) return folderRefusal;
    let stats: FsStats;
    try {
      stats = await fs.lstat(file);
    } catch (error) {
      return isMissing(error) ? { ok: true, value: null } : ioProblem("The key file could not be checked.");
    }
    const fileRefusal = refuse(stats, "file", file);
    if (fileRefusal !== null) return fileRefusal;
    let text: string;
    try {
      text = new TextDecoder().decode(await fs.readFile(file));
    } catch {
      return ioProblem("The key file could not be read.");
    }
    const keys = parseFile(text);
    if (keys === null) return fail("corrupt", `The Caztor key file (${file}) cannot be read, so Caztor does not use it and does not change it. Fix or remove the file.`);
    return { ok: true, value: keys };
  }

  /** Makes the folder when it is missing; its checks have already passed when it exists. */
  async function ensureDir(): Promise<Result<void, CredentialError>> {
    const folders = usersDir === null ? [dir] : [credentialPaths(configHome).dir, usersDir, dir];
    try {
      await fs.mkdir(configHome, { recursive: true });
    } catch {
      return ioProblem("The key folder could not be created.");
    }
    for (const folder of folders) {
      try {
        await fs.mkdir(folder, { mode: DIR_MODE });
      } catch (error) {
        if ((error as { code?: string }).code !== "EEXIST") return ioProblem("The key folder could not be created.");
      }
    }
    if (usersDir !== null) {
      try {
        const refusal = refuse(await fs.lstat(usersDir), "folder", usersDir);
        if (refusal !== null) return refusal;
      } catch {
        return ioProblem("The key folder could not be checked.");
      }
    }
    try {
      const refusal = refuse(await fs.lstat(dir), "folder", dir);
      return refusal ?? { ok: true, value: undefined };
    } catch {
      return ioProblem("The key folder could not be checked.");
    }
  }

  /** Writes the whole file to a new private file and renames it over the old one. */
  async function save(keys: Keys): Promise<Result<void, CredentialError>> {
    const prepared = await ensureDir();
    if (!prepared.ok) return prepared;
    const temp = `${dir}/${STORE_FILE}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temp, new TextEncoder().encode(`${JSON.stringify({ version: STORE_VERSION, keys }, null, 2)}\n`), { exclusive: true, mode: FILE_MODE });
      await fs.rename(temp, file);
      return { ok: true, value: undefined };
    } catch {
      await fs.rm(temp, { force: true }).catch(() => {});
      return ioProblem("The key could not be saved.");
    }
  }

  const slotOf = (slot: string): Result<CredentialSlot, CredentialError> => {
    const known = parseCredentialSlot(slot);
    return known === null ? fail("invalid", "That is not a key slot Caztor knows.") : { ok: true, value: known };
  };

  return {
    read: (slot) =>
      serial(async () => {
        const known = slotOf(slot);
        if (!known.ok) return known;
        const loaded = await load();
        if (!loaded.ok) return loaded;
        return { ok: true, value: loaded.value?.[known.value] ?? null };
      }),

    status: (slot) =>
      serial(async () => {
        const known = slotOf(slot);
        if (!known.ok) return known;
        const loaded = await load();
        if (!loaded.ok) return loaded;
        return { ok: true, value: statusOf(known.value, loaded.value?.[known.value]) };
      }),

    list: () =>
      serial(async () => {
        const loaded = await load();
        if (!loaded.ok) return loaded;
        return { ok: true, value: Object.entries(loaded.value ?? {}).map(([slot, key]) => statusOf(slot, key)) };
      }),

    set: (slot, key) =>
      serial(async () => {
        const known = slotOf(slot);
        if (!known.ok) return known;
        const parsed = parseApiKey(key);
        if (!parsed.ok) return fail("invalid", parsed.error.message);
        const loaded = await load();
        if (!loaded.ok) return loaded;
        const saved = await save({ ...(loaded.value ?? {}), [known.value]: parsed.value });
        return saved.ok ? { ok: true, value: statusOf(known.value, parsed.value) } : saved;
      }),

    clear: (slot) =>
      serial(async () => {
        const known = slotOf(slot);
        if (!known.ok) return known;
        const loaded = await load();
        if (!loaded.ok) return loaded;
        if (loaded.value === null || loaded.value[known.value] === undefined) return { ok: true, value: statusOf(known.value, undefined) };
        const { [known.value]: _removed, ...rest } = loaded.value;
        const saved = await save(rest);
        return saved.ok ? { ok: true, value: statusOf(known.value, undefined) } : saved;
      }),
  };
}
