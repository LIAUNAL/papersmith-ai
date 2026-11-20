import type { ProviderId, TurnUser } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createLoginRelay, type LoginRelayOptions } from "../../src/login/relay.ts";
import { terminalArgs } from "../../src/agent-sandbox.ts";
import { collaboratorEnv } from "../../src/user-home.ts";
import { fakeAgentSandbox } from "../fakes/fake-agent-sandbox.ts";
import { FakeClock } from "../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../fakes/fake-spawner.ts";
import { MemoryFileSystem } from "../fakes/memory-fs.ts";

const HOST: TurnUser = { id: "host", name: "Host", role: "host" };
const ALICE: TurnUser = { id: "alice-1", name: "Alice", role: "collaborator" };
const BOB: TurnUser = { id: "bob-2", name: "Bob", role: "collaborator" };
const homeOf = (user: TurnUser) => `/cfg/caztor/users/${user.id}/home`;
const ENV = { PATH: "/bin", HOME: "/home/host", LANG: "C.UTF-8", ANTHROPIC_API_KEY: "sk-host-key-must-not-pass", XDG_RUNTIME_DIR: "/run/user/1000" };
const ROOT = "/papers/paper";
const flush = async () => {
  for (let index = 0; index < 10; index += 1) await new Promise((resolve) => setImmediate(resolve));
};

/** The first output of each CLI's sign-in, as observed with an empty home (nothing was submitted). */
const FIRST: Record<string, ChildScript> = {
  claude: { stdout: ["Opening browser to sign in…\nIf the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=A3v5\nPaste code here if prompted > "] },
  codex: { stdout: ["Follow these steps to sign in with ChatGPT using device code authorization:\n\n1. Open this link in your browser and sign in to your account\n   \u001b[94mhttps://auth.openai.com/codex/device\u001b[0m\n\n2. Enter this one-time code \u001b[90m(expires in 15 minutes)\u001b[0m\n   \u001b[94mXZIF-17WOH\u001b[0m\n"] },
  opencode: { stdout: ["\u001b[0m\n┌  Add credential\n│\n●  Go to: https://auth.openai.com/codex/device\n│\n●  Enter code: XZH3-GJO81\n│\n◒  Waiting for authorization\u001b[999D\u001b[J◐  Waiting for authorization"] },
  pi: { stdout: ["\u001b[?1049h\u001b[2J\u001b[H\u001b[2;1H\u001b[2K pi v1.4.0\u001b[5;1H\u001b[2K Press ctrl+o to show full startup help"] },
  agy: { stdout: ["\n Welcome to the Antigravity CLI. You are currently not signed in.\r\n\n Select login method:\r\n > 1. Google OAuth\n2. Use a Google Cloud project\n\n↑/↓ Navigate · enter Select"] },
};

async function setup(options: { sandbox?: boolean; installed?: string[] } = {}) {
  const files: Record<string, string> = { "/usr/bin/script": "elf" };
  for (const name of options.installed ?? ["claude", "codex", "opencode", "pi", "agy"]) files[`/bin/${name}`] = "#!/bin/sh";
  const fs = new MemoryFileSystem(files);
  for (const path of Object.keys(files)) await fs.chmod(path, 0o755);
  for (const user of [ALICE, BOB]) await fs.mkdir(homeOf(user), { recursive: true });
  const spawner = new FakeSpawner();
  const clock = new FakeClock(1_000);
  const sandbox = fakeAgentSandbox();
  const signedIn: Array<[string, ProviderId]> = [];
  const relayOptions: LoginRelayOptions = {
    fs,
    spawner,
    clock,
    env: ENV,
    ...(options.sandbox === false ? {} : { sandbox: sandbox.sandbox }),
    homeOf: async (user) => ({ ok: true, value: homeOf(user) }),
    onSignedIn: (user, provider) => signedIn.push([user.id, provider]),
  };
  const relay = createLoginRelay(relayOptions);
  return { fs, spawner, clock, sandbox, relay, signedIn };
}

