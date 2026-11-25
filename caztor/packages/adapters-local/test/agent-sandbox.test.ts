import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { AGENT_CONFIG_PATHS, buildAgentSandboxedSpec, createAgentSandbox, SHARED_TURN_FOLDERS, type AgentSandboxProfile } from "../src/agent-sandbox.ts";
import type { SpawnSpec } from "../src/infra.ts";
import { FakeClock } from "./fakes/fake-clock.ts";
import { FakeSpawner } from "./fakes/fake-spawner.ts";
import { MemoryFileSystem } from "./fakes/memory-fs.ts";

const HOST_HOME = "/home/u";
const HOME = "/home/u/.config/caztor/users/alice-1/home";
const ROOT = "/home/u/proj";
const CLAUDE_REAL = "/home/u/.local/share/claude/versions/2.1.317";
const SYSTEM_FILES = ["/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf", "/etc/ld.so.cache", "/etc/localtime", "/etc/ssl/certs", "/etc/ca-certificates", "/etc/pki", "/etc/fonts"];

const PERSONAL = `${HOME}/.caztor-turns/${createHash("sha256").update(ROOT).digest("hex").slice(0, 32)}`;
const profile: AgentSandboxProfile = {
  bwrap: "/usr/bin/bwrap", tool: CLAUDE_REAL, hostHome: HOST_HOME, home: HOME, root: ROOT, readOnly: [CLAUDE_REAL], personal: PERSONAL,
  sharedFolders: [...SHARED_TURN_FOLDERS], agentConfig: [...AGENT_CONFIG_PATHS],
};
/** The profile of a project with no `.caztor/` folders and no CLI configuration yet: nothing of them to bind. */
const bare: AgentSandboxProfile = { ...profile, sharedFolders: [], agentConfig: [] };
/** What every collaborator turn gets after the project: `.caztor/` emptied, then only what a turn needs. */
const PROJECT_GUARDS = [
  "--tmpfs", `${ROOT}/.caztor`,
  "--ro-bind-try", `${ROOT}/.caztor/agents`, `${ROOT}/.caztor/agents`,
  "--ro-bind-try", `${ROOT}/.caztor/guides`, `${ROOT}/.caztor/guides`,
  "--ro-bind-try", `${ROOT}/.caztor/build`, `${ROOT}/.caztor/build`,
  "--bind", `${PERSONAL}/opencode-xdg`, `${ROOT}/.caztor/opencode-xdg`,
  "--bind", `${PERSONAL}/opencode-data-api`, `${ROOT}/.caztor/opencode-data-api`,
  "--bind", `${PERSONAL}/pi-sessions`, `${ROOT}/.caztor/pi-sessions`,
  "--bind", `${PERSONAL}/pi-agent-api`, `${ROOT}/.caztor/pi-agent-api`,
  "--ro-bind-try", `${ROOT}/.claude`, `${ROOT}/.claude`,
  "--ro-bind-try", `${ROOT}/.opencode`, `${ROOT}/.opencode`,
  "--ro-bind-try", `${ROOT}/.agents`, `${ROOT}/.agents`,
  "--ro-bind-try", `${ROOT}/.mcp.json`, `${ROOT}/.mcp.json`,
  "--ro-bind-try", `${ROOT}/opencode.json`, `${ROOT}/opencode.json`,
  "--ro-bind-try", `${ROOT}/opencode.jsonc`, `${ROOT}/opencode.jsonc`,
];
const spec: SpawnSpec = {
  file: "/home/u/.local/bin/claude",
  args: ["-p", "--output-format", "stream-json"],
  cwd: ROOT,
  env: { PATH: "/usr/bin", HOME, CLAUDE_CONFIG_DIR: `${HOME}/.claude`, TMPDIR: "/var/tmp/x", XDG_RUNTIME_DIR: "/run/user/1000", DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/1000/bus" },
  stdin: "Fix the typo",
};

const sources = (args: readonly string[]) =>
  args.flatMap((arg, index) => (["--bind", "--ro-bind", "--ro-bind-try", "--bind-try"].includes(arg) ? [args[index + 1]!] : []));

describe("buildAgentSandboxedSpec", () => {
  it("is the exact argument list: system read-only, the host's home hidden, then the CLI, the private home and the project", () => {
    expect(buildAgentSandboxedSpec(profile, spec)).toEqual({
      file: "/usr/bin/bwrap",
      cwd: ROOT,
      stdin: "Fix the typo",
      env: { PATH: "/usr/bin", HOME, CLAUDE_CONFIG_DIR: `${HOME}/.claude`, TMPDIR: "/tmp" },
      args: [
        "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64", "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        ...SYSTEM_FILES.flatMap((file) => ["--ro-bind-try", file, file]),
        "--ro-bind-try", "/etc/passwd", "/etc/passwd", "--ro-bind-try", "/etc/group", "/etc/group",
        "--tmpfs", HOST_HOME,
        "--ro-bind", CLAUDE_REAL, CLAUDE_REAL,
        "--bind", HOME, HOME,
        "--bind", ROOT, ROOT,
        ...PROJECT_GUARDS,
        "--chdir", ROOT, "--", CLAUDE_REAL, "-p", "--output-format", "stream-json",
      ],
    });
  });

  it("mounts the tmpfs over the host's home before anything under it, and never binds the home itself", () => {
    const { args } = buildAgentSandboxedSpec(profile, spec);
    const tmpfs = args.indexOf(HOST_HOME);
    expect(args[tmpfs - 1]).toBe("--tmpfs");
    args.forEach((arg, index) => {
      if (arg.startsWith(`${HOST_HOME}/`)) expect(index).toBeGreaterThan(tmpfs);
    });
    expect(sources(args)).not.toContain(HOST_HOME);
  });

  it("hides the project's .caztor/ (chat, state, snapshots) and gives the turn's own folders from the private home", () => {
    const { args } = buildAgentSandboxedSpec(profile, spec);
    const project = args.indexOf("--bind", args.indexOf(HOME) + 1);
    const hidden = args.indexOf(`${ROOT}/.caztor`);
    expect(args[hidden - 1]).toBe("--tmpfs");
    expect(hidden).toBeGreaterThan(project);
    const writable = args.flatMap((arg, index) => (arg === "--bind" ? [args[index + 2]!] : []));
    expect(writable.filter((target) => target.startsWith(`${ROOT}/.caztor`))).toEqual(["opencode-xdg", "opencode-data-api", "pi-sessions", "pi-agent-api"].map((name) => `${ROOT}/.caztor/${name}`));
    for (const target of writable.filter((target) => target.startsWith(`${ROOT}/.caztor`))) {
      expect(args[args.indexOf(target) - 1]!.startsWith(`${PERSONAL}/`)).toBe(true);
    }
    expect(args).not.toContain(`${ROOT}/.caztor/chat`);
    expect(args).not.toContain(`${ROOT}/.caztor/state.json`);
  });

  it("runs the command in a terminal through script when asked, with a wide screen", () => {
    const wrapped = buildAgentSandboxedSpec(profile, { ...spec, args: ["auth", "it's"] }, { terminal: "/usr/bin/script" });
    expect(wrapped.args.slice(-7)).toEqual(["--", "/usr/bin/script", "-q", "-e", "-c", `stty cols 300 rows 50 2>/dev/null; exec '${CLAUDE_REAL}' 'auth' 'it'\\''s'`, "/dev/null"]);
    expect(wrapped.env["SHELL"]).toBe("/bin/sh");
  });

  it("passes no D-Bus socket and no runtime folder", () => {
    const wrapped = buildAgentSandboxedSpec(profile, spec);
    expect(wrapped.env).not.toHaveProperty("DBUS_SESSION_BUS_ADDRESS");
    expect(wrapped.env).not.toHaveProperty("XDG_RUNTIME_DIR");
    expect(wrapped.args.some((arg) => arg.startsWith("/run"))).toBe(false);
  });
});

const ELF = "\u007fELF....";
const ok = { code: 0, signal: null } as const;

async function setup(layout: "claude" | "brew-script" | "brew-elf", options: { bwrap?: boolean; hostHome?: string | null; root?: string; protectedFolders?: string[] } = {}) {
  const files: Record<string, string> = {};
  if (options.bwrap !== false) files["/usr/bin/bwrap"] = ELF;
  if (layout === "claude") files[CLAUDE_REAL] = ELF;
  if (layout === "brew-script") {
    files["/opt/brew/lib/node_modules/pi/dist/cli.js"] = "#!/usr/bin/env node\nconsole.log(1)\n";
    files["/opt/brew/Cellar/node/26.8.2/bin/node"] = ELF;
  }
  if (layout === "brew-elf") files["/opt/brew/Cellar/opencode/1.19.0/bin/opencode"] = ELF;
  const fs = new MemoryFileSystem(files);
  for (const path of Object.keys(files)) await fs.chmod(path, 0o755);
  await fs.mkdir(HOME, { recursive: true });
  await fs.mkdir(ROOT, { recursive: true });
  await fs.mkdir("/home/u/.local/bin", { recursive: true });
  await fs.mkdir("/opt/brew/bin", { recursive: true });
  fs.symlink(CLAUDE_REAL, "/home/u/.local/bin/claude");
  fs.symlink("/opt/brew/lib/node_modules/pi/dist/cli.js", "/opt/brew/bin/pi");
  fs.symlink("/opt/brew/Cellar/node/26.8.2/bin/node", "/opt/brew/bin/node");
  fs.symlink("/opt/brew/Cellar/opencode/1.19.0/bin/opencode", "/opt/brew/bin/opencode");
  const spawner = new FakeSpawner();
  const env: Record<string, string> = { PATH: "/home/u/.local/bin:/opt/brew/bin:/usr/bin" };
  if (options.hostHome !== null) env["HOME"] = options.hostHome ?? HOST_HOME;
  const sandbox = createAgentSandbox({ fs, spawner, clock: new FakeClock(0), root: options.root ?? ROOT, env, ...(options.protectedFolders === undefined ? {} : { protectedFolders: options.protectedFolders }) });
  return { fs, spawner, sandbox };
}

const turnSpec = (file: string): SpawnSpec => ({ file, args: ["run"], cwd: ROOT, env: { PATH: "/usr/bin", HOME }, stdin: "go" });

describe("createAgentSandbox", () => {
  it("runs a native CLI from its real path, binding only that file and the libraries outside the system tree", async () => {
    const { spawner, sandbox } = await setup("claude");
    spawner.enqueue({ stdout: ["\tlibc.so.6 => /usr/lib/x86_64-linux-gnu/libc.so.6 (0x1)\n\t/lib64/ld-linux-x86-64.so.2 (0x2)\n"], exit: ok });
    spawner.enqueue({ stdout: ["2.1.317 (Claude Code)\n"], exit: ok });
    const wrapper = await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    expect(wrapper.ok).toBe(true);
    expect(spawner.calls[0]).toMatchObject({ file: "ldd", args: [CLAUDE_REAL] });
    expect(spawner.calls[1]).toEqual(buildAgentSandboxedSpec(bare, { file: CLAUDE_REAL, args: ["--version"], cwd: ROOT, env: { PATH: "/home/u/.local/bin:/opt/brew/bin:/usr/bin", HOME } }));
    if (!wrapper.ok) return;
    expect(wrapper.value(turnSpec("/home/u/.local/bin/claude"))).toEqual(buildAgentSandboxedSpec(bare, turnSpec("/home/u/.local/bin/claude")));
  });

  it("binds the whole install prefix of a script CLI and of the interpreter its first line names", async () => {
    const { spawner, sandbox } = await setup("brew-script");
    spawner.enqueue({ stdout: ["\tlibuv.so.1 => /opt/brew/lib/libuv.so.1 (0x1)\n"], exit: ok });
    spawner.enqueue({ stdout: ["0.80.0\n"], exit: ok });
    const wrapper = await sandbox.wrapper({ binary: "/opt/brew/bin/pi", home: HOME });
    expect(spawner.calls[0]).toMatchObject({ file: "ldd", args: ["/opt/brew/Cellar/node/26.8.2/bin/node"] });
    const probe = spawner.calls[1]!;
    expect(sources(probe.args).filter((source) => source.startsWith("/opt"))).toEqual(["/opt/brew"]);
    expect(probe.args.slice(-3)).toEqual(["--", "/opt/brew/lib/node_modules/pi/dist/cli.js", "--version"]);
    expect(wrapper.ok).toBe(true);
  });

  it("binds the prefix of a native CLI kept in a package cellar", async () => {
    const { spawner, sandbox } = await setup("brew-elf");
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stdout: ["1.19.0\n"], exit: ok });
    await sandbox.wrapper({ binary: "/opt/brew/bin/opencode", home: HOME });
    expect(sources(spawner.calls[1]!.args).filter((source) => source.startsWith("/opt"))).toEqual(["/opt/brew"]);
  });

  it("remembers a successful probe for the same CLI and home", async () => {
    const { spawner, sandbox } = await setup("claude");
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stdout: ["2.1.317\n"], exit: ok });
    await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    const again = await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    expect(again.ok).toBe(true);
    expect(spawner.calls).toHaveLength(2);
  });

  it("refuses when bwrap is not installed, without running anything", async () => {
    const { spawner, sandbox } = await setup("claude", { bwrap: false });
    expect(await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).toEqual({ ok: false, reason: expect.stringMatching(/Bubblewrap \(bwrap\) was not found/) });
    expect(spawner.calls).toEqual([]);
  });

  it("refuses when the probe inside the sandbox fails, naming the kernel's refusal", async () => {
    const { spawner, sandbox } = await setup("claude");
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stderr: ["bwrap: No permissions to create new namespace\n"], exit: { code: 1, signal: null } });
    const refused = await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    expect(refused).toEqual({ ok: false, reason: expect.stringMatching(/user namespaces/) });
  });

  it("does not remember a failed probe", async () => {
    const { spawner, sandbox } = await setup("claude");
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ exit: { code: 1, signal: null } });
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(false);
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stdout: ["2.1.317\n"], exit: ok });
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(true);
  });

  it("refuses when the host's home is not known, since it could not be hidden", async () => {
    const { spawner, sandbox } = await setup("claude", { hostHome: null });
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(false);
    expect(spawner.calls).toEqual([]);
  });

  it("refuses a project folder that holds the host's whole home", async () => {
    const { spawner, sandbox } = await setup("claude", { root: "/home" });
    const refused = await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    expect(refused).toEqual({ ok: false, reason: expect.stringMatching(/project folder/) });
    expect(spawner.calls).toEqual([]);
  });

  it("refuses a private home reached through a link, or one that is the host's home", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    fs.symlink(HOME, "/home/u/linked-home");
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: "/home/u/linked-home" })).ok).toBe(false);
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOST_HOME })).ok).toBe(false);
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: "relative/home" })).ok).toBe(false);
    expect(spawner.calls).toEqual([]);
  });

  it("refuses a CLI whose install folder would contain the private home or the project", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    await fs.writeFile(`${ROOT}/tool`, new TextEncoder().encode(ELF));
    await fs.chmod(`${ROOT}/tool`, 0o755);
    expect((await sandbox.wrapper({ binary: `${ROOT}/tool`, home: HOME })).ok).toBe(false);
    expect(spawner.calls).toEqual([]);
  });

  it("never mounts the folder of every person's private things and the users store, outside the host's home too", async () => {
    const outside = "/srv/cfg/caztor";
    const own = `${outside}/users/alice-1/home`;
    const { fs, spawner, sandbox } = await setup("claude", { protectedFolders: [outside] });
    await fs.mkdir(own, { recursive: true });
    await fs.mkdir(`${outside}/users/bob-2/home`, { recursive: true });
    // A CLI installed in the protected folder would mount it, and with it other people's folders.
    await fs.writeFile(`${outside}/users/bob-2/home/tool`, new TextEncoder().encode(ELF));
    await fs.chmod(`${outside}/users/bob-2/home/tool`, 0o755);
    expect(await sandbox.wrapper({ binary: `${outside}/users/bob-2/home/tool`, home: own })).toEqual({ ok: false, reason: expect.stringMatching(/cannot be mounted/) });
    // A private home outside the protected folder is not one Caztor made.
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(false);
    expect(spawner.calls).toEqual([]);
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stdout: ["2.1.317\n"], exit: ok });
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: own })).ok).toBe(true);
    const bound = sources(spawner.calls[1]!.args);
    expect(bound.filter((source) => source.startsWith(outside)).every((source) => source === own || source.startsWith(`${own}/`))).toBe(true);
    expect(bound).toContain(own);
  });

  it("refuses a project folder inside the protected folder", async () => {
    const { fs, spawner, sandbox } = await setup("claude", { protectedFolders: ["/home/u"] });
    void fs;
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(false);
    expect(spawner.calls).toEqual([]);
  });

  it("makes the person's own turn folders for this project in their private home, closed to others", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    spawner.enqueue({ stdout: [""], exit: ok });
    spawner.enqueue({ stdout: ["2.1.317\n"], exit: ok });
    expect((await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(true);
    const args = spawner.calls[1]!.args;
    const source = args[args.indexOf(`${ROOT}/.caztor/pi-sessions`) - 1]!;
    expect(source).toMatch(new RegExp(`^${HOME}/\\.caztor-turns/[0-9a-f]{32}/pi-sessions$`));
    expect((await fs.stat(source)).isDirectory()).toBe(true);
    expect((await fs.stat(source)).mode & 0o077).toBe(0);
  });

  it("refuses a project whose .caztor is a link, since the hiding would land elsewhere", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    await fs.mkdir("/home/u/elsewhere", { recursive: true });
    fs.symlink("/home/u/elsewhere", `${ROOT}/.caztor`);
    expect(await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).toEqual({ ok: false, reason: expect.stringMatching(/\.caztor/) });
    expect(spawner.calls).toEqual([]);
  });

  /** A sandbox whose probe already passed, for checks made when a later turn's spec is built. */
  async function probed() {
    const made = await setup("claude");
    made.spawner.enqueue({ stdout: [""], exit: ok });
    made.spawner.enqueue({ stdout: ["2.1.317\n"], exit: ok });
    expect((await made.sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).ok).toBe(true);
    return made;
  }
  const turnArgs = async (sandbox: Awaited<ReturnType<typeof setup>>["sandbox"]) => {
    const wrapper = await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME });
    if (!wrapper.ok) throw new Error(wrapper.reason);
    return wrapper.value(turnSpec("/home/u/.local/bin/claude")).args;
  };

  it("binds the project's CLI configuration and shared .caztor folders read-only when they are plain", async () => {
    const { fs, sandbox } = await probed();
    for (const dir of [".claude", ".caztor/agents", ".caztor/build"]) await fs.mkdir(`${ROOT}/${dir}`, { recursive: true });
    await fs.writeFile(`${ROOT}/.mcp.json`, new TextEncoder().encode("{}"));
    const bound = sources(await turnArgs(sandbox));
    expect(bound.filter((source) => source.startsWith(`${ROOT}/`))).toEqual([`${ROOT}/.caztor/agents`, `${ROOT}/.caztor/build`, `${ROOT}/.claude`, `${ROOT}/.mcp.json`]);
  });

  it("never binds a link a turn left at a configuration path or a shared folder, checked again for every turn", async () => {
    const { fs, sandbox } = await probed();
    await fs.mkdir(`${ROOT}/.caztor`, { recursive: true });
    await fs.mkdir("/home/u/.config/caztor", { recursive: true });
    // What a collaborator's turn can leave in the writable project for the next one.
    fs.symlink("../../u", `${ROOT}/.claude`);
    fs.symlink(".caztor", `${ROOT}/.opencode`);
    fs.symlink("../.config/caztor", `${ROOT}/.agents`);
    fs.symlink("/nowhere", `${ROOT}/.mcp.json`);
    fs.symlink("/home/u", `${ROOT}/.caztor/agents`);
    await fs.mkdir(`${ROOT}/real-guides`, { recursive: true });
    fs.symlink(`${ROOT}/real-guides`, `${ROOT}/.caztor/guides`);
    const args = await turnArgs(sandbox);
    expect(sources(args).filter((source) => source.startsWith(`${ROOT}/`) && source !== ROOT)).toEqual([]);
    // The links stay as they are inside the sandbox, and a dangling one does not stop the turn.
    expect(args).toContain("--chdir");
  });

  it("refuses a turn whose own folder in the private home became a link after the probe", async () => {
    const { fs, sandbox } = await probed();
    await fs.rm(`${PERSONAL}/opencode-xdg`, { recursive: true });
    fs.symlink("/home/u/.config", `${PERSONAL}/opencode-xdg`);
    expect(await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).toEqual({ ok: false, reason: expect.stringMatching(/not a plain folder/) });
  });

  it("refuses a turn whose .caztor became a link after the probe", async () => {
    const { fs, sandbox } = await probed();
    fs.symlink("/home/u", `${ROOT}/.caztor`);
    expect(await sandbox.wrapper({ binary: "/home/u/.local/bin/claude", home: HOME })).toEqual({ ok: false, reason: expect.stringMatching(/\.caztor/) });
  });

  it("mounts only the package folder of a CLI installed with an npm prefix in the host's home, never the prefix", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    const pkg = "/home/u/.local/lib/node_modules/@acme/cli";
    await fs.mkdir(`${pkg}/dist`, { recursive: true });
    await fs.writeFile(`${pkg}/dist/cli.js`, new TextEncoder().encode("#!/usr/bin/node\nconsole.log(1)\n"));
    await fs.chmod(`${pkg}/dist/cli.js`, 0o755);
    await fs.mkdir("/home/u/.local/share/opencode", { recursive: true });
    await fs.writeFile("/usr/bin/node", new TextEncoder().encode("node"));
    spawner.enqueue({ stdout: ["1.0.0\n"], exit: ok });
    expect((await sandbox.wrapper({ binary: `${pkg}/dist/cli.js`, home: HOME })).ok).toBe(true);
    const bound = sources(spawner.calls.at(-1)!.args);
    expect(bound).toContain(pkg);
    expect(bound).not.toContain("/home/u/.local");
    expect(bound.filter((path) => path.startsWith("/home/u/.local"))).toEqual([pkg]);
  });

  it("mounts only the formula folder of a CLI kept in a package cellar inside the host's home", async () => {
    const { fs, spawner, sandbox } = await setup("claude");
    const formula = "/home/u/.brew/Cellar/tool/2.0";
    await fs.mkdir(`${formula}/bin`, { recursive: true });
    await fs.writeFile(`${formula}/bin/tool`, new TextEncoder().encode("plain"));
    await fs.chmod(`${formula}/bin/tool`, 0o755);
    spawner.enqueue({ stdout: ["2.0\n"], exit: ok });
    expect((await sandbox.wrapper({ binary: `${formula}/bin/tool`, home: HOME })).ok).toBe(true);
    expect(sources(spawner.calls.at(-1)!.args).filter((path) => path.startsWith("/home/u/.brew"))).toEqual([formula]);
  });
});
