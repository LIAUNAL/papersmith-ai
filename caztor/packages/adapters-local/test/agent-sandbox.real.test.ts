import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { AGENT_CONFIG_PATHS, buildAgentSandboxedSpec, createAgentSandbox, SHARED_TURN_FOLDERS, type AgentSandboxProfile } from "../src/agent-sandbox.ts";
import type { ChildHandle, SpawnSpec } from "../src/infra.ts";
import { createNodeSpawner, nodeFileSystem, systemClock } from "../src/index.ts";
import { resolveBinary } from "../src/providers/resolve-binary.ts";
import { scanClaudeProjectConfig } from "../src/providers/project-config.ts";
import { createTrustSeal } from "../src/trust-seal.ts";

/**
 * Runs the real bubblewrap. Only with `CAZTOR_REAL_BIN=1` and `CAZTOR_REAL_SANDBOX=1`. No CLI gets a prompt or a login:
 * each runs `--version` only, with HOME and every XDG folder in a scratch folder.
 */
const enabled = process.env["CAZTOR_REAL_BIN"] === "1" && process.env["CAZTOR_REAL_SANDBOX"] === "1";
const dirs: string[] = [];
afterAll(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

const spawner = createNodeSpawner();
const PATH = process.env["PATH"] ?? "/usr/bin:/bin";

function scratch() {
  const base = realpathSync(mkdtempSync(join(tmpdir(), "caztor-agent-sandbox-")));
  dirs.push(base);
  const hostHome = join(base, "host");
  const config = join(hostHome, ".config");
  const home = join(config, "caztor", "users", "alice-1", "home");
  const root = join(hostHome, "papers", "paper");
  for (const dir of [home, root]) mkdirSync(dir, { recursive: true, mode: 0o700 });
  writeFileSync(join(hostHome, "canary.txt"), "host secret");
  writeFileSync(join(config, "caztor", "users.json"), "{}");
  mkdirSync(join(config, "caztor", "users", "bob-2", "home"), { recursive: true });
  writeFileSync(join(config, "caztor", "users", "bob-2", "home", "bob.txt"), "bob's");
  writeFileSync(join(root, "main.tex"), "x");
  const personal = join(home, ".caztor-turns", "k");
  for (const name of ["opencode-xdg", "opencode-data-api", "pi-sessions", "pi-agent-api"]) mkdirSync(join(personal, name), { recursive: true, mode: 0o700 });
  return { base, hostHome, config, home, root, personal };
}

async function runSpec(spec: SpawnSpec): Promise<{ code: number | null; stdout: string; stderr: string }> {
  const child = spawner.spawn(spec);
  const read = async (stream: AsyncIterable<Uint8Array>) => {
    let text = "";
    for await (const chunk of stream) text += new TextDecoder().decode(chunk);
    return text;
  };
  const [stdout, stderr] = await Promise.all([read(child.stdout), read(child.stderr)]);
  return { code: (await child.exit).code, stdout, stderr };
}

/** Every shared folder and configuration path bound, as for a project where all of them are plain. */
const ALL = { sharedFolders: [...SHARED_TURN_FOLDERS], agentConfig: [...AGENT_CONFIG_PATHS] };

const env = (home: string) => ({
  PATH,
  HOME: home,
  XDG_CONFIG_HOME: `${home}/.config`,
  XDG_DATA_HOME: `${home}/.local/share`,
  XDG_STATE_HOME: `${home}/.local/state`,
  XDG_CACHE_HOME: `${home}/.cache`,
});

describe.skipIf(!enabled)("the agent sandbox with the real bubblewrap", () => {
  it("shows a canary in the hidden host home to nobody, nor the users store or another person's folder", async () => {
    const t = scratch();
    const profile: AgentSandboxProfile = { bwrap: (await resolveBinary(nodeFileSystem, "bwrap", PATH))!, tool: "/bin/sh", hostHome: t.hostHome, home: t.home, root: t.root, readOnly: [], personal: t.personal, ...ALL };
    const script = [
      `cat ${t.hostHome}/canary.txt`,
      `cat ${t.config}/caztor/users.json`,
      `cat ${t.config}/caztor/users/bob-2/home/bob.txt`,
      `ls -A ${t.hostHome}`,
      `ls -A ${t.config}/caztor/users`,
      `echo ok > ${t.home}/written && echo ok > ${t.root}/written && echo HOME=$HOME TMPDIR=$TMPDIR DBUS=\${DBUS_SESSION_BUS_ADDRESS-none} RUNTIME=\${XDG_RUNTIME_DIR-none}`,
    ].join("; ");
    const result = await runSpec(buildAgentSandboxedSpec(profile, { file: "/bin/sh", args: ["-c", script], cwd: t.root, env: { ...env(t.home), DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/1000/bus", XDG_RUNTIME_DIR: "/run/user/1000" } }));
    expect(result.stdout).not.toContain("host secret");
    expect(result.stdout).not.toContain("bob's");
    expect(result.stdout).not.toContain("{}");
    const lines = result.stdout.trim().split("\n");
    // Only the folders bwrap made to mount the private home and the project on the tmpfs.
    expect(lines).toContain(".config");
    expect(lines).toContain("papers");
    expect(lines).not.toContain("canary.txt");
    expect(lines).toContain("alice-1");
    expect(lines).not.toContain("bob-2");
    expect(lines.at(-1)).toBe(`HOME=${t.home} TMPDIR=/tmp DBUS=none RUNTIME=none`);
    expect(result.stderr).toMatch(/canary\.txt: No such file/);
  });

  it("shows the real host home as an empty tmpfs", async () => {
    const t = scratch();
    const realHome = realpathSync(homedir());
    const profile: AgentSandboxProfile = { bwrap: (await resolveBinary(nodeFileSystem, "bwrap", PATH))!, tool: "/bin/ls", hostHome: realHome, home: t.home, root: t.root, readOnly: [], personal: t.personal, ...ALL };
    const result = await runSpec(buildAgentSandboxedSpec(profile, { file: "/bin/ls", args: ["-A", realHome], cwd: t.root, env: env(t.home) }));
    expect(result.code).toBe(0);
    expect(result.stdout).toBe("");
  });

  it("ends the sandboxed child when its group is signalled", async () => {
    const t = scratch();
    const marker = `${Math.floor(Math.random() * 1e6) + 1000}.5`;
    const profile: AgentSandboxProfile = { bwrap: (await resolveBinary(nodeFileSystem, "bwrap", PATH))!, tool: "/bin/sleep", hostHome: t.hostHome, home: t.home, root: t.root, readOnly: [], personal: t.personal, ...ALL };
    const child: ChildHandle = spawner.spawn(buildAgentSandboxedSpec(profile, { file: "/bin/sleep", args: [marker], cwd: t.root, env: env(t.home) }));
    const running = () => {
      try {
        return execFileSync("pgrep", ["-f", `sleep ${marker}`], { encoding: "utf8" }).trim() !== "";
      } catch {
        return false;
      }
    };
    for (let tries = 0; tries < 50 && !running(); tries += 1) await new Promise((resolve) => setTimeout(resolve, 50));
    expect(running()).toBe(true);
    child.killGroup("SIGINT");
    const exit = await child.exit;
    expect(exit.code === null || exit.code !== 0).toBe(true);
    for (let tries = 0; tries < 50 && running(); tries += 1) await new Promise((resolve) => setTimeout(resolve, 50));
    expect(running()).toBe(false);
  });

  it("hides the host's chat, state and snapshots, keeps the agent files read-only and the turn folders the person's own", async () => {
    const t = scratch();
    const caztor = join(t.root, ".caztor");
    for (const dir of ["chat", "snapshots/objects", "agents", "opencode-xdg"]) mkdirSync(join(caztor, dir), { recursive: true });
    writeFileSync(join(caztor, "chat", "claude.jsonl"), "host chat line");
    writeFileSync(join(caztor, "state.json"), '{"sessions":{"claude":"host-session-id"}}');
    writeFileSync(join(caztor, "snapshots", "objects", "x"), "snapshot bytes");
    writeFileSync(join(caztor, "agents", "pi.md"), "pi system prompt");
    mkdirSync(join(t.root, ".claude"));
    writeFileSync(join(t.root, ".claude", "settings.json"), "{}");
    const before = await scanClaudeProjectConfig(nodeFileSystem, t.root);
    // The host trusted the configuration as it was.
    const trust = createTrustSeal({ fs: nodeFileSystem, configHome: t.config, uid: null, root: t.root });
    const sealed = await trust.seal("claude", before!.fingerprint);
    const profile: AgentSandboxProfile = { bwrap: (await resolveBinary(nodeFileSystem, "bwrap", PATH))!, tool: "/bin/sh", hostHome: t.hostHome, home: t.home, root: t.root, readOnly: [], personal: t.personal, ...ALL };
    const script = [
      `cat ${caztor}/chat/claude.jsonl`,
      `cat ${caztor}/state.json`,
      `cat ${caztor}/snapshots/objects/x`,
      `cat ${caztor}/agents/pi.md`,
      `echo forged > ${caztor}/state.json && echo wrote-state`,
      `echo planted > ${caztor}/agents/pi.md && echo wrote-agent`,
      `mkdir -p ${caztor}/opencode-xdg/opencode && echo '{"mcp":{"x":{"type":"local","command":["sh"]}}}' > ${caztor}/opencode-xdg/opencode/opencode.json && echo wrote-xdg`,
      `echo '{"hooks":{}}' > ${t.root}/.claude/settings.json && echo wrote-settings`,
      `echo '{"mcpServers":{}}' > ${t.root}/.mcp.json && echo wrote-mcp`,
    ].join("; ");
    const result = await runSpec(buildAgentSandboxedSpec(profile, { file: "/bin/sh", args: ["-c", script], cwd: t.root, env: env(t.home) }));
    expect(result.stdout).not.toContain("host chat line");
    expect(result.stdout).not.toContain("host-session-id");
    expect(result.stdout).not.toContain("snapshot bytes");
    expect(result.stdout).toContain("pi system prompt");
    expect(result.stdout).not.toContain("wrote-agent");
    expect(result.stdout).not.toContain("wrote-settings");
    expect(result.stdout).toContain("wrote-xdg");
    expect(result.stdout).toContain("wrote-mcp");
    // Nothing of the host's changed: the state, the agent file, the host's opencode folder and the trusted settings.
    expect(readFileSync(join(caztor, "state.json"), "utf8")).toBe('{"sessions":{"claude":"host-session-id"}}');
    expect(readFileSync(join(caztor, "agents", "pi.md"), "utf8")).toBe("pi system prompt");
    expect(readdirSync(join(caztor, "opencode-xdg"))).toEqual([]);
    expect(existsSync(join(t.personal, "opencode-xdg", "opencode", "opencode.json"))).toBe(true);
    expect(readFileSync(join(t.root, ".claude", "settings.json"), "utf8")).toBe("{}");
    // The file it could create is new to the host's gate: the fingerprint the host confirmed no longer holds.
    const after = await scanClaudeProjectConfig(nodeFileSystem, t.root);
    expect(after?.files).toEqual([".mcp.json", ".claude/settings.json"]);
    expect(after?.fingerprint).not.toBe(before?.fingerprint);
    expect(await trust.holds("claude", after!.fingerprint, sealed)).toBe(false);
  });

  /** The sandbox of the scratch host as a server would make it, running bash as the collaborator's CLI. */
  async function bashTurns(t: ReturnType<typeof scratch>) {
    const bash = (await resolveBinary(nodeFileSystem, "bash", PATH))!;
    const sandbox = createAgentSandbox({ fs: nodeFileSystem, spawner, clock: systemClock, root: t.root, env: { PATH, HOME: t.hostHome }, protectedFolders: [join(t.config, "caztor")] });
    return async (script: string) => {
      const wrapper = await sandbox.wrapper({ binary: bash, home: t.home });
      if (!wrapper.ok) return { refused: wrapper.reason, code: null, stdout: "", stderr: "" };
      return { refused: null, ...(await runSpec(wrapper.value({ file: bash, args: ["-c", script], cwd: t.root, env: env(t.home) }))) };
    };
  }

  function canaries(t: ReturnType<typeof scratch>) {
    writeFileSync(join(t.hostHome, "secret.txt"), "host secret file");
    mkdirSync(join(t.hostHome, ".claude"));
    writeFileSync(join(t.hostHome, ".claude", ".credentials.json"), "fake host credentials");
    writeFileSync(join(t.config, "caztor", "trust.key"), "fake trust key");
    const caztor = join(t.root, ".caztor");
    mkdirSync(join(caztor, "chat"), { recursive: true });
    writeFileSync(join(caztor, "chat", "claude.jsonl"), "host chat line");
    writeFileSync(join(caztor, "state.json"), '{"sessions":{"claude":"host-session-id"}}');
  }
  const SECRETS = ["host secret file", "fake host credentials", "fake trust key", "bob's", "host chat line", "host-session-id"];

  it("never mounts the target of a link a turn left at a configuration path for the next turn, and a dangling one runs", async () => {
    const t = scratch();
    canaries(t);
    const turn = await bashTurns(t);
    const first = await turn("ln -s ../.. .claude && ln -s .caztor .opencode && ln -s ../../.config/caztor .agents && ln -s /nonexistent .mcp.json && echo linked");
    expect(first.stdout).toContain("linked");
    // The host's own shared folders, if they ever were links, are left out the same way.
    symlinkSync(t.hostHome, join(t.root, ".caztor", "agents"));
    symlinkSync("/nonexistent", join(t.root, ".caztor", "guides"));
    const second = await turn(
      [
        "cat .claude/secret.txt .claude/.claude/.credentials.json",
        "cat .agents/trust.key .agents/users/bob-2/home/bob.txt",
        "cat .opencode/chat/claude.jsonl .opencode/state.json",
        "echo opencode: $(ls -A .opencode)",
        "cat .caztor/agents/secret.txt",
        "echo done",
      ].join("; "),
    );
    expect(second.refused).toBeNull();
    for (const secret of SECRETS) expect(second.stdout).not.toContain(secret);
    expect(second.stdout).toContain("done");
    // Inside the sandbox `.opencode` resolves to the sandbox's own `.caztor`: only the turn folders of the person.
    expect(second.stdout).toContain("opencode: opencode-data-api opencode-xdg pi-agent-api pi-sessions");
  });

  it("refuses the next turn when a turn turned its own turn folder into a link to the host's files", async () => {
    const t = scratch();
    canaries(t);
    const turn = await bashTurns(t);
    const first = await turn(`for d in "$HOME"/.caztor-turns/*/; do rm -rf "$d/opencode-xdg" && ln -s ${t.config} "$d/opencode-xdg"; done; echo linked`);
    expect(first.stdout).toContain("linked");
    const second = await turn(`cat ${t.root}/.caztor/opencode-xdg/caztor/trust.key; echo done`);
    expect(second.stdout).not.toContain("fake trust key");
    expect(second.refused).toMatch(/not a plain folder/);
  });

  for (const name of ["claude", "agy", "opencode", "pi", "codex"]) {
    it(`runs ${name} --version inside the sandbox, when it is installed`, async () => {
      const binary = await resolveBinary(nodeFileSystem, name, PATH);
      if (binary === null) return;
      const t = scratch();
      const sandbox = createAgentSandbox({
        fs: nodeFileSystem,
        spawner,
        clock: systemClock,
        root: t.root,
        // The real home is the one hidden, as on the host; the CLI's own HOME and XDG folders are the scratch home.
        env: { PATH, HOME: realpathSync(homedir()) },
        protectedFolders: [join(t.config, "caztor")],
      });
      const wrapper = await sandbox.wrapper({ binary, home: t.home });
      if (!wrapper.ok) throw new Error(wrapper.reason);
      const spec = wrapper.value({ file: binary, args: ["--version"], cwd: t.root, env: env(t.home) });
      const mounted = spec.args.flatMap((arg, index) => (arg === "--ro-bind" ? [spec.args[index + 1]!] : []));
      console.log(`${name}: ${binary} -> read-only ${JSON.stringify(mounted.filter((path) => !path.startsWith("/usr")))}`);
      const result = await runSpec(spec);
      expect(result.code, result.stderr).toBe(0);
      expect(result.stdout.trim()).not.toBe("");
    }, 60_000);
  }
});
