import { describe, expect, it } from "vitest";
import { createTrustKey, createTrustSeal, trustKeyPath } from "../src/trust-seal.ts";
import { MemoryFileSystem } from "./fakes/memory-fs.ts";

const FINGERPRINT = `sha256:${"a".repeat(64)}`;
const CONFIG = "/home/u/.config";

describe("the trust seal of a project's CLI configuration", () => {
  it("is not the fingerprint, holds for exactly the provider, fingerprint and project it was made for", async () => {
    const fs = new MemoryFileSystem({});
    const key = createTrustKey({ fs, configHome: CONFIG, uid: null });
    const seal = createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one", key });
    const sealed = await seal.seal("claude", FINGERPRINT);
    expect(sealed).toMatch(/^hmac1:/);
    expect(sealed).not.toContain(FINGERPRINT);
    expect(await seal.holds("claude", FINGERPRINT, sealed)).toBe(true);
    expect(await seal.holds("opencode", FINGERPRINT, sealed)).toBe(false);
    expect(await seal.holds("claude", `sha256:${"b".repeat(64)}`, sealed)).toBe(false);
    expect(await createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/two", key }).holds("claude", FINGERPRINT, sealed)).toBe(false);
  });

  it("does not take the plain fingerprint, which anyone who writes the project can compute, nor a record of the old format", async () => {
    const fs = new MemoryFileSystem({});
    const seal = createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" });
    expect(await seal.holds("claude", FINGERPRINT, FINGERPRINT)).toBe(false);
    expect(await seal.holds("claude", FINGERPRINT, undefined)).toBe(false);
    expect(await seal.holds("claude", FINGERPRINT, "hmac1:forged")).toBe(false);
  });

  it("keeps its key in Caztor's configuration folder, readable only by this user, so a confirmation survives a restart", async () => {
    const fs = new MemoryFileSystem({});
    const first = await createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" }).seal("claude", FINGERPRINT);
    expect((await fs.stat(trustKeyPath(CONFIG))).mode & 0o077).toBe(0);
    expect(await createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" }).holds("claude", FINGERPRINT, first)).toBe(true);
  });

  it("trusts nothing with a key that others can read or that is a link", async () => {
    const fs = new MemoryFileSystem({});
    const sealed = await createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" }).seal("claude", FINGERPRINT);
    await fs.chmod(trustKeyPath(CONFIG), 0o644);
    expect(await createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" }).holds("claude", FINGERPRINT, sealed)).toBe(false);
    await fs.rm(trustKeyPath(CONFIG));
    await fs.writeFile("/elsewhere", new TextEncoder().encode("x".repeat(43)), { mode: 0o600 });
    fs.symlink("/elsewhere", trustKeyPath(CONFIG));
    await expect(createTrustSeal({ fs, configHome: CONFIG, uid: null, root: "/p/one" }).seal("claude", FINGERPRINT)).rejects.toThrow(/trust key/);
  });
});