describe("signing a collaborator in from the browser", () => {
  it("runs claude auth login in their sandbox, with their private home and environment, without a terminal", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["claude"]!);
    const started = await t.relay.start(ALICE, "claude");
    expect(started).toMatchObject({ ok: true, value: { provider: "claude", method: "subscription", state: "running", terminal: false } });
    expect(t.sandbox.asked).toEqual([{ binary: "/bin/claude", home: homeOf(ALICE), terminal: false }]);
    expect(t.spawner.calls[0]).toEqual({
      file: "/usr/bin/bwrap",
      args: ["--", "/bin/claude", "auth", "login", "--claudeai"],
      cwd: homeOf(ALICE),
      env: collaboratorEnv(ENV, homeOf(ALICE), "claude"),
      interactive: true,
    });
    expect(t.spawner.calls[0]!.env).not.toHaveProperty("ANTHROPIC_API_KEY");
    await flush();
    expect(t.relay.view(ALICE, "claude")?.text).toContain("https://claude.com/cai/oauth/authorize?code=true");
  });

  it("forwards the pasted code and marks only that person signed in when the CLI exits 0", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["claude"]!);
    await t.relay.start(ALICE, "claude");
    await flush();
    expect(t.relay.send(ALICE, "claude", { line: "pasted-code-abc#state" })).toMatchObject({ ok: true });
    expect(t.spawner.written).toEqual(["pasted-code-abc#state\n"]);
    t.spawner.pushStdout("pasted-code-abc#state\nLogin successful.\n");
    await flush();
    expect(t.relay.view(ALICE, "claude")?.text).not.toContain("pasted-code-abc");
    expect(t.signedIn).toEqual([]);
  });

  it.each([
    ["codex", undefined, ["login", "--device-auth"], "XZIF-17WOH"],
    ["opencode", undefined, ["auth", "login", "-p", "openai", "-m", "ChatGPT Pro/Plus (headless)"], "XZH3-GJO81"],
  ] as const)("runs %s's device-code sign-in and shows the code", async (provider, method, args, code) => {
    const t = await setup();
    t.spawner.enqueue({ ...FIRST[provider]!, exit: { code: 0, signal: null } });
    expect((await t.relay.start(ALICE, provider, method)).ok).toBe(true);
    expect(t.spawner.calls[0]!.args).toEqual(["--", `/bin/${provider}`, ...args]);
    expect(t.spawner.calls[0]!.env).toEqual(collaboratorEnv(ENV, homeOf(ALICE), provider));
    await flush();
    expect(t.relay.view(ALICE, provider)).toMatchObject({ state: "signed_in", code });
    expect(t.signedIn).toEqual([["alice-1", provider]]);
  });

  it("offers opencode's own menu in a terminal for other providers", async () => {
    const t = await setup();
    expect(t.relay.methods("opencode").map((method) => method.id)).toEqual(["chatgpt", "menu"]);
    t.spawner.enqueue({ stdout: ["◆  Select provider"] });
    expect(await t.relay.start(ALICE, "opencode", "menu")).toMatchObject({ ok: true, value: { terminal: true } });
    expect(t.sandbox.asked.at(-1)).toEqual({ binary: "/bin/opencode", home: homeOf(ALICE), terminal: true });
    expect(await t.relay.start(ALICE, "opencode", "nope")).toMatchObject({ ok: false, error: { code: "unknown_method" } });
  });

  it("runs Pi in a terminal, types /login, and is signed in once Pi writes its auth file", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["pi"]!);
    expect(await t.relay.start(ALICE, "pi")).toMatchObject({ ok: true, value: { terminal: true } });
    expect(t.sandbox.asked).toEqual([{ binary: "/bin/pi", home: homeOf(ALICE), terminal: true }]);
    expect(t.spawner.calls[0]!.args).toEqual(["--", "/bin/pi", "-na", "-ne", "--no-mcp", "-ns", "-np", "--no-themes", "-nc"]);
    await flush();
    t.clock.advance(1_500);
    expect(t.spawner.written).toEqual(["/login\r"]);
    t.relay.send(ALICE, "pi", { key: "enter" });
    await flush();
    await t.fs.mkdir(`${homeOf(ALICE)}/.pi/agent`, { recursive: true });
    await t.fs.writeFile(`${homeOf(ALICE)}/.pi/agent/auth.json`, new TextEncoder().encode("{}"));
    t.clock.advance(3_000);
    await flush();
    expect(t.relay.view(ALICE, "pi")?.state).toBe("signed_in");
    expect(t.signedIn).toEqual([["alice-1", "pi"]]);
  });

  it("runs agy in a terminal, and checks the sign-in with agy models in the same sandbox after the code is pasted", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["agy"]!);
    expect(await t.relay.start(ALICE, "antigravity")).toMatchObject({ ok: true, value: { terminal: true } });
    expect(t.spawner.calls[0]!.args).toEqual(["--", "/bin/agy"]);
    expect(t.spawner.calls[0]!.env).toEqual(collaboratorEnv(ENV, homeOf(ALICE), "antigravity"));
    expect(t.spawner.calls[0]!.env).not.toHaveProperty("XDG_RUNTIME_DIR");
    await flush();
    t.spawner.enqueue({ stdout: ["gemini-3-pro\n"], exit: { code: 0, signal: null } });
    t.relay.send(ALICE, "antigravity", { line: "4/0AVGzR1A-pasted-code" });
    await flush();
    expect(t.spawner.calls[1]).toMatchObject({ file: "/usr/bin/bwrap", args: ["--", "/bin/agy", "models"], cwd: homeOf(ALICE) });
    expect(t.relay.view(ALICE, "antigravity")?.state).toBe("signed_in");
    expect(t.signedIn).toEqual([["alice-1", "antigravity"]]);
  });

  it("refuses a collaborator's sign-in without a sandbox, and runs nothing", async () => {
    const t = await setup({ sandbox: false });
    expect(await t.relay.start(ALICE, "claude")).toMatchObject({ ok: false, error: { code: "isolation_failed" } });
    expect(t.spawner.calls).toEqual([]);
  });

  it("says when the CLI is not installed", async () => {
    const t = await setup({ installed: [] });
    expect(await t.relay.start(ALICE, "codex")).toMatchObject({ ok: false, error: { code: "not_installed" } });
  });

  it("starts one sign-in at a time per person: of two started together, the first is ended before the second runs", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["claude"]!);
    t.spawner.enqueue(FIRST["codex"]!);
    const [first, second] = await Promise.all([t.relay.start(ALICE, "claude"), t.relay.start(ALICE, "codex")]);
    expect(first.ok && second.ok).toBe(true);
    await flush();
    expect(t.spawner.calls).toHaveLength(2);
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(t.relay.view(ALICE, "claude")).toBeNull();
    expect(t.relay.view(ALICE, "codex")?.state).toBe("running");
  });

  it("keeps one sign-in per person: a new one ends the old, and nobody else sees or touches it", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["claude"]!);
    await t.relay.start(ALICE, "claude");
    t.spawner.enqueue(FIRST["codex"]!);
    await t.relay.start(BOB, "codex");
    t.spawner.enqueue(FIRST["codex"]!);
    await t.relay.start(ALICE, "codex");
    await flush();
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(t.relay.view(ALICE, "claude")).toBeNull();
    expect(t.relay.view(ALICE, "codex")?.state).toBe("running");
    expect(t.relay.view(BOB, "codex")?.state).toBe("running");
    expect(t.relay.view(BOB, "claude")).toBeNull();
    expect(t.relay.view(HOST, "codex")).toBeNull();
    expect(t.relay.send(BOB, "claude", { line: "code" })).toMatchObject({ ok: false, error: { code: "not_found" } });
    expect(t.relay.cancel(HOST, "codex")).toBe(false);
    expect(t.relay.cancel(BOB, "codex")).toBe(true);
    await flush();
    expect(t.relay.view(BOB, "codex")?.state).toBe("cancelled");
    expect(t.relay.view(ALICE, "codex")?.state).toBe("running");
  });
});

