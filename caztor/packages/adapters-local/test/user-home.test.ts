import { describe, expect, it } from "vitest";
import { collaboratorEnv, ensureUserHome, userHomePaths } from "../src/user-home.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

cleanupSandboxes();

const HOST_ENV = {
  PATH: "/usr/bin",
  HOME: "/home/host",
  LANG: "en_US.UTF-8",
  TMPDIR: "/tmp",
  HTTPS_PROXY: "http://proxy:3128",
  XDG_CONFIG_HOME: "/home/host/.config",
  XDG_DATA_HOME: "/home/host/.local/share",
  XDG_RUNTIME_DIR: "/run/user/1000",
  DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/1000/bus",
  CLAUDE_CONFIG_DIR: "/home/host/.claude",
  CLAUDE_CODE_OAUTH_TOKEN: "host-oauth-token",
  CODEX_HOME: "/home/host/.codex",
  PI_CODING_AGENT_DIR: "/home/host/.pi/agent",
  ANTHROPIC_API_KEY: "sk-host-key",
};
const HOME = "/cfg/caztor/users/alice-1/home";

describe("the environment of a collaborator's turn", () => {
  it("points every CLI at the private folder and keeps only the host's harmless variables", () => {
    for (const provider of ["claude", "codex", "opencode", "pi"] as const) {
      expect(collaboratorEnv(HOST_ENV, HOME, provider)).toEqual({
        PATH: "/usr/bin",
        LANG: "en_US.UTF-8",
        TMPDIR: "/tmp",
        HTTPS_PROXY: "http://proxy:3128",
        HOME,
        CLAUDE_CONFIG_DIR: `${HOME}/.claude`,
        CODEX_HOME: `${HOME}/.codex`,
        XDG_CONFIG_HOME: `${HOME}/.config`,
        XDG_DATA_HOME: `${HOME}/.local/share`,
        XDG_STATE_HOME: `${HOME}/.local/state`,
        XDG_CACHE_HOME: `${HOME}/.cache`,
        PI_CODING_AGENT_DIR: `${HOME}/.pi/agent`,
      });
    }
  });

  it("gives agy HOME alone, without D-Bus or a runtime folder, so its login lands in a file and not the host keyring", () => {
    const env = collaboratorEnv(HOST_ENV, HOME, "antigravity");
    expect(env).toEqual({ PATH: "/usr/bin", LANG: "en_US.UTF-8", TMPDIR: "/tmp", HTTPS_PROXY: "http://proxy:3128", HOME });
    expect(env).not.toHaveProperty("DBUS_SESSION_BUS_ADDRESS");
    expect(env).not.toHaveProperty("XDG_RUNTIME_DIR");
  });
});

describe.each(implementations)("a collaborator's private folder: %s", (_name, create) => {
  async function setup() {
    const box = create();
    const configHome = `${box.root}/config`;
    const project = `${box.root}/papers/paper`;
    await box.fs.mkdir(configHome, { recursive: true });
    await box.fs.mkdir(project, { recursive: true });
    const uid = (await box.fs.lstat(configHome)).uid;
    return { ...box, configHome, project, uid };
  }

  it("is created 0700 under the configuration folder, outside every project", async () => {
    const t = await setup();
    const made = await ensureUserHome({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1", projectRoot: t.project });
    const { home, dir } = userHomePaths(t.configHome, "alice-1");
    expect(made).toEqual({ ok: true, value: home });
    expect(home).toBe(`${t.configHome}/caztor/users/alice-1/home`);
    for (const folder of [`${t.configHome}/caztor/users`, dir, home]) expect((await t.fs.lstat(folder)).mode).toBe(0o700);
    expect(home.startsWith(`${t.project}/`)).toBe(false);
    expect(await ensureUserHome({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1", projectRoot: t.project })).toEqual({ ok: true, value: home });
  });

  it("is refused inside the open project", async () => {
    const t = await setup();
    const made = await ensureUserHome({ fs: t.fs, configHome: `${t.project}/cfg`, uid: t.uid, userId: "alice-1", projectRoot: t.project });
    expect(made).toMatchObject({ ok: false, error: { message: expect.stringContaining("inside the project") } });
  });

  it("is refused when it is a link, or reachable by other users", async () => {
    const t = await setup();
    const { dir, home } = userHomePaths(t.configHome, "alice-1");
    await t.fs.mkdir(dir, { recursive: true, mode: 0o700 });
    for (const folder of [`${t.configHome}/caztor`, `${t.configHome}/caztor/users`, dir]) await t.fs.chmod(folder, 0o700);
    await t.fs.mkdir(`${t.root}/elsewhere`, { mode: 0o700 });
    t.symlink(`${t.root}/elsewhere`, home);
    expect(await ensureUserHome({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1", projectRoot: t.project })).toMatchObject({ ok: false, error: { message: expect.stringContaining("link") } });
    await t.fs.rm(home);
    await t.fs.mkdir(home, { mode: 0o700 });
    await t.fs.chmod(home, 0o755);
    expect(await ensureUserHome({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId: "alice-1", projectRoot: t.project })).toMatchObject({ ok: false, error: { message: expect.stringContaining("other users") } });
  });

  it("refuses a hostile user id", async () => {
    const t = await setup();
    for (const userId of ["..", "a/b", "host", ""]) {
      expect(await ensureUserHome({ fs: t.fs, configHome: t.configHome, uid: t.uid, userId, projectRoot: t.project })).toMatchObject({ ok: false });
      expect(() => userHomePaths(t.configHome, userId)).toThrow(/user id/i);
    }
    expect(await t.fs.readdir(t.configHome)).toEqual([]);
  });
});
