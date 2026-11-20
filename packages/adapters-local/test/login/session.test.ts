import { describe, expect, it } from "vitest";
import { createLoginSession, KILL_GRACE_MS, LOGIN_IDLE_MS, LOGIN_TIMEOUT_MS, type LoginSessionOptions } from "../../src/login/session.ts";
import type { SpawnSpec } from "../../src/infra.ts";
import { FakeClock } from "../fakes/fake-clock.ts";
import { FakeSpawner, type ChildScript } from "../fakes/fake-spawner.ts";

const SPEC: SpawnSpec = { file: "/usr/bin/bwrap", args: ["--", "/cli", "auth", "login"], cwd: "/home/x", env: { HOME: "/home/x" }, interactive: true };
/** The first lines `claude auth login` prints with no terminal, as observed. */
const CLAUDE_FIRST = [
  "Opening browser to sign in…\n",
  "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.com%2Foauth%2Fcode%2Fcallback&state=A3v5\n",
  "Paste code here if prompted > ",
];
const flush = async () => {
  for (let index = 0; index < 10; index += 1) await new Promise((resolve) => setImmediate(resolve));
};

function setup(script: ChildScript, options: Partial<LoginSessionOptions> = {}) {
  const spawner = new FakeSpawner();
  const clock = new FakeClock(0);
  spawner.enqueue(script);
  let signedIn = 0;
  const session = createLoginSession({ spawner, clock, spec: SPEC, terminal: false, onSignedIn: () => (signedIn += 1), ...options });
  return { spawner, clock, session, signedIn: () => signedIn };
}

