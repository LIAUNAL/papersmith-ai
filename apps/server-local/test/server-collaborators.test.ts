import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { ScriptedSpawner } from "./support/scripted-spawner.ts";
import type { FetchHandler, Listener, ListenFn } from "../src/listen.ts";
import { startServer, type ServerOptions } from "../src/server.ts";

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const pathOf = (link: string) => new URL(link).pathname;
const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;
const KEY = /^[A-HJ-NP-Z2-9]{5}(-[A-HJ-NP-Z2-9]{5}){3}$/;
const PUBLIC = "box.tail1234.ts.net";
const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const scratch = (prefix: string) => {
  const dir = realpathSync(mkdtempSync(join(tmpdir(), prefix)));
  dirs.push(dir);
  return dir;
};

interface Call {
  method?: string;
  host?: string;
  origin?: string;
  token?: string;
  cookie?: string;
  body?: unknown;
  /** A form post, as the sign-in page sends it. */
  form?: Record<string, string>;
}

async function boot(options: Partial<Pick<ServerOptions, "host" | "publicNames" | "secure">> = {}, start = 1_000_000) {
  const home = scratch("caztor-collab-");
  const project = join(home, "paper");
  await nodeFileSystem.mkdir(project);
  writeFileSync(join(project, "main.tex"), "x");
  const bound: Array<{ hostname: string; fetch: FetchHandler }> = [];
  const listen: ListenFn = async ({ port, hostname, fetch }) => {
    bound.push({ hostname, fetch });
    return { port, close: async () => {} } satisfies Listener;
  };
  let clock = start;
  const server = await startServer({
    projectDir: project,
    webRoot,
    env: { PATH: "/none", HOME: home, TMPDIR: tmpdir() },
    fs: nodeFileSystem,
    listen,
    watcher: { watch: () => () => {} },
    spawner: new ScriptedSpawner(),
    now: () => clock,
    ...options,
  });
  const local = `127.0.0.1:${server.port}`;
  const request = async (path: string, call: Call = {}) => {
    const method = call.method ?? "GET";
    const host = call.host ?? local;
    const headers: Record<string, string> = { host };
    if (call.token !== undefined) headers["x-caztor-token"] = call.token;
    if (call.cookie !== undefined) headers["cookie"] = call.cookie;
    if (method !== "GET") {
      if (call.origin !== "") headers["origin"] = call.origin ?? `http://${host}`;
      headers["content-type"] = call.form === undefined ? "application/json" : "application/x-www-form-urlencoded";
    } else if (call.origin !== undefined) headers["origin"] = call.origin;
    const body = call.form !== undefined ? new URLSearchParams(call.form).toString() : call.body === undefined ? undefined : JSON.stringify(call.body);
    return bound[0]!.fetch(new Request(`http://${host}${path}`, { method, headers, ...(body === undefined ? {} : { body }) }));
  };
  const host = (path: string, call: Call = {}) => request(path, { token: server.token, ...call });
  const usersFile = join(home, ".config", "caztor", "users.json");
  /** Posts an access key to an invite link the way the sign-in page does. */
  const signIn = (link: string, key: string, call: Call = {}) => request(pathOf(link), { method: "POST", host: PUBLIC, form: { key }, ...call });
  return { server, bound, request, host, signIn, home, usersFile, advance: (ms: number) => (clock += ms) };
}

const cookieOf = (response: Response) => {
  const header = response.headers.get("set-cookie");
  return header === null ? null : header.split(";")[0]!;
};
const metaToken = (html: string) => /<meta name="caztor-token" content="([^"]*)"/.exec(html)?.[1] ?? null;

type Setup = Awaited<ReturnType<typeof boot>>;
interface Made {
  link: string;
  key: string;
  expiresAt: number;
  inviteId: string;
  user: { id: string };
}

async function invite(setup: Setup, body: Record<string, unknown> = { name: "Ana" }): Promise<Made> {
  const invited = await setup.host("/api/users/invites", { method: "POST", body });
  expect(invited.status).toBe(201);
  return (await invited.json()) as Made;
}

