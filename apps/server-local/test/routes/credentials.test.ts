import { chmodSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createCredentialStore, credentialPaths, nodeFileSystem } from "@caztor/adapters-local";
import type { CredentialStorePort } from "@caztor/core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanupProjects, harness, HOST, ORIGIN, TOKEN } from "./support.ts";

cleanupProjects();

const KEY = "sk-abcdef1234";
const OTHER = "sk-ant-api03-ZZZZ9876";
const configHomes: string[] = [];
afterEach(() => {
  for (const dir of configHomes.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/** The routes over a real store in a temporary configuration home; the user's own ~/.config is never touched. */
function setup(options: { store?: boolean } = {}) {
  const configHome = mkdtempSync(join(tmpdir(), "caztor-config-"));
  configHomes.push(configHome);
  const credentials: CredentialStorePort = createCredentialStore({ fs: nodeFileSystem, configHome, uid: process.getuid?.() ?? null });
  const h = harness(options.store === false ? {} : { credentials });
  const { dir, file } = credentialPaths(configHome);
  return { ...h, configHome, credentials, dir, file };
}

/** Every file below `dir`, read as text. */
function filesUnder(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...filesUnder(full));
    else if (entry.isFile()) out.push(readFileSync(full, "utf8"));
  }
  return out;
}

const everything = async (response: Response): Promise<string> => `${response.status} ${[...response.headers].map(([k, v]) => `${k}: ${v}`).join("\n")}\n${await response.text()}`;

describe("PUT /api/credentials/:slot", () => {
  it("stores the key and answers with the slot, that it is set and the last four characters only", async () => {
    const h = setup();
    const response = await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const text = await response.text();
    expect(JSON.parse(text)).toEqual({ slot: "claude", set: true, last4: "1234" });
    expect(text).not.toContain(KEY);
    expect(JSON.parse(readFileSync(h.file, "utf8"))).toEqual({ version: 1, keys: { claude: KEY } });
    expect(statSync(h.dir).mode & 0o777).toBe(0o700);
    expect(statSync(h.file).mode & 0o777).toBe(0o600);
  });

  it("keeps the key out of every file inside the project", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });
    for (const content of filesUnder(h.root)) expect(content).not.toContain(KEY);
  });

  it("shows no last four characters for a key shorter than twelve", async () => {
    const h = setup();
    const response = await h.call("PUT", "/api/credentials/codex", { body: { key: "sk-short12" } });
    expect(await response.json()).toEqual({ slot: "codex", set: true });
  });

  it("takes an opencode slot with its colon, written plain or percent-encoded", async () => {
    const h = setup();
    expect(await (await h.call("PUT", "/api/credentials/opencode:openai", { body: { key: KEY } })).json()).toEqual({ slot: "opencode:openai", set: true, last4: "1234" });
    expect(await (await h.call("PUT", "/api/credentials/opencode%3Aanthropic", { body: { key: OTHER } })).json()).toEqual({ slot: "opencode:anthropic", set: true, last4: "9876" });
  });

  it("replaces a key", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    await h.call("PUT", "/api/credentials/claude", { body: { key: OTHER } });
    expect(await h.credentials.read("claude")).toEqual({ ok: true, value: OTHER });
    expect(readFileSync(h.file, "utf8")).not.toContain(KEY);
  });

  it("refuses a slot it does not know, without echoing it or touching the store", async () => {
    const h = setup();
    for (const slot of ["nobody", "opencode:nowhere", "..%2Fclaude", "opencode"]) {
      const response = await h.call("PUT", `/api/credentials/${slot}`, { body: { key: KEY } });
      expect(response.status).toBe(404);
      const text = await response.text();
      expect(JSON.parse(text)).toMatchObject({ error: "unknown_slot" });
      expect(text).not.toContain(KEY);
    }
    expect(existsSync(h.dir)).toBe(false);
  });

  it.each([["a space in it", "has space"], ["nothing", ""], ["non-ASCII", "clé-secrète-1234"], ["too many characters", "k".repeat(513)]])("refuses a key with %s, without repeating it", async (_label, key) => {
    const h = setup();
    const response = await h.call("PUT", "/api/credentials/claude", { body: { key } });
    expect(response.status).toBe(400);
    const text = await response.text();
    expect(JSON.parse(text)).toMatchObject({ error: "invalid_key" });
    if (key !== "") expect(text).not.toContain(key);
    expect(existsSync(h.dir)).toBe(false);
  });

  it("refuses a body that is not JSON or has no key, and a key sent in the URL", async () => {
    const h = setup();
    expect((await h.call("PUT", "/api/credentials/claude", { body: "{not json" })).status).toBe(400);
    expect((await h.call("PUT", "/api/credentials/claude", { body: {} })).status).toBe(400);
    expect((await h.call("PUT", "/api/credentials/claude", { body: { key: 42 } })).status).toBe(400);
    const inUrl = await h.call("PUT", `/api/credentials/claude?key=${KEY}`, { body: {} });
    expect(inUrl.status).toBe(400);
    expect(await inUrl.text()).not.toContain(KEY);
    expect(existsSync(h.dir)).toBe(false);
  });

  it("answers 503 when the server has no credential store, without writing anything", async () => {
    const h = setup({ store: false });
    const response = await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    expect(response.status).toBe(503);
    expect(JSON.parse(await response.text())).toMatchObject({ error: "credentials_unavailable" });
  });

  it("answers 409 with a readable message when the stored file is open to other users, and changes nothing", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    chmodSync(h.file, 0o644);
    const before = readFileSync(h.file, "utf8");
    const response = await h.call("PUT", "/api/credentials/claude", { body: { key: OTHER } });
    expect(response.status).toBe(409);
    const text = await response.text();
    expect(JSON.parse(text)).toMatchObject({ error: "credential_store_unusable", message: expect.stringContaining("chmod") });
    expect(text).not.toContain(KEY);
    expect(text).not.toContain(OTHER);
    expect(readFileSync(h.file, "utf8")).toBe(before);
  });

  it("answers 409 for a corrupt file and never overwrites it", async () => {
    const h = setup();
    mkdirSync(h.dir, { mode: 0o700 });
    chmodSync(h.dir, 0o700);
    const { writeFileSync } = await import("node:fs");
    writeFileSync(h.file, `garbage ${KEY}`, { mode: 0o600 });
    const response = await h.call("PUT", "/api/credentials/claude", { body: { key: OTHER } });
    expect(response.status).toBe(409);
    expect(await response.text()).not.toContain(KEY);
    expect(readFileSync(h.file, "utf8")).toBe(`garbage ${KEY}`);
  });
});

