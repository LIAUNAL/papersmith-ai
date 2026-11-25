import { chmodSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, utimesSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { nodeFileSystem } from "../src/node-infra.ts";
import {
  createUserStore,
  hashSecret,
  HOST_USER_ID,
  INVITE_DEFAULT_MINUTES,
  INVITE_MAX_FAILURES,
  INVITE_MAX_MINUTES,
  INVITE_MIN_MINUTES,
  normalizeAccessKey,
  userStorePaths,
} from "../src/user-store.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;

function setup(start = 1_000_000) {
  const configHome = realpathSync(mkdtempSync(join(tmpdir(), "caztor-users-")));
  dirs.push(configHome);
  let clock = start;
  const store = createUserStore({ fs: nodeFileSystem, configHome, uid: process.getuid?.() ?? null, now: () => clock, wait: async () => {} });
  const paths = userStorePaths(configHome);
  return { store, paths, configHome, advance: (ms: number) => (clock += ms), raw: () => readFileSync(paths.file, "utf8") };
}

async function invited(store: ReturnType<typeof setup>["store"], name = "Ana", minutes = INVITE_DEFAULT_MINUTES) {
  const made = await store.createInvite(name, minutes);
  if (!made.ok) throw new Error(made.error.message);
  return made.value;
}

async function signedIn(store: ReturnType<typeof setup>["store"], id: string, key: string) {
  const opened = await store.signIn(id, key);
  if (!opened.ok || opened.value === null) throw new Error("sign-in failed");
  return opened.value;
}

describe("user store", () => {
  it("lives in <configHome>/caztor/users.json, 0600 in a 0700 folder, and stores only hashes", async () => {
    const { store, paths, raw } = setup();
    const invite = await invited(store);
    const session = await signedIn(store, invite.id, invite.key);
    expect(statSync(paths.dir).mode & 0o777).toBe(0o700);
    expect(statSync(paths.file).mode & 0o777).toBe(0o600);
    const text = raw();
    expect(text).not.toContain(invite.key);
    expect(text).not.toContain(normalizeAccessKey(invite.key)!);
    expect(text).not.toContain(session.secret);
    expect(text).toContain(hashSecret(session.secret));
    expect(text).toContain(hashSecret(normalizeAccessKey(invite.key)!));
    expect(JSON.parse(text)).toMatchObject({
      version: 2,
      users: [{ name: "Ana", role: "collaborator", sessions: [{ hash: hashSecret(session.secret), inviteId: invite.id, expiresAt: invite.expiresAt }] }],
      invites: [{ id: invite.id, userId: invite.user.id, expiresAt: invite.expiresAt, failures: 0 }],
    });
  });

  it("makes a link id of at least 96 random bits and an easy-to-type key of at least 80", async () => {
    const { store } = setup();
    const first = await invited(store);
    const second = await invited(store);
    expect(first.id).toMatch(/^[A-Za-z0-9_-]{16,}$/);
    expect(first.id).not.toBe(second.id);
    // 4 groups of 5 from 32 unambiguous characters: 100 bits.
    expect(first.key).toMatch(/^[A-HJ-NP-Z2-9]{5}(-[A-HJ-NP-Z2-9]{5}){3}$/);
    expect(first.key).not.toBe(second.key);
    // The same name is the same collaborator, so a second invite attaches more browsers.
    expect(second.user.id).toBe(first.user.id);
  });

  it("accepts the key with or without dashes, in either case, and refuses other shapes", () => {
    expect(normalizeAccessKey("abcde-fgh23-jkmnp-qrst4")).toBe("ABCDEFGH23JKMNPQRST4");
    expect(normalizeAccessKey(" ABCDEFGH23JKMNPQRST4 ")).toBe("ABCDEFGH23JKMNPQRST4");
    expect(normalizeAccessKey("ABCDE FGH23 JKMNP QRST4")).toBe("ABCDEFGH23JKMNPQRST4");
    expect(normalizeAccessKey("ABCDE-FGH23-JKMNP-QRST")).toBeNull();
    expect(normalizeAccessKey("ABCDE-FGH23-JKMNP-QRSTO")).toBeNull();
    expect(normalizeAccessKey("")).toBeNull();
  });

  it("lets the host choose the lifetime, from 10 minutes to 365 days", async () => {
    const { store } = setup();
    expect((await invited(store, "Ana", 60)).expiresAt).toBe(1_000_000 + 60 * MINUTE);
    expect((await invited(store, "Ana", INVITE_MIN_MINUTES)).expiresAt).toBe(1_000_000 + 10 * MINUTE);
    expect((await invited(store, "Ana", INVITE_MAX_MINUTES)).expiresAt).toBe(1_000_000 + 365 * DAY);
    for (const minutes of [9, INVITE_MAX_MINUTES + 1, 1.5, Number.NaN, -60]) {
      expect(await store.createInvite("Ana", minutes)).toMatchObject({ ok: false, error: { code: "invalid_lifetime" } });
    }
  });

  it("signs in several browsers with the key until it expires, then refuses the key and ends those sessions", async () => {
    const { store, advance } = setup();
    const invite = await invited(store, "Ana", 60);
    const laptop = await signedIn(store, invite.id, invite.key);
    const phone = await signedIn(store, invite.id, invite.key.toLowerCase().replaceAll("-", ""));
    expect(laptop.secret).not.toBe(phone.secret);
    expect(await store.findSession(laptop.secret)).toEqual({ id: invite.user.id, name: "Ana", role: "collaborator" });
    expect(await store.findSession(phone.secret)).not.toBeNull();
    advance(60 * MINUTE);
    expect(await store.signIn(invite.id, invite.key)).toEqual({ ok: true, value: null });
    expect(await store.findSession(laptop.secret)).toBeNull();
    expect(await store.findSession(phone.secret)).toBeNull();
    const listed = await store.list();
    expect(listed.ok && listed.value[0]).toMatchObject({ sessions: 0, invites: [{ id: invite.id, status: "expired", sessions: 0 }] });
  });

  it("refuses a wrong key or an unknown link without saying which, and finds no forged session", async () => {
    const { store } = setup();
    const invite = await invited(store);
    const other = await invited(store, "Bo");
    expect(await store.signIn(invite.id, other.key)).toEqual({ ok: true, value: null });
    expect(await store.signIn("AAAAAAAAAAAAAAAAAAAAAA", invite.key)).toEqual({ ok: true, value: null });
    expect(await store.signIn(invite.id, "not a key")).toEqual({ ok: true, value: null });
    expect(await store.findSession("forged")).toBeNull();
    expect(await store.findSession("")).toBeNull();
  });

  it("locks an invite after 10 wrong keys, so even the right key no longer works", async () => {
    const { store } = setup();
    const invite = await invited(store);
    const wrong = (await invited(store, "Bo")).key;
    for (let attempt = 1; attempt < INVITE_MAX_FAILURES; attempt += 1) expect((await store.signIn(invite.id, wrong)).ok).toBe(true);
    const listedBefore = await store.list();
    expect(listedBefore.ok && listedBefore.value[0]!.invites[0]).toMatchObject({ status: "active", failures: 9 });
    await store.signIn(invite.id, wrong);
    expect(await store.signIn(invite.id, invite.key)).toEqual({ ok: true, value: null });
    const listed = await store.list();
    expect(listed.ok && listed.value[0]!.invites[0]).toMatchObject({ status: "locked", failures: 10 });
  });

  it("revokes one key with its sessions, leaving the person's other keys", async () => {
    const { store } = setup();
    const laptop = await invited(store);
    const phone = await invited(store);
    const first = await signedIn(store, laptop.id, laptop.key);
    const second = await signedIn(store, phone.id, phone.key);
    expect(await store.revokeInvite(laptop.id)).toEqual({ ok: true, value: undefined });
    expect(await store.findSession(first.secret)).toBeNull();
    expect(await store.signIn(laptop.id, laptop.key)).toEqual({ ok: true, value: null });
    expect(await store.findSession(second.secret)).not.toBeNull();
    expect(await store.revokeInvite(laptop.id)).toMatchObject({ ok: false, error: { code: "not_found" } });
    const listed = await store.list();
    expect(listed.ok && listed.value[0]!.invites.map((entry) => entry.id)).toEqual([phone.id]);
  });

  it("revokes a collaborator with their sessions and invites, and never the host", async () => {
    const { store, raw } = setup();
    const invite = await invited(store);
    const session = await signedIn(store, invite.id, invite.key);
    const host = await store.createHostSession();
    if (!host.ok) throw new Error("host failed");
    expect(await store.revoke(invite.user.id)).toEqual({ ok: true, value: undefined });
    expect(await store.findSession(session.secret)).toBeNull();
    expect(await store.signIn(invite.id, invite.key)).toEqual({ ok: true, value: null });
    expect(JSON.parse(raw()).invites).toEqual([]);
    expect((await store.revoke(HOST_USER_ID)).ok).toBe(false);
    expect((await store.revoke("missing")).ok).toBe(false);
    expect(await store.findSession(host.value.secret)).toEqual({ id: HOST_USER_ID, name: "Host", role: "host" });
  });

  it("lists users with their sessions and every key's expiry", async () => {
    const { store } = setup();
    const invite = await invited(store, "Ana", 60);
    await signedIn(store, invite.id, invite.key);
    expect(await store.list()).toEqual({
      ok: true,
      value: [
        {
          id: invite.user.id,
          name: "Ana",
          role: "collaborator",
          createdAt: 1_000_000,
          sessions: 1,
          invites: [{ id: invite.id, createdAt: 1_000_000, expiresAt: 1_000_000 + 60 * MINUTE, status: "active", failures: 0, sessions: 1 }],
        },
      ],
    });
  });

  it("refuses an invalid name", async () => {
    const { store } = setup();
    expect(await store.createInvite("  ", 60)).toMatchObject({ ok: false, error: { code: "invalid_name" } });
    expect(await store.createInvite("../x", 60)).toMatchObject({ ok: false, error: { code: "invalid_name" } });
  });

  it("sees a change another process wrote, so a revoke from the CLI signs the browser out at once", async () => {
    const { store, configHome } = setup();
    const other = createUserStore({ fs: nodeFileSystem, configHome, uid: process.getuid?.() ?? null, now: () => 1_000_000 });
    const invite = await invited(store);
    const session = await signedIn(store, invite.id, invite.key);
    expect(await other.findSession(session.secret)).not.toBeNull();
    expect((await other.revoke(invite.user.id)).ok).toBe(true);
    expect(await store.findSession(session.secret)).toBeNull();
  });

  it("waits for a held lock, takes over one left behind, and leaves no lock file", async () => {
    const { store, paths } = setup(Date.now());
    mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
    writeFileSync(paths.lock, "123\n");
    const old = (Date.now() - 60_000) / 1000;
    utimesSync(paths.lock, old, old);
    expect((await store.createInvite("Ana", 60)).ok).toBe(true);
    expect(() => statSync(paths.lock)).toThrow();
  });

  it("refuses a store other users can read and never overwrites a corrupt one", async () => {
    const { store, paths } = setup();
    mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
    writeFileSync(paths.file, "{ not json", { mode: 0o600 });
    expect(await store.createInvite("Ana", 60)).toMatchObject({ ok: false, error: { code: "corrupt" } });
    expect(readFileSync(paths.file, "utf8")).toBe("{ not json");
    writeFileSync(paths.file, JSON.stringify({ version: 2, users: [], invites: [] }));
    chmodSync(paths.file, 0o644);
    expect(await store.list()).toMatchObject({ ok: false, error: { code: "unsafe" } });
  });

  describe("a store of the first version", () => {
    function writeOld(paths: ReturnType<typeof userStorePaths>) {
      mkdirSync(paths.dir, { recursive: true, mode: 0o700 });
      const old = {
        version: 1,
        users: [
          { id: "u-ana", name: "Ana", role: "collaborator", createdAt: 5, sessions: [{ hash: hashSecret("old-session-secret"), createdAt: 6 }] },
          { id: HOST_USER_ID, name: "Host", role: "host", createdAt: 5, sessions: [{ hash: hashSecret("old-host-secret"), createdAt: 6 }] },
        ],
        invites: [{ hash: hashSecret("old-one-time-code"), userId: "u-ana", expiresAt: 1_000_000 + 3 * DAY }],
      };
      writeFileSync(paths.file, `${JSON.stringify(old)}\n`, { mode: 0o600 });
    }

    it("loads, keeps its sessions valid, and reports its unused invite as an old one", async () => {
      const { store, paths, raw } = setup();
      writeOld(paths);
      expect(await store.findSession("old-session-secret")).toEqual({ id: "u-ana", name: "Ana", role: "collaborator" });
      expect(await store.findSession("old-host-secret")).toEqual({ id: HOST_USER_ID, name: "Host", role: "host" });
      const listed = await store.list();
      expect(listed.ok && listed.value.find((user) => user.id === "u-ana")).toMatchObject({ sessions: 1, invites: [{ status: "old", expiresAt: 1_000_000 + 3 * DAY }] });
      // Reading never rewrites the file.
      expect(JSON.parse(raw()).version).toBe(1);
    });

    it("refuses the old one-time code, and writes the new format on the next change", async () => {
      const { store, paths, raw } = setup();
      writeOld(paths);
      const listed = await store.list();
      const old = listed.ok ? listed.value.find((user) => user.id === "u-ana")!.invites[0]! : null;
      expect(await store.signIn(old!.id, "old-one-time-code")).toEqual({ ok: true, value: null });
      await invited(store, "Bo");
      const written = JSON.parse(raw()) as { version: number; users: Array<{ id: string; sessions: unknown[] }>; invites: Array<{ id: string; legacy?: boolean }> };
      expect(written.version).toBe(2);
      expect(written.users.find((user) => user.id === "u-ana")!.sessions).toEqual([{ hash: hashSecret("old-session-secret"), createdAt: 6 }]);
      expect(written.invites.find((entry) => entry.id === old!.id)).toMatchObject({ legacy: true });
      expect(await store.findSession("old-session-secret")).not.toBeNull();
      expect((await store.revokeInvite(old!.id)).ok).toBe(true);
    });
  });
});