/** Signs a browser in with an invite's link and key, and returns its cookie and page token. */
async function browserOf(setup: Setup, made: Pick<Made, "link" | "key">) {
  const signedIn = await setup.signIn(made.link, made.key);
  const cookie = cookieOf(signedIn)!;
  const page = await setup.request("/", { host: PUBLIC, cookie });
  const token = metaToken(await page.text())!;
  const call = (path: string, extra: Call = {}) => setup.request(path, { host: PUBLIC, cookie, token, ...extra });
  return { cookie, token, call, signedIn };
}

/** Invites `name` and signs one browser in. */
async function collaborator(setup: Setup, name = "Ana") {
  const made = await invite(setup, { name });
  const browser = await browserOf(setup, made);
  return { ...made, id: made.user.id, ...browser };
}

describe("the host on a loopback-only server", () => {
  it("keeps today's flow: the page carries the launch token and the API answers with it", async () => {
    const setup = await boot();
    expect(setup.bound[0]!.hostname).toBe("127.0.0.1");
    expect(setup.server.hostLink).toBeUndefined();
    const page = await setup.request("/");
    expect(page.status).toBe(200);
    expect(metaToken(await page.text())).toBe(setup.server.token);
    // Nobody else can reach this server, so the session answer is the single-user one, without a user.
    const session = await setup.host("/api/session");
    expect(await session.json()).not.toHaveProperty("user");
    expect((await setup.request("/api/session", { token: "wrong-token-0123456789" })).status).toBe(401);
    expect(() => statSync(setup.usersFile)).toThrow();
    await setup.server.close();
  });

  it("refuses invites while nothing is exposed", async () => {
    const setup = await boot();
    const invited = await setup.host("/api/users/invites", { method: "POST", body: { name: "Ana" } });
    expect(invited.status).toBe(409);
    expect(((await invited.json()) as { error: string }).error).toBe("not_exposed");
    await setup.server.close();
  });
});

describe("exposure", () => {
  it("refuses to bind beyond loopback without a public name", async () => {
    await expect(boot({ host: "0.0.0.0" })).rejects.toThrow(/--public-name/);
  });

  it("binds the given address and allows the public name in Host and Origin, refusing others", async () => {
    const setup = await boot({ host: "0.0.0.0", publicNames: [PUBLIC] });
    expect(setup.bound[0]!.hostname).toBe("0.0.0.0");
    expect((await setup.host("/api/files", { host: PUBLIC })).status).toBe(200);
    expect((await setup.host("/api/settings", { method: "PATCH", host: PUBLIC, body: { autoCompile: false } })).status).toBe(200);
    expect((await setup.host("/api/files", { host: "evil.ts.net" })).status).toBe(403);
    expect((await setup.host("/api/settings", { method: "PATCH", host: PUBLIC, origin: "http://evil.ts.net", body: { autoCompile: false } })).status).toBe(403);
    expect((await setup.host("/api/settings", { method: "PATCH", host: PUBLIC, origin: `https://${PUBLIC}`, body: { autoCompile: false } })).status).toBe(403);
    await setup.server.close();
  });

  it("allows https origins for public names with --secure", async () => {
    const setup = await boot({ publicNames: [PUBLIC], secure: true });
    expect(setup.bound[0]!.hostname).toBe("127.0.0.1");
    expect((await setup.host("/api/settings", { method: "PATCH", host: PUBLIC, origin: `https://${PUBLIC}`, body: { autoCompile: false } })).status).toBe(200);
    await setup.server.close();
  });

  it("serves a page without app or token to a visitor with no session, even on loopback", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    for (const host of [PUBLIC, `127.0.0.1:${setup.server.port}`]) {
      const page = await setup.request("/", { host });
      const html = await page.text();
      expect(page.status).toBe(401);
      expect(html).toContain("Ask the host for an invite link");
      expect(html).not.toContain(setup.server.token);
      expect(html).not.toContain("caztor-token");
      expect(html).not.toContain("app.js");
    }
    await setup.server.close();
  });

  it("signs the host in with the one-time host link, which then stops working", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const link = setup.server.hostLink!;
    expect(link).toMatch(new RegExp(`^http://127\\.0\\.0\\.1:${setup.server.port}/host/[A-Za-z0-9_-]{43}$`));
    const opened = await setup.request(pathOf(link));
    expect(opened.status).toBe(200);
    expect(await opened.text()).toContain('http-equiv="refresh" content="0;url=/"');
    const setCookie = opened.headers.get("set-cookie")!;
    expect(setCookie).toMatch(/^caztor_session=[A-Za-z0-9_-]{43}; /);
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("SameSite=Strict");
    expect(setCookie).toContain("Path=/");
    expect(setCookie).not.toContain("Secure");
    const page = await setup.request("/", { cookie: cookieOf(opened)! });
    expect(metaToken(await page.text())).toBe(setup.server.token);
    const again = await setup.request(pathOf(link));
    expect(again.status).toBe(403);
    expect(again.headers.get("set-cookie")).toBeNull();
    await setup.server.close();
  });
});