describe("signing the host in from the browser", () => {
  it("runs the CLI as the host would in a terminal: no sandbox, the server's environment", async () => {
    const t = await setup();
    t.spawner.enqueue({ ...FIRST["codex"]!, exit: { code: 0, signal: null } });
    await t.relay.start(HOST, "codex");
    expect(t.sandbox.asked).toEqual([]);
    expect(t.spawner.calls[0]).toEqual({ file: "/bin/codex", args: ["login", "--device-auth"], cwd: "/tmp/caztor-login-000001", env: { PATH: "/bin", HOME: "/home/host", LANG: "C.UTF-8", ANTHROPIC_API_KEY: "sk-host-key-must-not-pass", XDG_RUNTIME_DIR: "/run/user/1000", PWD: "/tmp/caztor-login-000001" }, interactive: true });
    await flush();
    expect(t.signedIn).toEqual([["host", "codex"]]);
  });

  it("gives a terminal through the system's script for a CLI that needs one", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["agy"]!);
    await t.relay.start(HOST, "antigravity");
    expect(t.spawner.calls[0]).toMatchObject({ file: "/usr/bin/script", args: terminalArgs("/bin/agy", []), cwd: "/tmp/caztor-login-000001", env: { ...ENV, SHELL: "/bin/sh" } });
  });

  it.each([
    ["claude", "subscription"],
    ["codex", "device"],
    ["opencode", "chatgpt"],
    ["opencode", "menu"],
    ["pi", "login"],
    ["antigravity", "google"],
  ] as const)("runs the host's %s sign-in (%s) in a fresh empty folder closed to others, never the project, and removes it after", async (provider, method) => {
    const t = await setup();
    // A collaborator's turn can write the project, so a plugin left there must not load with the host's sign-in.
    await t.fs.mkdir(`${ROOT}/.opencode/plugin`, { recursive: true });
    t.spawner.enqueue({ stdout: ["…"], exit: { code: 1, signal: null } });
    // agy's sign-in check runs agy models the same way.
    t.spawner.enqueue({ stdout: [""], exit: { code: 1, signal: null } });
    expect((await t.relay.start(HOST, provider, method)).ok).toBe(true);
    const cwd = t.spawner.calls[0]!.cwd;
    expect(cwd).not.toBe(ROOT);
    expect(cwd.startsWith(`${ROOT}/`)).toBe(false);
    expect(cwd).toMatch(/^\/tmp\/caztor-login-/);
    expect(await t.fs.readdir(cwd)).toEqual([]);
    expect((await t.fs.stat(cwd)).mode & 0o777).toBe(0o700);
    await flush();
    expect(await t.fs.stat(cwd).then(() => true, () => false)).toBe(false);
  });

  it("runs agy models, the check of the host's agy sign-in, in a fresh folder too, and removes it", async () => {
    const t = await setup();
    t.spawner.enqueue(FIRST["agy"]!);
    await t.relay.start(HOST, "antigravity");
    await flush();
    t.spawner.enqueue({ stdout: ["gemini-3-pro\n"], exit: { code: 0, signal: null } });
    t.relay.send(HOST, "antigravity", { line: "4/0AVGzR1A-pasted-code" });
    await flush();
    const check = t.spawner.calls[1]!;
    expect(check).toMatchObject({ file: "/bin/agy", args: ["models"] });
    expect(check.cwd).toMatch(/^\/tmp\/caztor-login-/);
    expect(check.cwd).not.toBe(t.spawner.calls[0]!.cwd);
    expect(await t.fs.stat(check.cwd).then(() => true, () => false)).toBe(false);
  });
});
