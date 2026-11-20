import type { CredentialStorePort } from "@caztor/core";
import { describe, expect, it, vi } from "vitest";
import { createCredentialStore, credentialPaths, credentialConfigHome } from "../src/credential-store.ts";
import type { FileSystem } from "../src/infra.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

cleanupSandboxes();

const nodeFsStub = {} as FileSystem;

const KEY = "sk-abcdef1234";
const OTHER_KEY = "sk-zzzzzzzz9876";
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
const encode = (text: string) => new TextEncoder().encode(text);

/** A file system whose named method fails with a message that contains the key, as a hostile provider could. */
function failing(fs: FileSystem, method: keyof FileSystem, message: string): FileSystem {
  return new Proxy(fs, {
    get(target, property) {
      if (property === method) return () => Promise.reject(Object.assign(new Error(message), { code: "EIO" }));
      const value = Reflect.get(target, property) as unknown;
      return typeof value === "function" ? (value as (...args: unknown[]) => unknown).bind(target) : value;
    },
  });
}

describe.each(implementations)("credential store: %s", (_name, create) => {
  async function setup(wrap: (fs: FileSystem) => FileSystem = (fs) => fs) {
    const box = create();
    const configHome = `${box.root}/config`;
    await box.fs.mkdir(configHome, { recursive: true });
    const uid = (await box.fs.lstat(configHome)).uid;
    const { dir, file } = credentialPaths(configHome);
    const store = (overrides: { uid?: number | null } = {}): CredentialStorePort =>
      createCredentialStore({ fs: wrap(box.fs), configHome, uid: overrides.uid === undefined ? uid : overrides.uid });
    const plant = async (text: string, mode = 0o600) => {
      await box.fs.mkdir(dir, { recursive: true, mode: 0o700 });
      await box.fs.chmod(dir, 0o700);
      await box.fs.writeFile(file, encode(text), { mode });
      await box.fs.chmod(file, mode);
    };
    const names = async () => (await box.fs.readdir(dir)).map((entry) => entry.name).sort();
    return { ...box, configHome, uid, dir, file, store, plant, names };
  }

  describe("saving and reading", () => {
    it("creates the folder as 0700 and the file as 0600 on the first save, with the key only inside the file", async () => {
      const t = await setup();
      const saved = await t.store().set("claude", KEY);

      expect(saved).toEqual({ ok: true, value: { slot: "claude", set: true, last4: "1234" } });
      expect((await t.fs.lstat(t.dir)).mode).toBe(0o700);
      expect((await t.fs.lstat(t.file)).mode).toBe(0o600);
      expect(JSON.parse(decode(await t.fs.readFile(t.file)))).toEqual({ version: 1, keys: { claude: KEY } });
      expect(await t.names()).toEqual(["credentials.json"]);
    });

    it("creates missing parents of the configuration folder", async () => {
      const t = await setup();
      const deep = createCredentialStore({ fs: t.fs, configHome: `${t.root}/a/b/config`, uid: t.uid });
      expect(await deep.set("codex", KEY)).toMatchObject({ ok: true });
      expect(decode(await t.fs.readFile(`${t.root}/a/b/config/caztor/credentials.json`))).toContain(KEY);
    });

    it("reads back what was saved, and null for a slot without a key, without creating anything", async () => {
      const t = await setup();
      expect(await t.store().read("claude")).toEqual({ ok: true, value: null });
      await expect(t.fs.lstat(t.dir)).rejects.toMatchObject({ code: "ENOENT" });

      await t.store().set("claude", KEY);
      await t.store().set("opencode:openai", OTHER_KEY);
      expect(await t.store().read("claude")).toEqual({ ok: true, value: KEY });
      expect(await t.store().read("opencode:openai")).toEqual({ ok: true, value: OTHER_KEY });
      expect(await t.store().read("codex")).toEqual({ ok: true, value: null });
    });

    it("shows the last four characters only for a key of twelve or more characters", async () => {
      const t = await setup();
      expect(await t.store().set("claude", "x".repeat(11) + "7")).toEqual({ ok: true, value: { slot: "claude", set: true, last4: "xxx7" } });
      const short = await t.store().set("codex", "sk-abc12345");
      expect(short).toEqual({ ok: true, value: { slot: "codex", set: true } });
      expect(await t.store().status("codex")).toEqual({ ok: true, value: { slot: "codex", set: true } });
    });

    it("reports status and the list of slots without any key", async () => {
      const t = await setup();
      expect(await t.store().status("claude")).toEqual({ ok: true, value: { slot: "claude", set: false } });
      expect(await t.store().list()).toEqual({ ok: true, value: [] });

      await t.store().set("claude", KEY);
      await t.store().set("opencode:groq", OTHER_KEY);
      expect(await t.store().status("claude")).toEqual({ ok: true, value: { slot: "claude", set: true, last4: "1234" } });
      const listed = await t.store().list();
      expect(listed).toEqual({
        ok: true,
        value: expect.arrayContaining([
          { slot: "claude", set: true, last4: "1234" },
          { slot: "opencode:groq", set: true, last4: "9876" },
        ]),
      });
      expect(JSON.stringify(listed)).not.toContain(KEY);
      expect(JSON.stringify(listed)).not.toContain(OTHER_KEY);
    });

    it("replaces a key and deletes it, so the old value is gone", async () => {
      const t = await setup();
      await t.store().set("claude", KEY);
      await t.store().set("claude", OTHER_KEY);
      expect(await t.store().read("claude")).toEqual({ ok: true, value: OTHER_KEY });
      expect(decode(await t.fs.readFile(t.file))).not.toContain(KEY);

      expect(await t.store().clear("claude")).toEqual({ ok: true, value: { slot: "claude", set: false } });
      expect(await t.store().read("claude")).toEqual({ ok: true, value: null });
      expect(decode(await t.fs.readFile(t.file))).not.toContain(OTHER_KEY);
    });

    it("clears a slot that has no key, and one when there is no store, without writing", async () => {
      const t = await setup();
      expect(await t.store().clear("claude")).toEqual({ ok: true, value: { slot: "claude", set: false } });
      await expect(t.fs.lstat(t.dir)).rejects.toMatchObject({ code: "ENOENT" });
    });

    it("keeps the other keys when one is saved or deleted, also when two saves overlap", async () => {
      const t = await setup();
      const store = t.store();
      await Promise.all([store.set("claude", KEY), store.set("codex", OTHER_KEY), store.set("opencode:xai", "xai-key-000111")]);
      expect(await store.read("claude")).toEqual({ ok: true, value: KEY });
      expect(await store.read("codex")).toEqual({ ok: true, value: OTHER_KEY });
      await store.clear("claude");
      expect(await store.read("codex")).toEqual({ ok: true, value: OTHER_KEY });
      expect(await store.read("opencode:xai")).toEqual({ ok: true, value: "xai-key-000111" });
    });

    it("refuses a slot that is not one of the known ones and a key of the wrong shape, writing nothing", async () => {
      const t = await setup();
      expect(await t.store().set("../escape", KEY)).toMatchObject({ ok: false, error: { code: "invalid" } });
      expect(await t.store().set("claude", "has a space")).toMatchObject({ ok: false, error: { code: "invalid" } });
      expect(await t.store().read("opencode:unknown")).toMatchObject({ ok: false, error: { code: "invalid" } });
      await expect(t.fs.lstat(t.dir)).rejects.toMatchObject({ code: "ENOENT" });
    });
  });

  describe("permissions and ownership", () => {
    it.each([0o640, 0o604, 0o644, 0o660])("refuses a key file with mode %o for reading and saving, and leaves it unchanged", async (mode) => {
      const t = await setup();
      const body = JSON.stringify({ version: 1, keys: { claude: KEY } });
      await t.plant(body, mode);

      for (const result of [await t.store().read("claude"), await t.store().set("claude", OTHER_KEY), await t.store().status("claude"), await t.store().clear("claude")]) {
        expect(result).toMatchObject({ ok: false, error: { code: "unsafe_permissions" } });
        expect(JSON.stringify(result)).not.toContain(KEY);
      }
      expect(decode(await t.fs.readFile(t.file))).toBe(body);
      expect((await t.fs.lstat(t.file)).mode).toBe(mode);
    });

    it.each([0o750, 0o705, 0o755])("refuses a folder with mode %o and does not change it", async (mode) => {
      const t = await setup();
      await t.plant(JSON.stringify({ version: 1, keys: { claude: KEY } }));
      await t.fs.chmod(t.dir, mode);

      expect(await t.store().read("claude")).toMatchObject({ ok: false, error: { code: "unsafe_permissions" } });
      expect(await t.store().set("claude", OTHER_KEY)).toMatchObject({ ok: false, error: { code: "unsafe_permissions" } });
      expect((await t.fs.lstat(t.dir)).mode).toBe(mode);
      expect(decode(await t.fs.readFile(t.file))).toContain(KEY);
    });

    it("refuses a folder or file that belongs to another user", async () => {
      const t = await setup();
      await t.plant(JSON.stringify({ version: 1, keys: { claude: KEY } }));
      const stranger = t.uid + 1;

      expect(await t.store({ uid: stranger }).read("claude")).toMatchObject({ ok: false, error: { code: "unsafe_owner" } });
      expect(await t.store({ uid: stranger }).set("claude", OTHER_KEY)).toMatchObject({ ok: false, error: { code: "unsafe_owner" } });
      expect(decode(await t.fs.readFile(t.file))).toContain(KEY);
    });

    it("skips the owner check where the platform has no user ids", async () => {
      const t = await setup();
      await t.plant(JSON.stringify({ version: 1, keys: { claude: KEY } }));
      expect(await t.store({ uid: null }).read("claude")).toEqual({ ok: true, value: KEY });
    });
  });

  describe("links", () => {
    it("refuses a folder that is a symbolic link and writes nothing through it", async () => {
      const t = await setup();
      const elsewhere = `${t.root}/elsewhere`;
      await t.fs.mkdir(elsewhere, { recursive: true });
      await t.fs.chmod(elsewhere, 0o700);
      t.symlink(elsewhere, t.dir);

      expect(await t.store().set("claude", KEY)).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(await t.store().read("claude")).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(await t.store().status("claude")).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(await t.fs.readdir(elsewhere)).toEqual([]);
    });

    it("refuses a key file that is a symbolic link and leaves its target unchanged", async () => {
      const t = await setup();
      await t.fs.mkdir(t.dir, { recursive: true, mode: 0o700 });
      await t.fs.chmod(t.dir, 0o700);
      const target = `${t.root}/target.json`;
      await t.fs.writeFile(target, encode('{"version":1,"keys":{}}'), { mode: 0o600 });
      await t.fs.chmod(target, 0o600);
      t.symlink(target, t.file);

      expect(await t.store().set("claude", KEY)).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(await t.store().read("claude")).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(decode(await t.fs.readFile(target))).toBe('{"version":1,"keys":{}}');
    });
  });

  describe("a file that cannot be used", () => {
    it.each([
      ["not JSON", "this is not json"],
      ["an empty file", ""],
      ["an unknown version", JSON.stringify({ version: 2, keys: {} })],
      ["keys that are not text", JSON.stringify({ version: 1, keys: { claude: 7 } })],
      ["no keys object", JSON.stringify({ version: 1 })],
      ["a JSON array", "[]"],
    ])("treats %s as corrupt: every operation is refused and the file is never overwritten", async (_label, body) => {
      const t = await setup();
      await t.plant(body);

      for (const result of [await t.store().read("claude"), await t.store().status("claude"), await t.store().list(), await t.store().set("claude", KEY), await t.store().clear("claude")]) {
        expect(result).toMatchObject({ ok: false, error: { code: "corrupt", message: expect.any(String) } });
      }
      expect(decode(await t.fs.readFile(t.file))).toBe(body);
      expect(await t.names()).toEqual(["credentials.json"]);
    });

    it("does not show the content of a corrupt file in the refusal", async () => {
      const t = await setup();
      await t.plant(`garbage ${KEY}`);
      expect(JSON.stringify(await t.store().read("claude"))).not.toContain(KEY);
    });
  });

  describe("failures while saving", () => {
    it("removes the temporary file and keeps the old content when the rename fails, without echoing the key", async () => {
      const t = await setup();
      const body = JSON.stringify({ version: 1, keys: { claude: KEY } });
      await t.plant(body);

      const hostile = createCredentialStore({ fs: failing(t.fs, "rename", `disk said no for ${OTHER_KEY}`), configHome: t.configHome, uid: t.uid });
      const logged: string[] = [];
      const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation((...args: unknown[]) => void logged.push(args.map(String).join(" "))));
      const saved = await hostile.set("claude", OTHER_KEY);
      for (const spy of spies) spy.mockRestore();

      expect(logged.join("\n")).not.toContain(OTHER_KEY);
      expect(saved).toMatchObject({ ok: false, error: { code: "io" } });
      expect(JSON.stringify(saved)).not.toContain(OTHER_KEY);
      expect(JSON.stringify(saved)).not.toContain(KEY);
      expect(await t.names()).toEqual(["credentials.json"]);
      expect(decode(await t.fs.readFile(t.file))).toBe(body);
    });

    it("reports a read that fails without the text of the failure", async () => {
      const t = await setup();
      await t.plant(JSON.stringify({ version: 1, keys: { claude: KEY } }));
      const hostile = createCredentialStore({ fs: failing(t.fs, "readFile", `cannot read ${KEY}`), configHome: t.configHome, uid: t.uid });
      const read = await hostile.read("claude");
      expect(read).toMatchObject({ ok: false, error: { code: "io" } });
      expect(JSON.stringify(read)).not.toContain(KEY);
    });
  });
  describe("a collaborator's store", () => {
    it("lives in their own folder, 0700 and 0600, apart from the host's", async () => {
      const t = await setup();
      const alice = createCredentialStore({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1" });
      expect(credentialPaths(t.configHome, "alice-1")).toEqual({ dir: `${t.configHome}/caztor/users/alice-1`, file: `${t.configHome}/caztor/users/alice-1/credentials.json` });
      expect(await alice.set("claude", KEY)).toMatchObject({ ok: true });
      expect(await t.store().set("claude", OTHER_KEY)).toMatchObject({ ok: true });
      expect(await alice.read("claude")).toEqual({ ok: true, value: KEY });
      expect(await t.store().read("claude")).toEqual({ ok: true, value: OTHER_KEY });
      const own = credentialPaths(t.configHome, "alice-1");
      expect((await t.fs.lstat(own.dir)).mode).toBe(0o700);
      expect((await t.fs.lstat(`${t.configHome}/caztor/users`)).mode).toBe(0o700);
      expect((await t.fs.lstat(own.file)).mode).toBe(0o600);
      expect(decode(await t.fs.readFile(t.file))).not.toContain(KEY);
    });

    it("refuses a hostile user id", () => {
      for (const userId of ["..", "a/b", "host", ""]) expect(() => createCredentialStore({ fs: nodeFsStub, configHome: "/c", uid: null, userId })).toThrow(/user id/i);
    });

    it("refuses a users folder that is a link", async () => {
      const t = await setup();
      await t.fs.mkdir(`${t.configHome}/caztor`, { mode: 0o700 });
      await t.fs.mkdir(`${t.root}/elsewhere`, { mode: 0o700 });
      t.symlink(`${t.root}/elsewhere`, `${t.configHome}/caztor/users`);
      const alice = createCredentialStore({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1" });
      expect(await alice.set("claude", KEY)).toMatchObject({ ok: false, error: { code: "linked" } });
      expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
    });
  });
});

describe("credentialConfigHome", () => {
  it("prefers an absolute XDG_CONFIG_HOME, then HOME/.config", () => {
    expect(credentialConfigHome({ XDG_CONFIG_HOME: "/xdg", HOME: "/home/u" })).toBe("/xdg");
    expect(credentialConfigHome({ HOME: "/home/u" })).toBe("/home/u/.config");
    expect(credentialConfigHome({ HOME: "/home/u/" })).toBe("/home/u/.config");
  });

  it("ignores a relative or empty XDG_CONFIG_HOME and gives none without an absolute HOME", () => {
    expect(credentialConfigHome({ XDG_CONFIG_HOME: "relative", HOME: "/home/u" })).toBe("/home/u/.config");
    expect(credentialConfigHome({ XDG_CONFIG_HOME: "", HOME: "/home/u" })).toBe("/home/u/.config");
    expect(credentialConfigHome({})).toBeNull();
    expect(credentialConfigHome({ HOME: "relative" })).toBeNull();
  });
});

describe("credentialPaths", () => {
  it("puts the file in a caztor folder of the configuration area", () => {
    expect(credentialPaths("/home/u/.config")).toEqual({ dir: "/home/u/.config/caztor", file: "/home/u/.config/caztor/credentials.json" });
  });

});