describe("invites", () => {
  it("returns a link that holds no secret: opened any number of times it signs no one in and changes nothing", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup);
    expect(made.link).toMatch(new RegExp(`^http://${PUBLIC.replaceAll(".", "\\.")}/invite/[A-Za-z0-9_-]{22}$`));
    expect(pathOf(made.link)).toBe(`/invite/${made.inviteId}`);
    expect(made.key).toMatch(KEY);
    expect(made.link).not.toContain(made.key);
    const before = readFileSync(setup.usersFile, "utf8");
    for (let preview = 0; preview < 5; preview += 1) {
      const opened = await setup.request(pathOf(made.link), { host: PUBLIC });
      expect(opened.status).toBe(200);
      expect(opened.headers.get("set-cookie")).toBeNull();
      expect(opened.headers.get("cache-control")).toBe("no-store");
      const html = await opened.text();
      expect(html).toContain(`<form method="post" action="/invite/${made.inviteId}">`);
      expect(html).toContain('name="key"');
      expect(html).not.toContain("<script");
    }
    expect(readFileSync(setup.usersFile, "utf8")).toBe(before);
    // The key still works after all those previews.
    expect((await setup.signIn(made.link, made.key)).status).toBe(303);
    await setup.server.close();
  });

  it("signs in with the right key into a cookie session with its own page token", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    expect(ana.signedIn.status).toBe(303);
    expect(ana.signedIn.headers.get("location")).toBe("/");
    expect(ana.signedIn.headers.get("set-cookie")).toMatch(/^caztor_session=[A-Za-z0-9_-]{43}; Path=\/; HttpOnly; SameSite=Strict/);
    expect(ana.signedIn.headers.get("set-cookie")).not.toContain("Secure");
    expect(ana.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(ana.token).not.toBe(setup.server.token);

    const session = await ana.call("/api/session");
    expect(session.status).toBe(200);
    expect(((await session.json()) as { user: { name: string; role: string } }).user).toEqual({ id: ana.id, name: "Ana", role: "collaborator" });
    // The cookie alone, the token alone, or the cookie with the launch token's slot filled by another token are refused.
    expect((await setup.request("/api/session", { host: PUBLIC, cookie: ana.cookie })).status).toBe(401);
    expect((await setup.request("/api/session", { host: PUBLIC, token: ana.token })).status).toBe(401);
    expect((await setup.request("/api/session", { host: PUBLIC, cookie: ana.cookie, token: "x".repeat(43) })).status).toBe(401);

    const stored = readFileSync(setup.usersFile, "utf8");
    expect(statSync(setup.usersFile).mode & 0o777).toBe(0o600);
    expect(statSync(join(setup.home, ".config", "caztor")).mode & 0o777).toBe(0o700);
    for (const secret of [ana.key, ana.key.replaceAll("-", ""), ana.cookie.split("=")[1]!, ana.token, setup.server.token]) expect(stored).not.toContain(secret);
    await setup.server.close();
  });

  it("refuses a wrong key with 403 and the same page as an unknown link, saying nothing of why", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup);
    const other = await invite(setup, { name: "Bo" });
    const wrong = await setup.signIn(made.link, other.key);
    const unknown = await setup.signIn(`http://${PUBLIC}/invite/AAAAAAAAAAAAAAAAAAAAAA`, made.key);
    const garbage = await setup.signIn(made.link, "not a key");
    const text = await wrong.text();
    for (const response of [wrong, unknown, garbage]) {
      expect(response.status).toBe(403);
      expect(response.headers.get("set-cookie")).toBeNull();
    }
    expect(text).toContain("That key does not work.");
    expect(text).toContain('name="key"');
    expect((await unknown.text()).replace(/AAAAAAAAAAAAAAAAAAAAAA/g, made.inviteId)).toBe(text);
    expect((await garbage.text())).toBe(text);
    await setup.server.close();
  });

  it("takes the key with or without dashes, in either case, as a form or as JSON, from a second browser too", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    const phone = await setup.request(pathOf(ana.link), { method: "POST", host: PUBLIC, body: { key: ana.key.toLowerCase().replaceAll("-", "") } });
    expect(phone.status).toBe(200);
    expect(await phone.json()).toEqual({ signedIn: true });
    const phoneCookie = cookieOf(phone)!;
    expect(phoneCookie).not.toBe(ana.cookie);
    const phonePage = await setup.request("/", { host: PUBLIC, cookie: phoneCookie });
    const phoneToken = metaToken(await phonePage.text())!;
    expect((await setup.request("/api/session", { host: PUBLIC, cookie: phoneCookie, token: phoneToken })).status).toBe(200);
    expect((await ana.call("/api/session")).status).toBe(200);
    const wrongJson = await setup.request(pathOf(ana.link), { method: "POST", host: PUBLIC, body: { key: "AAAAA-AAAAA-AAAAA-AAAAA" } });
    expect(wrongJson.status).toBe(403);
    expect(await wrongJson.json()).toEqual({ error: "invalid_key", message: "That key does not work. Check it, or ask the host for a new invite." });
    const listed = (await (await setup.host("/api/users")).json()) as { users: Array<{ sessions: number; invites: Array<{ sessions: number; status: string }> }> };
    expect(listed.users[0]).toMatchObject({ sessions: 2, invites: [{ sessions: 2, status: "active" }] });
    await setup.server.close();
  });

  it("refuses the key and ends every session made with it once it expires", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup, { name: "Ana", minutes: 60 });
    expect(made.expiresAt).toBe(1_000_000 + 60 * MINUTE);
    const laptop = await browserOf(setup, made);
    const phone = await browserOf(setup, made);
    expect((await laptop.call("/api/session")).status).toBe(200);
    setup.advance(60 * MINUTE - 1);
    expect((await phone.call("/api/session")).status).toBe(200);
    setup.advance(1);
    for (const browser of [laptop, phone]) {
      expect((await browser.call("/api/session")).status).toBe(401);
      expect(metaToken(await (await setup.request("/", { host: PUBLIC, cookie: browser.cookie })).text())).toBeNull();
    }
    const late = await setup.signIn(made.link, made.key);
    expect(late.status).toBe(403);
    expect(late.headers.get("set-cookie")).toBeNull();
    const listed = (await (await setup.host("/api/users")).json()) as { users: Array<{ sessions: number; invites: Array<{ status: string }> }> };
    expect(listed.users[0]).toMatchObject({ sessions: 0, invites: [{ status: "expired" }] });
    await setup.server.close();
  });

  it("lets the host choose the lifetime, from 10 minutes to 365 days, 7 days by default", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    expect((await invite(setup, { name: "Ana" })).expiresAt).toBe(1_000_000 + 7 * DAY);
    expect((await invite(setup, { name: "Ana", minutes: 10 })).expiresAt).toBe(1_000_000 + 10 * MINUTE);
    expect((await invite(setup, { name: "Ana", minutes: 365 * 24 * 60 })).expiresAt).toBe(1_000_000 + 365 * DAY);
    for (const minutes of [9, 365 * 24 * 60 + 1, 90.5, "60", null]) {
      const refused = await setup.host("/api/users/invites", { method: "POST", body: { name: "Ana", minutes } });
      expect(refused.status, String(minutes)).toBe(400);
      expect(await refused.json()).toMatchObject({ error: "invalid_lifetime", message: "Choose how long the key lasts: from 10 minutes to 365 days." });
    }
    await setup.server.close();
  });

  it("locks an invite after 10 wrong keys, so the right key is refused too, and shows the host it is locked", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup);
    for (let attempt = 0; attempt < 10; attempt += 1) expect((await setup.signIn(made.link, "AAAAA-AAAAA-AAAAA-AAAAA")).status).toBe(403);
    const refused = await setup.signIn(made.link, made.key);
    expect(refused.status).toBe(403);
    expect(refused.headers.get("set-cookie")).toBeNull();
    const listed = (await (await setup.host("/api/users")).json()) as { users: Array<{ invites: Array<{ status: string; failures: number }> }> };
    expect(listed.users[0]!.invites).toEqual([expect.objectContaining({ status: "locked", failures: 10 })]);
    await setup.server.close();
  });

  it("refuses a sign-in posted from another origin, or with none", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup);
    const foreign = await setup.signIn(made.link, made.key, { origin: "http://evil.ts.net" });
    expect(foreign.status).toBe(403);
    expect(foreign.headers.get("set-cookie")).toBeNull();
    expect((await setup.signIn(made.link, made.key, { origin: "" })).status).toBe(403);
    // Every other page outside the API still takes reads only.
    expect((await setup.request("/host/whatever", { method: "POST", host: PUBLIC, form: {} })).status).toBe(405);
    expect((await setup.request(`/invite/${made.inviteId}/more`, { method: "POST", host: PUBLIC, form: { key: made.key } })).status).toBe(405);
    expect((await setup.signIn(made.link, made.key)).status).toBe(303);
    await setup.server.close();
  });

  it("marks the cookie Secure and the link https only with --secure", async () => {
    const setup = await boot({ publicNames: [PUBLIC], secure: true });
    const made = await invite(setup);
    expect(made.link.startsWith(`https://${PUBLIC}/invite/`)).toBe(true);
    const signedIn = await setup.signIn(made.link, made.key, { origin: `https://${PUBLIC}` });
    expect(signedIn.headers.get("set-cookie")).toContain("; Secure");
    await setup.server.close();
  });

  it("revokes one access key, ending only the sessions made with it", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const laptopKey = await invite(setup);
    const phoneKey = await invite(setup);
    const laptop = await browserOf(setup, laptopKey);
    const phone = await browserOf(setup, phoneKey);
    expect((await setup.host(`/api/users/invites/${laptopKey.inviteId}`, { method: "DELETE" })).status).toBe(200);
    expect((await laptop.call("/api/session")).status).toBe(401);
    expect((await setup.signIn(laptopKey.link, laptopKey.key)).status).toBe(403);
    expect((await phone.call("/api/session")).status).toBe(200);
    expect((await setup.host(`/api/users/invites/${laptopKey.inviteId}`, { method: "DELETE" })).status).toBe(404);
    expect((await phone.call(`/api/users/invites/${phoneKey.inviteId}`, { method: "DELETE" })).status).toBe(403);
    await setup.server.close();
  });

  it("lists collaborators to the host and revokes one, ending their session at once", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    const listed = (await (await setup.host("/api/users")).json()) as { users: Array<{ id: string; name: string; role: string; sessions: number }> };
    expect(listed.users).toEqual([
      expect.objectContaining({ id: ana.id, name: "Ana", role: "collaborator", sessions: 1, invites: [expect.objectContaining({ id: ana.inviteId, expiresAt: ana.expiresAt, status: "active" })] }),
    ]);
    const revoked = await setup.host(`/api/users/${ana.id}`, { method: "DELETE" });
    expect(revoked.status).toBe(200);
    expect((await ana.call("/api/session")).status).toBe(401);
    const page = await setup.request("/", { host: PUBLIC, cookie: ana.cookie });
    expect(metaToken(await page.text())).toBeNull();
    expect(((await (await setup.host("/api/users")).json()) as { users: unknown[] }).users).toEqual([]);
    expect((await setup.signIn(ana.link, ana.key)).status).toBe(403);
    expect((await setup.host("/api/users/host", { method: "DELETE" })).status).toBe(409);
    expect((await setup.host("/api/users/missing", { method: "DELETE" })).status).toBe(404);
    await setup.server.close();
  });

  it("loads a first-version store: its sessions still work and its unused one-time link is refused as an old invite", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const configDir = join(setup.home, ".config", "caztor");
    mkdirSync(configDir, { recursive: true, mode: 0o700 });
    const sha = (value: string) => createHash("sha256").update(value).digest("hex");
    const oldCode = "Q".repeat(32);
    writeFileSync(
      setup.usersFile,
      JSON.stringify({
        version: 1,
        users: [{ id: "u-ana", name: "Ana", role: "collaborator", createdAt: 1, sessions: [{ hash: sha("A".repeat(43)), createdAt: 2 }] }],
        invites: [{ hash: sha(oldCode), userId: "u-ana", expiresAt: 1_000_000 + DAY }],
      }),
      { mode: 0o600 },
    );
    const cookie = `caztor_session=${"A".repeat(43)}`;
    const page = await setup.request("/", { host: PUBLIC, cookie });
    expect(metaToken(await page.text())).toMatch(/^[A-Za-z0-9_-]{43}$/);
    const old = await setup.request(`/invite/${oldCode}`, { host: PUBLIC });
    expect(old.headers.get("set-cookie")).toBeNull();
    expect((await setup.request(`/invite/${oldCode}`, { method: "POST", host: PUBLIC, form: { key: oldCode } })).status).toBe(403);
    const listed = (await (await setup.host("/api/users")).json()) as { users: Array<{ id: string; invites: Array<{ status: string }> }> };
    expect(listed.users).toEqual([expect.objectContaining({ id: "u-ana", sessions: 1, invites: [expect.objectContaining({ status: "old" })] })]);
    await setup.server.close();
  });
});

