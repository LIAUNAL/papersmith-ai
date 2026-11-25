import { mkdtempSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { runUserCommand } from "../src/user-commands.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const home = () => {
  const dir = realpathSync(mkdtempSync(join(tmpdir(), "caztor-cmd-")));
  dirs.push(dir);
  return dir;
};
const exposure = (publicNames: string[], secure = false) => ({ host: "127.0.0.1", publicNames, secure });

const NOW = Date.UTC(2026, 10, 3, 12, 0, 0);
const KEY = /Access key: ([A-HJ-NP-Z2-9]{5}(?:-[A-HJ-NP-Z2-9]{5}){3})/;

describe("user commands", () => {
  it("invites with a link and a key shown once, lists and revokes through the users store, keeping no raw key", async () => {
    const dir = home();
    const env = { HOME: dir };
    const deps = { fs: nodeFileSystem, env, now: () => NOW };
    const invited = await runUserCommand({ ok: true, command: "invite", name: "Ana", exposure: exposure(["box.ts.net"], true) }, deps);
    expect(invited.code).toBe(0);
    const text = invited.lines.join("\n");
    const link = /Link: https:\/\/box\.ts\.net\/invite\/([A-Za-z0-9_-]{22})$/m.exec(text);
    const key = KEY.exec(text);
    expect(link).not.toBeNull();
    expect(key).not.toBeNull();
    expect(text).toContain("Invite for Ana, until 2026-11-10T12:00:00.000Z (7 days):");
    expect(text).toContain("The key is shown only now.");
    const file = join(dir, ".config", "caztor", "users.json");
    expect(statSync(file).mode & 0o777).toBe(0o600);
    expect(readFileSync(file, "utf8")).not.toContain(key![1]);
    expect(readFileSync(file, "utf8")).not.toContain(key![1]!.replaceAll("-", ""));

    const listed = await runUserCommand({ ok: true, command: "users" }, deps);
    expect(listed.code).toBe(0);
    const id = (JSON.parse(readFileSync(file, "utf8")) as { users: Array<{ id: string }> }).users[0]!.id;
    expect(listed.lines).toEqual([`${id}  Ana  signed in: 0`, `  key ${link![1]}  expires 2026-11-10T12:00:00.000Z (in 7 days)  signed in: 0`]);

    const revoked = await runUserCommand({ ok: true, command: "revoke", id }, deps);
    expect(revoked.code).toBe(0);
    expect((await runUserCommand({ ok: true, command: "users" }, deps)).lines.join("\n")).toContain("No collaborators yet.");
    expect((await runUserCommand({ ok: true, command: "revoke", id }, deps)).code).toBe(1);
  });

  it("takes the key's lifetime from --for, refuses one out of bounds, and shows when each key ended", async () => {
    const dir = home();
    let clock = NOW;
    const deps = { fs: nodeFileSystem, env: { HOME: dir }, now: () => clock };
    const run = (lifetime: string, name = "Ana") => runUserCommand({ ok: true, command: "invite", name, lifetime, exposure: exposure(["box.ts.net"]) }, deps);
    const short = await run("90m");
    expect(short.lines[0]).toBe("Invite for Ana, until 2026-11-03T13:30:00.000Z (90 minutes):");
    const dated = await run("2026-11-05T12:00:00Z", "Bo");
    expect(dated.lines[0]).toBe("Invite for Bo, until 2026-11-05T12:00:00.000Z (2 days):");
    for (const bad of ["5m", "366d", "2026-11-01T00:00:00Z"]) {
      const refused = await run(bad);
      expect(refused.code, bad).toBe(1);
      expect(refused.lines).toEqual(["Choose how long the key lasts: from 10 minutes to 365 days."]);
    }
    const unreadable = await run("soon");
    expect(unreadable.code).toBe(1);
    expect(unreadable.lines.join("\n")).toContain("--for");
    clock += 2 * 60 * 60_000;
    const listed = (await runUserCommand({ ok: true, command: "users" }, deps)).lines.join("\n");
    expect(listed).toContain("expired 2026-11-03T13:30:00.000Z");
    // 46 hours left: rounded to the nearest day.
    expect(listed).toContain("expires 2026-11-05T12:00:00.000Z (in 2 days)");
  });

  it("revokes one key by its id, and says when a key is locked or an old invite", async () => {
    const dir = home();
    const deps = { fs: nodeFileSystem, env: { HOME: dir }, now: () => NOW };
    const invited = await runUserCommand({ ok: true, command: "invite", name: "Ana", exposure: exposure(["box.ts.net"]) }, deps);
    const inviteId = /\/invite\/([A-Za-z0-9_-]{22})/.exec(invited.lines.join("\n"))![1]!;
    const file = join(dir, ".config", "caztor", "users.json");
    const stored = JSON.parse(readFileSync(file, "utf8")) as { invites: Array<Record<string, unknown>> };
    stored.invites[0]!["failures"] = 10;
    stored.invites.push({ id: "old-abcdefabcdefabcdefabcd", hash: "0".repeat(64), userId: stored.invites[0]!["userId"], createdAt: NOW, expiresAt: NOW + 60_000, failures: 0, legacy: true });
    writeFileSync(file, JSON.stringify({ version: 2, ...stored, users: (JSON.parse(readFileSync(file, "utf8")) as { users: unknown[] }).users }), { mode: 0o600 });
    const listed = (await runUserCommand({ ok: true, command: "users" }, deps)).lines.join("\n");
    expect(listed).toContain(`key ${inviteId}  locked after 10 wrong keys`);
    expect(listed).toContain("key old-abcdefabcdefabcdefabcd  old invite, create a new one");
    const revoked = await runUserCommand({ ok: true, command: "revoke", id: inviteId }, deps);
    expect(revoked).toEqual({ code: 0, lines: [`Revoked key ${inviteId}. The browsers signed in with it are signed out.`] });
    expect((await runUserCommand({ ok: true, command: "users" }, deps)).lines.join("\n")).not.toContain(inviteId);
  });

  it("refuses an invite without a public name, since the link would not reach anyone", async () => {
    const dir = home();
    const result = await runUserCommand({ ok: true, command: "invite", name: "Ana", exposure: exposure([]) }, { fs: nodeFileSystem, env: { HOME: dir } });
    expect(result.code).toBe(1);
    expect(result.lines.join("\n")).toContain("--public-name");
    expect(() => statSync(join(dir, ".config", "caztor", "users.json"))).toThrow();
  });
});