describe("DELETE /api/credentials/:slot", () => {
  it("deletes the key and says it is no longer set", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    await h.call("PUT", "/api/credentials/codex", { body: { key: OTHER } });
    const response = await h.call("DELETE", "/api/credentials/claude");
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ slot: "claude", set: false });
    expect(await h.credentials.read("claude")).toEqual({ ok: true, value: null });
    expect(await h.credentials.read("codex")).toEqual({ ok: true, value: OTHER });
    expect(readFileSync(h.file, "utf8")).not.toContain(KEY);
  });

  it("answers the same for a slot with no key, and 404 for an unknown slot", async () => {
    const h = setup();
    expect(await (await h.call("DELETE", "/api/credentials/codex")).json()).toEqual({ slot: "codex", set: false });
    expect((await h.call("DELETE", "/api/credentials/nobody")).status).toBe(404);
  });
});

describe("the security gate applies to the credential routes", () => {
  const WRITES: Array<[string, string, unknown]> = [
    ["PUT", "/api/credentials/claude", { key: OTHER }],
    ["DELETE", "/api/credentials/claude", undefined],
  ];

  it.each(WRITES)("%s %s without the launch token is rejected and the store is unchanged", async (method, path, body) => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    const response = await h.call(method, path, { ...(body === undefined ? {} : { body }), headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect(await h.credentials.read("claude")).toEqual({ ok: true, value: KEY });
  });

  it.each(WRITES)("%s %s with a foreign Origin is rejected and the store is unchanged", async (method, path, body) => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    const response = await h.call(method, path, { ...(body === undefined ? {} : { body }), headers: { origin: "http://evil.example" } });
    expect(response.status).toBe(403);
    expect(await h.credentials.read("claude")).toEqual({ ok: true, value: KEY });
  });

  it.each(WRITES)("%s %s with a form content type is rejected and the store is unchanged", async (method, path, body) => {
    const h = setup();
    await h.credentials.set("claude", KEY);
    const response = await h.call(method, path, { ...(body === undefined ? {} : { body: `key=${OTHER}` }), headers: { "content-type": "application/x-www-form-urlencoded" } });
    expect(response.status).toBe(415);
    expect(await h.credentials.read("claude")).toEqual({ ok: true, value: KEY });
  });

  it("rejects a write with no Origin header and a request for another Host", async () => {
    const h = setup();
    const app = (await import("@caztor/api")).createApp(h.deps, { token: TOKEN, allowedHosts: [HOST], allowedOrigins: [ORIGIN] });
    const noOrigin = await app.request("/api/credentials/claude", { method: "PUT", headers: { host: HOST, "x-caztor-token": TOKEN, "content-type": "application/json" }, body: JSON.stringify({ key: OTHER }) });
    expect(noOrigin.status).toBe(403);
    const wrongHost = await app.request("/api/credentials/claude", { method: "PUT", headers: { host: "evil.example", origin: ORIGIN, "x-caztor-token": TOKEN, "content-type": "application/json" }, body: JSON.stringify({ key: OTHER }) });
    expect(wrongHost.status).toBe(403);
    expect(existsSync(h.dir)).toBe(false);
  });

  it("rejects an oversized body without echoing it", async () => {
    const h = setup();
    const response = await h.call("PUT", "/api/credentials/claude", { body: JSON.stringify({ key: "k".repeat(3 * 1024 * 1024) }) });
    expect(response.status).toBe(413);
    expect(existsSync(h.dir)).toBe(false);
  });
});