describe("what a collaborator may do", () => {
  it("is refused the user routes only: the chat, providers and keys are their own, and files and compile stay", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    expect((await ana.call("/api/users")).status).toBe(403);
    expect((await ana.call("/api/users/invites", { method: "POST", body: { name: "Eve" } })).status).toBe(403);
    expect((await ana.call(`/api/users/${ana.id}`, { method: "DELETE" })).status).toBe(403);
    const turn = await ana.call("/api/chat/turns", { method: "POST", body: { provider: "claude", prompt: "hi" } });
    expect(JSON.stringify(await turn.text())).not.toContain("collaborator_chat_unavailable");
    for (const path of ["/api/chat/history?provider=claude", "/api/credentials", "/api/providers"]) {
      const response = await ana.call(path);
      expect(response.status, path).not.toBe(403);
    }
    expect((await ana.call("/api/files")).status).toBe(200);
    expect((await ana.call("/api/compile/status")).status).toBe(200);
    // Any folder on the host's machine stays the host's choice; a collaborator moves only between listed projects.
    const elsewhere = await ana.call("/api/projects/open", { method: "POST", body: { path: setup.home } });
    expect(elsewhere.status).toBe(403);
    expect(await elsewhere.json()).toMatchObject({ error: "host_only" });
    expect((await ana.call("/api/projects/open", { method: "POST", body: { path: setup.server.root } })).status).toBe(200);
    await setup.server.close();
  });
});

