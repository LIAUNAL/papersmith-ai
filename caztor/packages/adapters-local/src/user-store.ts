import { createHash, randomBytes, randomUUID, timingSafeEqual } from "node:crypto";
import type { Result } from "@caztor/core";
import type { FileSystem, FsStats } from "./infra.ts";

const STORE_DIR = "caztor";
const STORE_FILE = "users.json";
const LOCK_FILE = "users.json.lock";
const DIR_MODE = 0o700;
const FILE_MODE = 0o600;
const GROUP_OR_OTHER = 0o077;
/** Version 2: invites are a link id plus an access key, with a lifetime the host picks. Version 1 is read and migrated. */
const STORE_VERSION = 2;
const MINUTE_MS = 60_000;
/** The lifetimes the host may pick, in minutes: 10 minutes to 365 days, 7 days when none is given. */
export const INVITE_MIN_MINUTES = 10;
export const INVITE_MAX_MINUTES = 365 * 24 * 60;
export const INVITE_DEFAULT_MINUTES = 7 * 24 * 60;
/** Wrong keys an invite takes before it locks, so even the right key no longer signs anyone in. */
export const INVITE_MAX_FAILURES = 10;
/** How long an expired or locked invite stays listed for the host before it goes from the store. */
const KEEP_ENDED_MS = 30 * 24 * 60 * MINUTE_MS;
/** How long a first-version invite lasted, to give it a creation time. */
const OLD_INVITE_TTL_MS = 7 * 24 * 60 * MINUTE_MS;
/** 16 random bytes (128 bits) for the link id, 32 for session secrets; both base64url. */
const INVITE_ID_BYTES = 16;
const SECRET_BYTES = 32;
/** The access key: 4 groups of 5 characters from 32 that cannot be mistaken for each other (no I, O, 0 or 1), 100 bits. */
const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const KEY_GROUPS = 4;
const KEY_GROUP_LENGTH = 5;
const KEY_LENGTH = KEY_GROUPS * KEY_GROUP_LENGTH;
const KEY_SHAPE = new RegExp(`^[${KEY_ALPHABET}]{${KEY_LENGTH}}$`);
/** A lock older than this was left by a process that died while holding it. */
const STALE_LOCK_MS = 10_000;
const LOCK_RETRY_MS = 25;
const LOCK_WAIT_MS = 3_000;
/** The host is one fixed record, so its sessions survive restarts and it can never be revoked. */
export const HOST_USER_ID = "host";
const HOST_NAME = "Host";
const USER_NAME = /^[\p{L}\p{N}][\p{L}\p{N} .'_-]{0,59}$/u;

export type UserRole = "host" | "collaborator";

/**
 * Where an access key stands: `active` signs in, `expired` reached its end, `locked` took too many wrong keys, and
 * `old` is a one-time link of the first version, which no longer works.
 */
export type InviteStatus = "active" | "expired" | "locked" | "old";

export interface InviteView {
  /** The id in the link. Not a secret: the key is. */
  id: string;
  createdAt: number;
  expiresAt: number;
  status: InviteStatus;
  /** Wrong keys tried so far. */
  failures: number;
  /** Browsers signed in with this key now. */
  sessions: number;
}

export interface UserView {
  id: string;
  name: string;
  role: UserRole;
  createdAt: number;
  /** How many browsers are signed in as this user. */
  sessions: number;
  /** Their access keys, active or ended, oldest first. */
  invites: InviteView[];
}

export interface UserStoreError {
  code: "invalid_name" | "invalid_lifetime" | "not_found" | "host_refused" | "io" | "busy" | "unsafe" | "corrupt";
  message: string;
}

export interface UserStore {
  /** The user a raw session secret belongs to, or null when no session matches or the key it came from expired. */
  findSession(secret: string): Promise<{ id: string; name: string; role: UserRole } | null>;
  list(): Promise<Result<UserView[], UserStoreError>>;
  /**
   * Finds the collaborator with this name, or adds one, and makes an invite for them that lasts `minutes`: a link id
   * and an access key. The raw key is returned once and never stored.
   */
  createInvite(name: string, minutes: number): Promise<Result<{ user: UserView; id: string; key: string; expiresAt: number }, UserStoreError>>;
  /**
   * Opens a session for the invite's user when the key is right and the invite is neither expired nor locked; the
   * session ends when the invite does. A wrong key counts toward the invite's lock. Null when it cannot be used,
   * without saying why.
   */
  signIn(inviteId: string, key: string): Promise<Result<{ secret: string; user: UserView } | null, UserStoreError>>;
  /** Opens a session for the host. */
  createHostSession(): Promise<Result<{ secret: string; user: UserView }, UserStoreError>>;
  /** Removes one access key and ends the sessions opened with it. */
  revokeInvite(inviteId: string): Promise<Result<void, UserStoreError>>;
  /** Removes a collaborator with their sessions and invites, so every browser of theirs is signed out at once. */
  revoke(id: string): Promise<Result<void, UserStoreError>>;
}

export interface UserStoreOptions {
  fs: FileSystem;
  /** The same configuration area the key store uses; the users live in `<configHome>/caztor/users.json`. */
  configHome: string;
  /** The user id of this process. Null where the platform has none: the owner check is then skipped. */
  uid: number | null;
  now?: () => number;
  /** Pause while another process holds the lock. Tests replace it. */
  wait?: (ms: number) => Promise<void>;
}

interface StoredSession {
  hash: string;
  createdAt: number;
  /** The invite the session was opened with; absent for the host's and for sessions of the first version. */
  inviteId?: string;
  /** The end of that invite: the session ends with it. Absent: until revoked. */
  expiresAt?: number;
}
interface StoredUser {
  id: string;
  name: string;
  role: UserRole;
  createdAt: number;
  sessions: StoredSession[];
}
interface StoredInvite {
  id: string;
  /** SHA-256 of the access key in its plain form (`normalizeAccessKey`). */
  hash: string;
  userId: string;
  createdAt: number;
  expiresAt: number;
  failures: number;
  /** A one-time link of the first version: listed so the host knows to send a new one, never accepted. */
  legacy?: true;
}
interface Stored {
  users: StoredUser[];
  invites: StoredInvite[];
}

export function userStorePaths(configHome: string): { dir: string; file: string; lock: string } {
  const dir = `${configHome.replace(/\/+$/, "")}/${STORE_DIR}`;
  return { dir, file: `${dir}/${STORE_FILE}`, lock: `${dir}/${LOCK_FILE}` };
}

/** SHA-256 of a secret, hex. Only this ever reaches the disk. */
export function hashSecret(secret: string): string {
  return createHash("sha256").update(secret, "utf8").digest("hex");
}

/**
 * The plain form of an access key: upper case, without dashes or spaces. Null for anything that is not a key's shape,
 * so a typo never reaches the store.
 */
export function normalizeAccessKey(typed: string): string | null {
  const plain = typed.replace(/[\s-]+/g, "").toUpperCase();
  return KEY_SHAPE.test(plain) ? plain : null;
}

/** A new access key, grouped for typing: `ABCDE-FGH23-JKMNP-QRST4`. 32 characters divide 256, so every one is equally likely. */
function newAccessKey(): string {
  const bytes = randomBytes(KEY_LENGTH);
  const plain = Array.from(bytes, (byte) => KEY_ALPHABET[byte % KEY_ALPHABET.length]).join("");
  return plain.match(new RegExp(`.{${KEY_GROUP_LENGTH}}`, "g"))!.join("-");
}

/** The link id of an invite: base64url, at least 96 bits. */
const INVITE_ID = /^[A-Za-z0-9_-]{16,64}$/;

function sameHash(a: string, b: string): boolean {
  const left = Buffer.from(a, "utf8");
  const right = Buffer.from(b, "utf8");
  return left.length === right.length && timingSafeEqual(left, right);
}

const fail = (code: UserStoreError["code"], message: string): Result<never, UserStoreError> => ({ ok: false, error: { code, message } });
const isMissing = (error: unknown): boolean => (error as { code?: string }).code === "ENOENT";
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isString = (value: unknown): value is string => typeof value === "string";

function parseSession(session: Record<string, unknown> | undefined): StoredSession | null {
  if (!isString(session?.["hash"]) || !isNumber(session?.["createdAt"])) return null;
  const parsed: StoredSession = { hash: session["hash"], createdAt: session["createdAt"] };
  const { inviteId, expiresAt } = session;
  if (inviteId !== undefined) {
    if (!isString(inviteId)) return null;
    parsed.inviteId = inviteId;
  }
  if (expiresAt !== undefined) {
    if (!isNumber(expiresAt)) return null;
    parsed.expiresAt = expiresAt;
  }
  return parsed;
}

function parseInvite(entry: Record<string, unknown> | undefined, version: number): StoredInvite | null {
  if (!isString(entry?.["hash"]) || !isString(entry?.["userId"]) || !isNumber(entry?.["expiresAt"])) return null;
  const { hash, userId, expiresAt } = entry as { hash: string; userId: string; expiresAt: number };
  // A first-version invite was a one-time code in the link. It keeps a listing under a made-up id and never signs in.
  if (version === 1) return { id: `old-${hash.slice(0, 22)}`, hash, userId, createdAt: expiresAt - OLD_INVITE_TTL_MS, expiresAt, failures: 0, legacy: true };
  const { id, createdAt, failures, legacy } = entry as Record<string, unknown>;
  if (!isString(id) || !isNumber(createdAt) || !isNumber(failures) || (legacy !== undefined && legacy !== true)) return null;
  return { id, hash, userId, createdAt, expiresAt, failures, ...(legacy === true ? { legacy: true as const } : {}) };
}

function parseFile(text: string): Stored | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  const record = raw as { version?: unknown; users?: unknown; invites?: unknown } | null;
  if (typeof record !== "object" || record === null || (record.version !== 1 && record.version !== STORE_VERSION)) return null;
  const version = record.version;
  if (!Array.isArray(record.users) || !Array.isArray(record.invites)) return null;
  const users: StoredUser[] = [];
  for (const entry of record.users as Array<Record<string, unknown>>) {
    const { id, name, role, createdAt, sessions } = entry ?? {};
    if (!isString(id) || !isString(name) || (role !== "host" && role !== "collaborator") || !isNumber(createdAt) || !Array.isArray(sessions)) return null;
    const parsed: StoredSession[] = [];
    for (const session of sessions as Array<Record<string, unknown>>) {
      const one = parseSession(session);
      if (one === null) return null;
      parsed.push(one);
    }
    users.push({ id, name, role, createdAt, sessions: parsed });
  }
  const invites: StoredInvite[] = [];
  for (const entry of record.invites as Array<Record<string, unknown>>) {
    const one = parseInvite(entry, version);
    if (one === null) return null;
    invites.push(one);
  }
  return { users, invites };
}