describe("no route gives a stored key back", () => {
  it("shows the key in no response, header or error path of any request that touches a credential route", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    await h.call("PUT", "/api/credentials/opencode:openai", { body: { key: OTHER } });
    await h.call("PUT", "/api/providers/claude/auth-mode", { body: { mode: "api" } });

    const probes: Array<[string, string, { body?: unknown; headers?: Record<string, string> }?]> = [
      ["GET", "/api/credentials"],
      ["GET", "/api/credentials/claude"],
      ["GET", "/api/credentials/opencode:openai"],
      ["GET", "/api/credentials/nobody"],
      ["HEAD", "/api/credentials/claude"],
      ["POST", "/api/credentials/claude", { body: { key: "x" } }],
      ["PUT", "/api/credentials/claude", { body: "{broken" }],
      ["PUT", "/api/credentials/claude", { body: { key: "has space" } }],
      ["DELETE", "/api/credentials/nobody"],
      ["GET", "/api/providers"],
      ["GET", "/api/session"],
      ["GET", "/api/credentials/claude", { headers: { "x-caztor-token": "wrong" } }],
    ];
    const logged: string[] = [];
    const record = (...args: unknown[]) => void logged.push(args.map(String).join(" "));
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) => vi.spyOn(console, level).mockImplementation(record));
    const out = vi.spyOn(process.stdout, "write").mockImplementation((chunk) => (logged.push(String(chunk)), true));
    const err = vi.spyOn(process.stderr, "write").mockImplementation((chunk) => (logged.push(String(chunk)), true));
    try {
      for (const [method, path, init] of probes) {
        const seen = await everything(await h.call(method, path, init));
        expect(seen, `${method} ${path}`).not.toContain(KEY);
        expect(seen, `${method} ${path}`).not.toContain(OTHER);
      }
    } finally {
      for (const spy of [...spies, out, err]) spy.mockRestore();
    }
    expect(logged.join("\n")).not.toContain(KEY);
    expect(logged.join("\n")).not.toContain(OTHER);
  });

  it("offers no GET that returns a value", async () => {
    const h = setup();
    await h.call("PUT", "/api/credentials/claude", { body: { key: KEY } });
    expect((await h.call("GET", "/api/credentials/claude")).status).toBe(404);
    expect((await h.call("GET", "/api/credentials")).status).toBe(404);
  });
});