describe("the host once collaborators can reach the server", () => {
  it("is named in the session answer", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const session = await setup.host("/api/session");
    expect(((await session.json()) as { user: unknown }).user).toEqual({ id: "host", name: "Host", role: "host" });
    await setup.server.close();
  });

  it("alone may change whether compiles are sandboxed; the other settings stay shared", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    const refused = await ana.call("/api/settings", { method: "PATCH", body: { sandboxedCompile: false } });
    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({ error: "host_only", message: "Only the host can change whether compiles run in the sandbox." });
    expect((await ana.call("/api/settings", { method: "PATCH", body: { autoCompile: false, sandboxedCompile: true } })).status).toBe(403);
    expect((await ana.call("/api/settings", { method: "PATCH", body: { autoCompile: false } })).status).toBe(200);
    expect((await setup.host("/api/settings", { method: "PATCH", host: PUBLIC, body: { sandboxedCompile: true } })).status).toBe(200);
    const settings = ((await (await setup.host("/api/session")).json()) as { settings: Record<string, unknown> }).settings;
    expect(settings).toMatchObject({ autoCompile: false, sandboxedCompile: true });
    await setup.server.close();
  });

  it("refuses every compile, the host's too, while the sandbox cannot be used", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    for (const response of [await ana.call("/api/compile", { method: "POST" }), await setup.host("/api/compile", { method: "POST", host: PUBLIC })]) {
      expect(response.status).toBe(409);
      expect(await response.json()).toMatchObject({ error: "sandbox_required", message: expect.stringContaining("every compile runs in the sandbox") });
    }
    await setup.server.close();
  });
});

