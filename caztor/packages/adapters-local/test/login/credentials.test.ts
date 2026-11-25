import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { nodeFileSystem } from "../../src/node-infra.ts";
import { signedInProviders } from "../../src/login/credentials.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function home(): string {
  const dir = realpathSync(mkdtempSync(join(tmpdir(), "caztor-creds-")));
  dirs.push(dir);
  return dir;
}

function put(path: string, text = "{}"): void {
  mkdirSync(path.slice(0, path.lastIndexOf("/")), { recursive: true });
  writeFileSync(path, text);
}

describe("providers signed in on this computer", () => {
  it("names Claude Code, Pi, opencode and Antigravity when their own sign-in files exist, without reading them", async () => {
    const h = home();
    put(`${h}/.claude/.credentials.json`);
    put(`${h}/.pi/agent/auth.json`, '{"anthropic":{}}');
    put(`${h}/.local/share/opencode/auth.json`);
    put(`${h}/.gemini/antigravity-cli/antigravity-oauth-token`, "token");
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual(["claude", "pi", "opencode", "antigravity"]);
  });

  it("does not count Pi as signed in while its auth.json names no provider", async () => {
    const h = home();
    put(`${h}/.pi/agent/auth.json`, "{}");
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual([]);
    put(`${h}/.pi/agent/auth.json`, "not json");
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual([]);
    put(`${h}/.pi/agent/auth.json`, JSON.stringify({ anthropic: { type: "oauth" } }));
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual(["pi"]);
  });

  it("names none in a home without sign-ins, and ignores empty files, folders and links", async () => {
    const h = home();
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual([]);
    put(`${h}/.claude/.credentials.json`, "");
    mkdirSync(`${h}/.pi/agent/auth.json`, { recursive: true });
    put(`${h}/elsewhere.json`);
    mkdirSync(`${h}/.local/share/opencode`, { recursive: true });
    symlinkSync(`${h}/elsewhere.json`, `${h}/.local/share/opencode/auth.json`);
    expect(await signedInProviders(nodeFileSystem, { HOME: h })).toEqual([]);
  });

  it("follows CLAUDE_CONFIG_DIR, PI_CODING_AGENT_DIR and XDG_DATA_HOME, and a Claude token in the environment", async () => {
    const h = home();
    put(`${h}/claude-conf/.credentials.json`);
    put(`${h}/pi-dir/auth.json`, '{"anthropic":{}}');
    put(`${h}/data/opencode/auth.json`);
    expect(await signedInProviders(nodeFileSystem, { HOME: h, CLAUDE_CONFIG_DIR: `${h}/claude-conf`, PI_CODING_AGENT_DIR: `${h}/pi-dir`, XDG_DATA_HOME: `${h}/data` })).toEqual(["claude", "pi", "opencode"]);
    expect(await signedInProviders(nodeFileSystem, { HOME: home(), CLAUDE_CODE_OAUTH_TOKEN: "t" })).toEqual(["claude"]);
  });
});
