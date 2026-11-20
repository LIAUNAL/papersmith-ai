import { describe, expect, it } from "vitest";
import { parseCommand, parseLifetime, parseProjectDir } from "../src/cli.ts";

describe("parseProjectDir", () => {
  it("takes the first argument after the script as the project folder", () => {
    expect(parseProjectDir(["node", "main.ts", "/work/thesis"])).toEqual({ ok: true, projectDir: "/work/thesis" });
  });

  it("ignores a leading -- separator that npm start inserts", () => {
    expect(parseProjectDir(["node", "main.ts", "--", "/work/thesis"])).toEqual({ ok: true, projectDir: "/work/thesis" });
  });

  it.each([
    ["no argument", ["node", "main.ts"]],
    ["an empty argument", ["node", "main.ts", ""]],
    ["more than one folder", ["node", "main.ts", "a", "b"]],
    ["an option instead of a folder", ["node", "main.ts", "--port=1"]],
  ])("returns a usage message for %s", (_label, argv) => {
    const result = parseProjectDir(argv);
    expect(result.ok).toBe(false);
    expect(result).toMatchObject({ usage: expect.stringContaining("Usage: npm start -- <projectDir>") });
  });
});

describe("parseCommand", () => {
  const argv = (...args: string[]) => ["node", "main.ts", "--", ...args];
  const local = { host: "127.0.0.1", publicNames: [], secure: false };

  it("serves a project on loopback by default, as before", () => {
    expect(parseCommand(argv("/work/thesis"), {})).toEqual({ ok: true, command: "serve", projectDir: "/work/thesis", exposure: local });
  });

  it("reads --host, repeated --public-name and --secure, in either form", () => {
    expect(parseCommand(argv("/p", "--host", "0.0.0.0", "--public-name", "box.ts.net", "--public-name=box.lan:4317", "--secure"), {})).toEqual({
      ok: true,
      command: "serve",
      projectDir: "/p",
      exposure: { host: "0.0.0.0", publicNames: ["box.ts.net", "box.lan:4317"], secure: true },
    });
    expect(parseCommand(argv("--host=100.64.0.2", "/p", "--public-name", "box"), {})).toMatchObject({ exposure: { host: "100.64.0.2", publicNames: ["box"] } });
  });

  it("reads --embed-origin, in either form, or CAZTOR_EMBED_ORIGIN, only when serving", () => {
    expect(parseCommand(argv("/p", "--embed-origin", "http://127.0.0.1:8765"), {})).toEqual({ ok: true, command: "serve", projectDir: "/p", exposure: local, embedOrigin: "http://127.0.0.1:8765" });
    expect(parseCommand(argv("--embed-origin=http://localhost:9000", "/p"), {})).toMatchObject({ embedOrigin: "http://localhost:9000" });
    expect(parseCommand(argv("/p"), { CAZTOR_EMBED_ORIGIN: "http://127.0.0.1:1" })).toMatchObject({ embedOrigin: "http://127.0.0.1:1" });
    expect(parseCommand(argv("/p", "--embed-origin"), {})).toMatchObject({ ok: false });
    expect(parseCommand(argv("users", "--embed-origin", "http://x"), {})).toMatchObject({ ok: false });
  });

  it("takes the same settings from CAZTOR_HOST, CAZTOR_PUBLIC_NAME and CAZTOR_SECURE, with options winning", () => {
    const env = { CAZTOR_HOST: "0.0.0.0", CAZTOR_PUBLIC_NAME: "a.ts.net, b.ts.net", CAZTOR_SECURE: "1" };
    expect(parseCommand(argv("/p"), env)).toMatchObject({ exposure: { host: "0.0.0.0", publicNames: ["a.ts.net", "b.ts.net"], secure: true } });
    expect(parseCommand(argv("/p", "--host", "127.0.0.1", "--public-name", "c.ts.net"), env)).toMatchObject({ exposure: { host: "127.0.0.1", publicNames: ["c.ts.net"] } });
  });

  it("reads the user commands", () => {
    expect(parseCommand(argv("invite", "Ana", "Lopez", "--public-name", "box.ts.net"), {})).toEqual({ ok: true, command: "invite", name: "Ana Lopez", exposure: { ...local, publicNames: ["box.ts.net"] } });
    expect(parseCommand(argv("users"), {})).toEqual({ ok: true, command: "users" });
    expect(parseCommand(argv("trust-build", "/work/paper"), {})).toEqual({ ok: true, command: "trust-build", projectDir: "/work/paper" });
    expect(parseCommand(argv("trust-build"), {})).toMatchObject({ ok: false });
    expect(parseCommand(argv("trust-build", "/p", "--embed-origin", "http://x"), {})).toMatchObject({ ok: false });
    expect(parseCommand(argv("revoke", "abc"), {})).toEqual({ ok: true, command: "revoke", id: "abc" });
  });

  it("reads how long an invite's key lasts from --for, in either form", () => {
    expect(parseCommand(argv("invite", "Ana", "--for", "24h", "--public-name", "box.ts.net"), {})).toEqual({
      ok: true,
      command: "invite",
      name: "Ana",
      lifetime: "24h",
      exposure: { ...local, publicNames: ["box.ts.net"] },
    });
    expect(parseCommand(argv("invite", "Ana", "--for=2026-12-01T10:00"), {})).toMatchObject({ command: "invite", lifetime: "2026-12-01T10:00" });
    expect(parseCommand(argv("invite", "Ana"), {})).not.toHaveProperty("lifetime");
  });

  it.each([
    ["no argument", argv()],
    ["two folders", argv("a", "b")],
    ["an unknown option", argv("/p", "--port=1")],
    ["an option without its value", argv("/p", "--host")],
    ["invite without a name", argv("invite")],
    ["revoke without an id", argv("revoke")],
    ["users with an argument", argv("users", "x")],
    ["--for without a value", argv("invite", "Ana", "--for")],
    ["--for when serving", argv("/p", "--for", "7d")],
    ["--for with users", argv("users", "--for", "7d")],
  ])("returns the usage for %s", (_label, args) => {
    expect(parseCommand(args, {})).toEqual({ ok: false, usage: expect.stringContaining("npm start -- invite <name>") });
  });
});

describe("parseLifetime", () => {
  const now = Date.UTC(2026, 10, 3, 12, 0, 0);
  it.each([
    ["90m", 90],
    ["24h", 24 * 60],
    ["7d", 7 * 24 * 60],
    ["30d", 30 * 24 * 60],
    ["2026-11-03T13:30:00Z", 90],
    ["2026-11-04T12:00:00.000Z", 24 * 60],
    // A part of a minute counts as a whole one, so the key lasts at least until the time given.
    ["2026-11-03T12:10:30Z", 11],
  ])("reads %s as %i minutes", (value, minutes) => {
    expect(parseLifetime(value, now)).toBe(minutes);
  });

  it.each(["", "7", "7w", "d7", "-5m", "1.5h", "tomorrow", "2026-13-45"])("refuses %j", (value) => {
    expect(parseLifetime(value, now)).toBeNull();
  });
});