describe("rate limits", () => {
  it("never refuse a valid session, however many forged cookies came first", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const ana = await collaborator(setup);
    const hostLink = await setup.request(pathOf(setup.server.hostLink!), { host: PUBLIC });
    const hostCookie = cookieOf(hostLink)!;
    for (let attempt = 0; attempt < 25; attempt += 1) {
      await setup.request("/api/session", { host: PUBLIC, cookie: `caztor_session=forged${attempt}`, token: "y".repeat(43) });
      await setup.request("/", { host: PUBLIC, cookie: `caztor_session=forged${attempt}` });
    }
    expect((await ana.call("/api/session")).status).toBe(200);
    expect(metaToken(await (await setup.request("/", { host: PUBLIC, cookie: ana.cookie })).text())).toBe(ana.token);
    expect(metaToken(await (await setup.request("/", { host: PUBLIC, cookie: hostCookie })).text())).toBe(setup.server.token);
    await setup.server.close();
  });

  it("never refuse a valid key, however many wrong keys came first", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const made = await invite(setup, { name: "Bo" });
    for (let attempt = 0; attempt < 25; attempt += 1) await setup.signIn(`http://${PUBLIC}/invite/bad${attempt}${"x".repeat(20)}`, "AAAAA-AAAAA-AAAAA-AAAAA");
    const signedIn = await setup.signIn(made.link, made.key);
    expect(signedIn.status).toBe(303);
    expect(cookieOf(signedIn)).toMatch(/^caztor_session=/);
    await setup.server.close();
  });

  it("refuses key attempts after 20 failures a minute from one address", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    const bad = (attempt: number | string) => setup.signIn(`http://${PUBLIC}/invite/bad${attempt}${"x".repeat(20)}`, "AAAAA-AAAAA-AAAAA-AAAAA");
    for (let attempt = 0; attempt < 20; attempt += 1) expect((await bad(attempt)).status).toBe(403);
    const limited = await bad("last");
    expect(limited.status).toBe(429);
    expect(await limited.text()).toContain("Too many tries");
    setup.advance(61_000);
    expect((await bad("again")).status).toBe(403);
    await setup.server.close();
  });

  it("refuses cookie checks after 20 failures a minute from one address", async () => {
    const setup = await boot({ publicNames: [PUBLIC] });
    for (let attempt = 0; attempt < 20; attempt += 1) {
      expect((await setup.request("/api/session", { host: PUBLIC, cookie: `caztor_session=forged${attempt}`, token: "y".repeat(43) })).status).toBe(401);
    }
    expect((await setup.request("/api/session", { host: PUBLIC, cookie: "caztor_session=forged", token: "y".repeat(43) })).status).toBe(429);
    // The host's launch token does not go through the cookie check.
    expect((await setup.host("/api/session", { host: PUBLIC })).status).toBe(200);
    await setup.server.close();
  });
});