/**
 * The people who may use this Caztor, outside every project. Only SHA-256 hashes of session secrets and access keys
 * are stored. A first-version file is read as it is and written in the current format on the next change. The folder and file are checked like the key store's: plain, owned by this user, closed to everyone else.
 * Writes take a lock file, so the CLI and the running server can both change the store; reads see a write at once.
 */
export function createUserStore(options: UserStoreOptions): UserStore {
  const { fs, configHome, uid } = options;
  const now = options.now ?? Date.now;
  const wait = options.wait ?? ((ms: number) => new Promise<void>((done) => setTimeout(done, ms)));
  const { dir, file, lock } = userStorePaths(configHome);
  let queue: Promise<unknown> = Promise.resolve();
  let cache: { signature: string; stored: Stored } | null = null;

  const serial = <T>(run: () => Promise<T>): Promise<T> => {
    const result = queue.then(run, run);
    queue = result.catch(() => {});
    return result;
  };

  const unsafe = (what: string) => fail("unsafe", `The Caztor users ${what} must be a plain ${what} owned by you and closed to other users (chmod ${what === "folder" ? "700" : "600"}).`);

  function refuse(stats: FsStats, what: "folder" | "file"): Result<never, UserStoreError> | null {
    if (stats.isSymbolicLink() || (what === "folder" ? !stats.isDirectory() : !stats.isFile())) return unsafe(what);
    if (uid !== null && stats.uid !== uid) return unsafe(what);
    if ((stats.mode & GROUP_OR_OTHER) !== 0) return unsafe(what);
    return null;
  }

  async function load(): Promise<Result<Stored, UserStoreError>> {
    const empty: Stored = { users: [], invites: [] };
    try {
      const refusal = refuse(await fs.lstat(dir), "folder");
      if (refusal !== null) return refusal;
    } catch (error) {
      return isMissing(error) ? { ok: true, value: empty } : fail("io", "The users folder could not be checked.");
    }
    let stats: FsStats;
    try {
      stats = await fs.lstat(file);
    } catch (error) {
      return isMissing(error) ? { ok: true, value: empty } : fail("io", "The users file could not be checked.");
    }
    const refusal = refuse(stats, "file");
    if (refusal !== null) return refusal;
    const signature = `${stats.id}:${stats.size}:${stats.mtimeMs}:${stats.ctimeMs}`;
    if (cache?.signature === signature) return { ok: true, value: structuredClone(cache.stored) };
    let text: string;
    try {
      text = new TextDecoder().decode(await fs.readFile(file));
    } catch {
      return fail("io", "The users file could not be read.");
    }
    const stored = parseFile(text);
    if (stored === null) return fail("corrupt", `The Caztor users file (${file}) cannot be read, so Caztor does not change it. Fix or remove the file.`);
    cache = { signature, stored };
    return { ok: true, value: structuredClone(stored) };
  }

  async function ensureDir(): Promise<Result<void, UserStoreError>> {
    try {
      await fs.mkdir(configHome, { recursive: true });
      await fs.mkdir(dir, { mode: DIR_MODE });
    } catch (error) {
      if ((error as { code?: string }).code !== "EEXIST") return fail("io", "The users folder could not be created.");
    }
    try {
      return refuse(await fs.lstat(dir), "folder") ?? { ok: true, value: undefined };
    } catch {
      return fail("io", "The users folder could not be checked.");
    }
  }

  /** Takes the lock file, waiting while another process holds it and removing one left by a process that died. */
  async function acquire(): Promise<Result<() => Promise<void>, UserStoreError>> {
    const started = now();
    for (;;) {
      try {
        await fs.writeFile(lock, new TextEncoder().encode(`${process.pid}\n`), { exclusive: true, mode: FILE_MODE });
        return { ok: true, value: () => fs.rm(lock, { force: true }).catch(() => {}) };
      } catch (error) {
        if ((error as { code?: string }).code !== "EEXIST") return fail("io", "The users lock could not be taken.");
      }
      const held = await fs.lstat(lock).catch(() => null);
      if (held !== null && now() - held.mtimeMs > STALE_LOCK_MS) {
        await fs.rm(lock, { force: true }).catch(() => {});
        continue;
      }
      if (now() - started > LOCK_WAIT_MS) return fail("busy", "Another Caztor is changing the users right now. Try again.");
      await wait(LOCK_RETRY_MS);
    }
  }

  async function save(stored: Stored): Promise<Result<void, UserStoreError>> {
    const temp = `${dir}/${STORE_FILE}.${randomUUID()}.tmp`;
    try {
      await fs.writeFile(temp, new TextEncoder().encode(`${JSON.stringify({ version: STORE_VERSION, ...stored }, null, 2)}\n`), { exclusive: true, mode: FILE_MODE });
      await fs.rename(temp, file);
      return { ok: true, value: undefined };
    } catch {
      await fs.rm(temp, { force: true }).catch(() => {});
      return fail("io", "The users could not be saved.");
    }
  }

  /**
   * Reads, changes and writes the store under the lock. Sessions whose key expired are dropped on every write, and
   * invites a month after they expired.
   */
  function change<T>(edit: (stored: Stored) => Result<T, UserStoreError>): Promise<Result<T, UserStoreError>> {
    return serial(async () => {
      const prepared = await ensureDir();
      if (!prepared.ok) return prepared;
      const locked = await acquire();
      if (!locked.ok) return locked;
      try {
        const loaded = await load();
        if (!loaded.ok) return loaded;
        const stored = loaded.value;
        const at = now();
        stored.invites = stored.invites.filter((invite) => invite.expiresAt + KEEP_ENDED_MS > at);
        for (const user of stored.users) user.sessions = user.sessions.filter((session) => sessionLive(session, at));
        const outcome = edit(stored);
        if (!outcome.ok) return outcome;
        const saved = await save(stored);
        return saved.ok ? outcome : saved;
      } finally {
        await locked.value();
      }
    });
  }

  const sessionLive = (session: StoredSession, at: number) => session.expiresAt === undefined || session.expiresAt > at;

  function statusOf(invite: StoredInvite, at: number): InviteStatus {
    if (invite.legacy === true) return "old";
    if (invite.expiresAt <= at) return "expired";
    return invite.failures >= INVITE_MAX_FAILURES ? "locked" : "active";
  }

  function viewOf(stored: Stored, user: StoredUser): UserView {
    const at = now();
    const live = user.sessions.filter((session) => sessionLive(session, at));
    return {
      id: user.id,
      name: user.name,
      role: user.role,
      createdAt: user.createdAt,
      sessions: live.length,
      invites: stored.invites
        .filter((invite) => invite.userId === user.id)
        .map((invite) => ({
          id: invite.id,
          createdAt: invite.createdAt,
          expiresAt: invite.expiresAt,
          status: statusOf(invite, at),
          failures: invite.failures,
          sessions: live.filter((session) => session.inviteId === invite.id).length,
        })),
    };
  }

  const newSecret = (bytes: number) => randomBytes(bytes).toString("base64url");

  function openSession(stored: Stored, user: StoredUser, invite?: StoredInvite): { secret: string; user: UserView } {
    const secret = newSecret(SECRET_BYTES);
    user.sessions.push({ hash: hashSecret(secret), createdAt: now(), ...(invite === undefined ? {} : { inviteId: invite.id, expiresAt: invite.expiresAt }) });
    return { secret, user: viewOf(stored, user) };
  }

  return {
    async findSession(secret) {
      if (secret === "") return null;
      const loaded = await load();
      if (!loaded.ok) return null;
      const hash = hashSecret(secret);
      const at = now();
      for (const user of loaded.value.users) {
        if (user.sessions.some((session) => sameHash(session.hash, hash) && sessionLive(session, at))) return { id: user.id, name: user.name, role: user.role };
      }
      return null;
    },

    list: () =>
      serial(async () => {
        const loaded = await load();
        if (!loaded.ok) return loaded;
        return { ok: true, value: loaded.value.users.map((user) => viewOf(loaded.value, user)) };
      }),

    createInvite(wanted, minutes) {
      const name = wanted.trim();
      if (!USER_NAME.test(name)) return Promise.resolve(fail("invalid_name", "Use a name of up to 60 letters, digits, spaces, dots, apostrophes, dashes or underscores."));
      if (!Number.isInteger(minutes) || minutes < INVITE_MIN_MINUTES || minutes > INVITE_MAX_MINUTES) {
        return Promise.resolve(fail("invalid_lifetime", "Choose how long the key lasts: from 10 minutes to 365 days."));
      }
      return change((stored) => {
        let user = stored.users.find((entry) => entry.role === "collaborator" && entry.name.toLowerCase() === name.toLowerCase());
        if (user === undefined) {
          user = { id: randomUUID(), name, role: "collaborator", createdAt: now(), sessions: [] };
          stored.users.push(user);
        }
        const id = newSecret(INVITE_ID_BYTES);
        const key = newAccessKey();
        const expiresAt = now() + minutes * MINUTE_MS;
        stored.invites.push({ id, hash: hashSecret(normalizeAccessKey(key)!), userId: user.id, createdAt: now(), expiresAt, failures: 0 });
        return { ok: true, value: { user: viewOf(stored, user), id, key, expiresAt } };
      });
    },

    async signIn(inviteId, typed) {
      if (!INVITE_ID.test(inviteId)) return { ok: true, value: null };
      // An unknown link is answered without taking the lock or writing, so guessing ids changes nothing on disk.
      const peek = await load();
      if (!peek.ok) return peek;
      if (!peek.value.invites.some((entry) => entry.id === inviteId)) return { ok: true, value: null };
      const plain = normalizeAccessKey(typed);
      return change((stored) => {
        const invite = stored.invites.find((entry) => entry.id === inviteId);
        const user = invite === undefined ? undefined : stored.users.find((entry) => entry.id === invite.userId);
        if (invite === undefined || user === undefined || statusOf(invite, now()) !== "active") return { ok: true, value: null };
        if (plain === null || !sameHash(invite.hash, hashSecret(plain))) {
          invite.failures += 1;
          return { ok: true, value: null };
        }
        return { ok: true, value: openSession(stored, user, invite) };
      });
    },

    revokeInvite: (inviteId) =>
      change((stored) => {
        const invite = stored.invites.find((entry) => entry.id === inviteId);
        if (invite === undefined) return fail("not_found", "There is no access key with that id.");
        stored.invites = stored.invites.filter((entry) => entry !== invite);
        for (const user of stored.users) user.sessions = user.sessions.filter((session) => session.inviteId !== inviteId);
        return { ok: true, value: undefined };
      }),

    createHostSession: () =>
      change((stored) => {
        let host = stored.users.find((entry) => entry.id === HOST_USER_ID);
        if (host === undefined) {
          host = { id: HOST_USER_ID, name: HOST_NAME, role: "host", createdAt: now(), sessions: [] };
          stored.users.push(host);
        }
        return { ok: true, value: openSession(stored, host) };
      }),

    revoke: (id) =>
      change((stored) => {
        const user = stored.users.find((entry) => entry.id === id);
        if (id === HOST_USER_ID || user?.role === "host") return fail("host_refused", "The host cannot be revoked.");
        if (user === undefined) return fail("not_found", "There is no collaborator with that id.");
        stored.users = stored.users.filter((entry) => entry !== user);
        stored.invites = stored.invites.filter((invite) => invite.userId !== id);
        return { ok: true, value: undefined };
      }),
  };
}
