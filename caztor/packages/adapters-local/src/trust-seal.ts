import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import type { ProviderId } from "@caztor/core";
import type { FileSystem } from "./infra.ts";

/**
 * Turns the host's confirmation of a project's CLI configuration into a record that only this server can make. The
 * fingerprint alone is a plain hash of the files, which anyone who can write the project could compute and store; the
 * seal is an HMAC with a secret kept in Caztor's own configuration folder (0600, never mounted in any sandbox).
 */
export interface TrustSeal {
  /** The value to store for this provider's configuration with this fingerprint. */
  seal(provider: ProviderId, fingerprint: string): Promise<string>;
  /** Whether `stored` is this server's seal of exactly this provider and fingerprint. */
  holds(provider: ProviderId, fingerprint: string, stored: string | undefined): Promise<boolean>;
}

const PREFIX = "hmac1:";
const KEY_BYTES = 32;

export interface TrustSealOptions {
  fs: FileSystem;
  /** Caztor's configuration home; the key is `<configHome>/caztor/trust.key`. Null keeps a key in memory only. */
  configHome: string | null;
  uid: number | null;
  /** Real path of the project: a seal holds only in the project it was made for. */
  root: string;
}

/** Where the seal key lives. */
export const trustKeyPath = (configHome: string) => `${configHome.replace(/\/+$/, "")}/caztor/trust.key`;

/** One key per server process, shared by every project. Reading it is cheap, so the file is the source of truth. */
export function createTrustKey(options: Omit<TrustSealOptions, "root">): () => Promise<Uint8Array | null> {
  const { fs, configHome, uid } = options;
  let memory: Uint8Array | null = null;
  let pending: Promise<Uint8Array | null> | null = null;

  async function load(): Promise<Uint8Array | null> {
    if (configHome === null) return (memory ??= new Uint8Array(randomBytes(KEY_BYTES)));
    const file = trustKeyPath(configHome);
    try {
      await fs.mkdir(file.slice(0, file.lastIndexOf("/")), { recursive: true, mode: 0o700 });
      await fs.writeFile(file, new TextEncoder().encode(randomBytes(KEY_BYTES).toString("base64url")), { exclusive: true, mode: 0o600 });
    } catch (error) {
      if ((error as { code?: string }).code !== "EEXIST") {
        // No writable configuration folder: a key in memory, so a confirmation lasts until the server stops.
        return (memory ??= new Uint8Array(randomBytes(KEY_BYTES)));
      }
    }
    try {
      const stats = await fs.lstat(file);
      // A key someone else could read or replace would let them forge the record, so nothing is trusted with it.
      if (stats.isSymbolicLink() || !stats.isFile() || (stats.mode & 0o077) !== 0 || (uid !== null && stats.uid !== uid)) return null;
      const text = new TextDecoder().decode(await fs.readFile(file)).trim();
      return text.length >= 32 ? new TextEncoder().encode(text) : null;
    } catch {
      return null;
    }
  }

  return () => (pending ??= load().finally(() => void (pending = null)));
}

export function createTrustSeal(options: TrustSealOptions & { key?: () => Promise<Uint8Array | null> }): TrustSeal {
  const key = options.key ?? createTrustKey(options);
  const root = options.root.replace(/(.)\/+$/, "$1");
  const mac = (secret: Uint8Array, provider: ProviderId, fingerprint: string) =>
    PREFIX + createHmac("sha256", secret).update(`caztor-project-config\0${root}\0${provider}\0${fingerprint}`).digest("base64url");

  return {
    async seal(provider, fingerprint) {
      const secret = await key();
      if (secret === null) throw new Error("Caztor's trust key cannot be used, so the confirmation cannot be kept.");
      return mac(secret, provider, fingerprint);
    },
    async holds(provider, fingerprint, stored) {
      if (stored === undefined || !stored.startsWith(PREFIX)) return false;
      const secret = await key();
      if (secret === null) return false;
      const expected = new TextEncoder().encode(mac(secret, provider, fingerprint));
      const given = new TextEncoder().encode(stored);
      return expected.length === given.length && timingSafeEqual(expected, given);
    },
  };
}