describe("a sign-in session", () => {
  it("runs exactly the spec it was given, with stdin kept open, and relays the CLI's lines", async () => {
    const t = setup({ stdout: CLAUDE_FIRST });
    await flush();
    expect(t.spawner.calls).toEqual([SPEC]);
    expect(t.session.view()).toMatchObject({ state: "running", text: expect.stringContaining("https://claude.com/cai/oauth/authorize?code=true") });
    expect(t.session.view().text.endsWith("Paste code here if prompted >")).toBe(true);
  });

  it("forwards a line with a newline, and never shows the pasted code again, even when the CLI echoes it", async () => {
    const t = setup({ stdout: CLAUDE_FIRST });
    await flush();
    const code = "Zq81abcDEF_long-pasted-code#state123";
    expect(t.session.send({ line: code })).toMatchObject({ ok: true });
    expect(t.spawner.written).toEqual([`${code}\n`]);
    t.spawner.pushStdout(`${code}\nLogin successful.\n`);
    await flush();
    expect(t.session.view().text).not.toContain(code);
    expect(t.session.view().text).toContain("[redacted]");
  });

  it("masks known secrets the CLI prints (tokens, keys)", async () => {
    const t = setup({ stdout: ["token sk-ant-oat01-ABCDEFGHIJKLMNOPQRSTUV and eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXBhcnQ\n"] });
    await flush();
    expect(t.session.view().text).not.toMatch(/sk-ant-oat01-ABC|eyJhbGci/);
  });

  it("names the device code the CLI printed (codex), so it is easy to copy", async () => {
    const t = setup({ stdout: ["1. Open this link in your browser and sign in to your account\n   \u001b[94mhttps://auth.openai.com/codex/device\u001b[0m\n\n2. Enter this one-time code \u001b[90m(expires in 15 minutes)\u001b[0m\n   \u001b[94mXZIF-17WOH\u001b[0m\n"] });
    await flush();
    expect(t.session.view().code).toBe("XZIF-17WOH");
  });

  it("refuses an input line that is too long or holds control characters, and sends nothing", async () => {
    const t = setup({ stdout: ["> "] });
    await flush();
    expect(t.session.send({ line: "x".repeat(2049) })).toMatchObject({ ok: false, error: { code: "invalid_input" } });
    expect(t.session.send({ line: "code\nsecond command" })).toMatchObject({ ok: false, error: { code: "invalid_input" } });
    expect(t.session.send({ key: "up" })).toMatchObject({ ok: false, error: { code: "invalid_input" } });
    expect(t.spawner.written).toEqual([]);
  });

  it("sends keys and lines the way a terminal does when the CLI runs in one", async () => {
    const t = setup({ stdout: [" > 1. Google OAuth\n2. Use a Google Cloud project\n"] }, { terminal: true });
    await flush();
    t.session.send({ key: "down" });
    t.session.send({ key: "enter" });
    t.session.send({ line: "4/0AVGzR1A-pasted" });
    expect(t.spawner.written).toEqual(["\u001b[B", "\r", "4/0AVGzR1A-pasted\r"]);
  });

  it("becomes signed in when the CLI exits 0, once", async () => {
    const t = setup({ stdout: ["Login successful.\n"], exit: { code: 0, signal: null } });
    await flush();
    expect(t.session.view().state).toBe("signed_in");
    expect(t.signedIn()).toBe(1);
  });

  it("fails when the CLI exits otherwise, without a sign-in", async () => {
    const t = setup({ stdout: ["Error: timed out\n"], exit: { code: 1, signal: null } });
    await flush();
    expect(t.session.view()).toMatchObject({ state: "failed", message: expect.stringContaining("1") });
    expect(t.signedIn()).toBe(0);
  });

  it("is stopped after 10 minutes, the process group signalled and then killed", async () => {
    const t = setup({ stdout: ["waiting\n"], ignores: ["SIGTERM"] });
    await flush();
    expect(LOGIN_TIMEOUT_MS).toBe(600_000);
    for (let elapsed = 0; elapsed < LOGIN_TIMEOUT_MS; elapsed += LOGIN_IDLE_MS / 2) {
      t.session.view();
      t.clock.advance(LOGIN_IDLE_MS / 2);
    }
    await flush();
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    t.clock.advance(KILL_GRACE_MS);
    await flush();
    expect(t.spawner.signals).toEqual(["SIGTERM", "SIGKILL"]);
    expect(t.session.view().state).toBe("timed_out");
    expect(t.signedIn()).toBe(0);
  });

  it("is stopped when nobody follows it any more (the person left)", async () => {
    const t = setup({ stdout: ["waiting\n"] });
    await flush();
    t.clock.advance(LOGIN_IDLE_MS);
    await flush();
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(t.session.view().state).toBe("cancelled");
  });

  it("is ended on cancel, and takes no input after", async () => {
    const t = setup({ stdout: ["waiting\n"] });
    await flush();
    t.session.cancel();
    await flush();
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
    expect(t.session.view().state).toBe("cancelled");
    expect(t.session.send({ line: "late code" })).toMatchObject({ ok: false, error: { code: "ended" } });
  });

  it("types the opening command once the program is quiet after its first output (Pi's /login)", async () => {
    const t = setup({ stdout: ["\u001b[2J\u001b[1;1H pi v1.4.0"] }, { terminal: true, autoInput: { text: "/login\r", quietMs: 1500 } });
    await flush();
    expect(t.spawner.written).toEqual([]);
    t.clock.advance(1500);
    await flush();
    expect(t.spawner.written).toEqual(["/login\r"]);
    t.clock.advance(5000);
    expect(t.spawner.written).toEqual(["/login\r"]);
  });

  it("with a check, becomes signed in when the check holds after an input, and stops the program", async () => {
    let answer = false;
    const t = setup({ stdout: ["Paste the authorization code:"] }, { terminal: true, check: async () => answer, checkEveryMs: 3000 });
    await flush();
    t.session.send({ line: "4/0AVGzR1A-pasted" });
    await flush();
    expect(t.session.view().state).toBe("running");
    answer = true;
    t.clock.advance(3000);
    await flush();
    expect(t.session.view().state).toBe("signed_in");
    expect(t.signedIn()).toBe(1);
    expect(t.spawner.signals).toEqual(["SIGTERM"]);
  });

  it("with a check, an exit 0 alone is not a sign-in (the person left the program)", async () => {
    const t = setup({ stdout: ["bye\n"], exit: { code: 0, signal: null } }, { terminal: true, check: async () => false });
    await flush();
    expect(t.session.view().state).toBe("failed");
    expect(t.signedIn()).toBe(0);
  });

  it("fails readably when the program cannot start", async () => {
    const t = setup({ spawnError: "ENOENT" });
    await flush();
    expect(t.session.view()).toMatchObject({ state: "failed", message: expect.stringMatching(/could not be started/) });
  });
});
