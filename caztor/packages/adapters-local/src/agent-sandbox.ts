import { createHash } from "node:crypto";
import type { AgentEvent, TurnRequest } from "@caztor/core";
import type { Clock, CommandWrapper, FileSystem, ProcessSpawner, SpawnSpec } from "./infra.ts";
import { failed } from "./providers/drive.ts";
import { resolveBinary } from "./providers/resolve-binary.ts";
import { isSystemPath, parseLddPaths, run, sandboxStartFailure, systemMountArgs, USERNS_HINT } from "./sandbox.ts";

/**
 * What a collaborator's turn sees. The system tree, the network files and the CLI's install folders are read-only;
 * the project and the collaborator's private home are writable; the host's home is an empty tmpfs; nothing else exists.
 */
export interface AgentSandboxProfile {
  /** Absolute path of `bwrap`. */
  bwrap: string;
  /** Real path of the CLI; the child runs this file. */
  tool: string;
  /** Real path of the host's home folder, hidden under an empty tmpfs. */
  hostHome: string;
  /** Real path of the collaborator's private folder: writable, and the child's HOME. */
  home: string;
  /** Real path of the project folder: writable. */
  root: string;
  /** The CLI's (and its interpreter's) install folders and libraries outside the system tree. */
  readOnly: readonly string[];
  /**
   * The person's own folder for this project's turn folders, inside their private home: mounted over the project's
   * `.caztor/<name>` for each of `PERSONAL_TURN_FOLDERS`, so their CLI never writes the host's.
   */
  personal: string;
  /**
   * The names of `SHARED_TURN_FOLDERS` this turn gets read-only, and of `AGENT_CONFIG_PATHS` it gets read-only: only
   * those that were, when the spec was built, a plain entry of the project reached through no link (see `plainInProject`).
   */
  sharedFolders: readonly string[];
  agentConfig: readonly string[];
}

/** What a turn reads from the project's `.caztor/`: the provisioned agent files, the writing guides and the compile output. */
export const SHARED_TURN_FOLDERS = ["agents", "guides", "build"] as const;
/** The per-turn folders runners point their CLI at below `.caztor/` (opencode's configuration and data, Pi's sessions and agent folder). */
export const PERSONAL_TURN_FOLDERS = ["opencode-xdg", "opencode-data-api", "pi-sessions", "pi-agent-api"] as const;
/**
 * Project files a host turn loads and trusts only after the host confirmed them (the project CLI configuration gates).
 * A collaborator's turn sees the existing ones read-only; one it creates is new to the gate, which asks the host again.
 */
export const AGENT_CONFIG_PATHS = [".claude", ".opencode", ".agents", ".mcp.json", "opencode.json", "opencode.jsonc"];

/** Quotes one word for `sh`. */
const shellWord = (word: string) => `'${word.replace(/'/g, "'\\''")}'`;

/**
 * The arguments of util-linux `script` that run `tool args` in a pseudo-terminal, for a CLI that only talks to one (a
 * TUI, or a code read from /dev/tty). The screen is wide, so a long link stays on one line. `script` runs the command
 * with `$SHELL`, which the caller sets to `/bin/sh`.
 */
export function terminalArgs(tool: string, args: readonly string[]): string[] {
  return ["-q", "-e", "-c", `stty cols 300 rows 50 2>/dev/null; exec ${[tool, ...args].map(shellWord).join(" ")}`, "/dev/null"];
}

/** Account files without secrets (the password hashes are in `/etc/shadow`, never mounted): CLIs that look up their user find it. */
const ACCOUNT_FILES = ["/etc/passwd", "/etc/group"];
/** Variables that would lead the child to the host's session bus or runtime folder. */
const SESSION_NAMES = ["DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"];
const LDD_LIMIT_MS = 5_000;
const PROBE_LIMIT_MS = 30_000;
/** Package layouts whose files are spread under a prefix (Homebrew's cellar, npm's global folder): the whole prefix is mounted. */
const PREFIX_MARKERS = ["/Cellar/", "/lib/node_modules/"];

/** The spec that runs `spec` inside bubblewrap as a collaborator's turn. Pure: it builds an argument array and never a shell string. */
export function buildAgentSandboxedSpec(profile: AgentSandboxProfile, spec: SpawnSpec, options: { terminal?: string } = {}): SpawnSpec {
  const args = ["--unshare-all", "--share-net", "--die-with-parent", "--new-session", ...systemMountArgs()];
  for (const file of ACCOUNT_FILES) args.push("--ro-bind-try", file, file);
  // The tmpfs goes first: everything below is mounted on top of it, so only those folders of the host's home show.
  args.push("--tmpfs", profile.hostHome);
  for (const path of profile.readOnly) args.push("--ro-bind", path, path);
  args.push("--bind", profile.home, profile.home, "--bind", profile.root, profile.root);
  // The project's `.caztor/` holds the host's chat, the state with the trust and sessions, the snapshots and the host's
  // CLI folders: an empty tmpfs hides all of it, then only what a turn reads comes back read-only and its own folders writable.
  const caztor = `${profile.root}/.caztor`;
  args.push("--tmpfs", caztor);
  // bwrap resolves a bind source on the host's side and follows links in it, so only entries checked to be plain are
  // bound. One that is a link is left as it is: inside the sandbox it resolves within the sandbox's own view.
  for (const name of profile.sharedFolders) args.push("--ro-bind-try", `${caztor}/${name}`, `${caztor}/${name}`);
  for (const name of PERSONAL_TURN_FOLDERS) args.push("--bind", `${profile.personal}/${name}`, `${caztor}/${name}`);
  for (const name of profile.agentConfig) args.push("--ro-bind-try", `${profile.root}/${name}`, `${profile.root}/${name}`);
  args.push("--chdir", spec.cwd, "--");
  if (options.terminal === undefined) args.push(profile.tool, ...spec.args);
  else args.push(options.terminal, ...terminalArgs(profile.tool, spec.args));
  const env: Record<string, string> = {};
  for (const [name, value] of Object.entries(spec.env)) if (!SESSION_NAMES.includes(name)) env[name] = value;
  env["HOME"] = profile.home;
  env["TMPDIR"] = "/tmp";
  if (options.terminal !== undefined) env["SHELL"] = "/bin/sh";
  return { ...spec, file: profile.bwrap, args, env };
}

export type AgentWrapperResult = { ok: true; value: CommandWrapper } | { ok: false; reason: string };

export interface AgentSandbox {
  /**
   * The wrapper for a collaborator's turn of the CLI at `binary` (as `resolveBinary` found it), with `home` as their
   * private folder, after a `--version` run of the CLI inside the same sandbox succeeded; or why it cannot run sandboxed.
   * With `terminal`, the CLI runs in a pseudo-terminal made by the system's `script`.
   */
  wrapper(input: { binary: string; home: string; terminal?: boolean }): Promise<AgentWrapperResult>;
}

export interface AgentSandboxOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder. */
  root: string;
  /** The server's environment: `PATH` finds bwrap and interpreters, `HOME` is the host's home to hide. */
  env: Readonly<Record<string, string | undefined>>;
  /**
   * Folders no mount may hold or lie in (Caztor's own config folder: every person's private folder and the users
   * store). The private home of the turn must be inside one, and is the only part of it that is mounted.
   */
  protectedFolders?: readonly string[];
}

const within = (path: string, folder: string) => path === folder || path.startsWith(`${folder === "/" ? "" : folder}/`);

/**
 * The folder to mount for a file of an installed program: its package prefix, or the file itself. A prefix inside the
 * host's home (npm's `~/.local`, a cellar there) holds the host's own logins, so only the package's folder is used:
 * `node_modules/<name>` (or `@scope/name`), or `Cellar/<formula>/<version>`.
 */
function installRoot(real: string, hostHome: string): string {
  for (const marker of PREFIX_MARKERS) {
    const at = real.indexOf(marker);
    if (at <= 0) continue;
    const prefix = real.slice(0, at);
    if (!within(prefix, hostHome)) return prefix;
    const rest = real.slice(at + marker.length).split("/");
    const depth = marker === "/Cellar/" ? 2 : rest[0]?.startsWith("@") === true ? 2 : 1;
    // Only a folder below the package's own: a file directly in the prefix's package folder is mounted alone.
    return rest.length > depth ? `${real.slice(0, at + marker.length)}${rest.slice(0, depth).join("/")}` : real;
  }
  return real;
}

/** The host's home itself, or a folder at most two levels below it (`~/.local`, `~/.local/share`, `~/.config`): too broad to mount. */
function broadInHome(path: string, hostHome: string): boolean {
  if (!within(path, hostHome)) return false;
  const parts = path.slice(hostHome.length).split("/").filter((part) => part !== "");
  return parts.length <= 2;
}

class Refusal extends Error {}

const TERMINAL_MISSING = "The system's script program (util-linux) was not found, so this sign-in cannot get a terminal.";

/** The system's own `script` (util-linux), which makes a pseudo-terminal; a copy outside the system tree is never used. */
export async function terminalProgram(fs: FileSystem): Promise<string | null> {
  for (const candidate of ["/usr/bin/script", "/bin/script"]) {
    if (await fs.stat(candidate).then((stats) => stats.isFile(), () => false)) return candidate;
  }
  return null;
}

/** Feature-detects bubblewrap and builds, per CLI and private home, the wrapper of a collaborator's turns. */
export function createAgentSandbox(options: AgentSandboxOptions): AgentSandbox {
  const { fs, spawner, clock } = options;
  const path = options.env["PATH"];
  const ready = new Map<string, Promise<AgentSandboxProfile>>();

  async function real(file: string, what: string): Promise<string> {
    try {
      return await fs.realpath(file);
    } catch {
      throw new Refusal(`${what} could not be found.`);
    }
  }

  async function head(file: string): Promise<string> {
    try {
      return new TextDecoder().decode(await fs.readRange(file, 0, 256));
    } catch {
      return "";
    }
  }

  /** The libraries of an executable outside the system tree, from `ldd`. A script has none of its own. */
  async function libraries(file: string, env: Record<string, string>, cwd: string): Promise<string[]> {
    if (!(await head(file)).startsWith("\u007fELF")) return [];
    const listed = await run(spawner, clock, { file: "ldd", args: [file], cwd, env }, LDD_LIMIT_MS);
    return listed.code === 0 ? parseLddPaths(listed.stdout) : [];
  }

  /** The interpreter a script's first line names (`#!/usr/bin/env node` or `#!/path/node`), as a real path, or null. */
  async function interpreter(file: string): Promise<string | null> {
    const first = (await head(file)).split("\n")[0] ?? "";
    if (!first.startsWith("#!")) return null;
    const words = first.slice(2).trim().split(/\s+/);
    const command = words[0]?.endsWith("/env") === true ? words.find((word, index) => index > 0 && !word.startsWith("-")) : words[0];
    if (command === undefined || command === "") return null;
    const found = command.startsWith("/") ? command : await resolveBinary(fs, command, path);
    if (found === null) throw new Refusal(`The program that runs this CLI (${command}) was not found on the PATH.`);
    return real(found, `The program that runs this CLI (${command})`);
  }

  async function prepare(binary: string, home: string): Promise<AgentSandboxProfile> {
    const bwrap = await resolveBinary(fs, "bwrap", path);
    if (bwrap === null) throw new Refusal("Bubblewrap (bwrap) was not found, so a collaborator's turn cannot run sandboxed. Install it on the host.");
    const hostHomeVar = options.env["HOME"];
    if (hostHomeVar === undefined || !hostHomeVar.startsWith("/")) throw new Refusal("The host's home folder is not known, so it could not be hidden from the turn.");
    const hostHome = await real(hostHomeVar, "The host's home folder");
    const root = await real(options.root, "The project folder");
    if (!home.startsWith("/")) throw new Refusal("The private folder is not an absolute path.");
    const ownHome = await real(home, "Your private folder");
    if (ownHome !== home) throw new Refusal("Your private folder is reached through a link, so it is not used.");
    if (!(await fs.stat(home)).isDirectory()) throw new Refusal("Your private folder is not a folder.");
    const guarded: string[] = [];
    for (const folder of options.protectedFolders ?? []) guarded.push(await fs.realpath(folder).catch(() => folder.replace(/(.)\/+$/, "$1")));
    if (guarded.length > 0 && !guarded.some((folder) => within(home, folder) && home !== folder)) {
      throw new Refusal("Your private folder is not one Caztor made, so it is not used.");
    }
    if (guarded.some((folder) => within(root, folder) || within(folder, root))) {
      throw new Refusal("The project folder overlaps Caztor's configuration folder, so a collaborator's turn cannot run in it.");
    }
    if (within(hostHome, root)) throw new Refusal("The project folder contains the host's home folder, so the turn could not hide it.");
    if (within(hostHome, home) || within(home, root) || within(root, home)) {
      throw new Refusal("Your private folder overlaps the host's home folder or the project, so it is not used.");
    }

    await plainCaztor(root);
    const personal = await personalFolder(home, root);

    const readOnly: string[] = [];
    const admit = async (entries: readonly string[]) => {
      for (const entry of entries) {
        if (isSystemPath(entry) || readOnly.some((kept) => within(entry, kept))) continue;
        if (broadInHome(entry, hostHome) && (await fs.stat(entry).then((stats) => stats.isDirectory(), () => true))) {
          throw new Refusal(`The CLI is installed in ${entry}, a broad folder of the host's home, so it cannot be mounted read-only.`);
        }
        // A mount of the host's home, the private home or the project would show or hide what the sandbox is for.
        if ([hostHome, home, root, ...guarded].some((folder) => within(folder, entry)) || [home, root, ...guarded].some((folder) => within(entry, folder))) {
          throw new Refusal(`The CLI is installed in ${entry}, which holds the host's home, your private folder or the project, so it cannot be mounted read-only.`);
        }
        for (let index = readOnly.length - 1; index >= 0; index -= 1) if (within(readOnly[index]!, entry)) readOnly.splice(index, 1);
        readOnly.push(entry);
      }
    };
    const tool = await real(binary, "The CLI");
    const env = { PATH: path ?? "", HOME: home };
    await admit([installRoot(tool, hostHome)]);
    await admit(await libraries(tool, env, root));
    const runner = await interpreter(tool);
    if (runner !== null) {
      await admit([installRoot(runner, hostHome)]);
      await admit(await libraries(runner, env, root));
    }
    const profile = await current({ bwrap, tool, hostHome, home, root, readOnly, personal, sharedFolders: [], agentConfig: [] });

    const trial = await run(spawner, clock, buildAgentSandboxedSpec(profile, { file: tool, args: ["--version"], cwd: root, env }), PROBE_LIMIT_MS);
    if (trial.error !== undefined) throw new Refusal("Bubblewrap (bwrap) could not be started.");
    if (trial.code !== 0) {
      const failure = sandboxStartFailure(trial.stderr) ?? trial.stderr.trim().split("\n").at(-1) ?? "";
      if (USERNS_HINT.test(failure)) throw new Refusal(`Unprivileged user namespaces are not available on this system, so the sandbox cannot start (bwrap: ${failure}).`);
      throw new Refusal(`The CLI did not answer --version inside the sandbox${failure === "" ? "" : `: ${failure.slice(0, 200)}`}.`);
    }
    return profile;
  }

  /** `<home>/.caztor-turns/<sha256(project) first 32 hex>`, with every per-turn folder made and closed to others. */
  async function personalFolder(home: string, root: string): Promise<string> {
    const base = `${home}/.caztor-turns`;
    const folder = `${base}/${createHash("sha256").update(root).digest("hex").slice(0, 32)}`;
    for (const path of [base, folder, ...PERSONAL_TURN_FOLDERS.map((name) => `${folder}/${name}`)]) {
      try {
        await fs.mkdir(path, { mode: 0o700 });
      } catch (error) {
        if ((error as { code?: string }).code !== "EEXIST") throw new Refusal("Your own turn folders could not be created.");
      }
      const stats = await fs.lstat(path).catch(() => null);
      if (stats === null || stats.isSymbolicLink() || !stats.isDirectory()) throw new Refusal("A turn folder in your private folder is not a plain folder, so it is not used.");
      if ((stats.mode & 0o077) !== 0) await fs.chmod(path, 0o700);
    }
    return folder;
  }

  /** Refuses a project whose `.caztor` is there but no plain folder: the tmpfs that hides it would land elsewhere. */
  async function plainCaztor(root: string): Promise<void> {
    const stats = await fs.lstat(`${root}/.caztor`).catch(() => null);
    if (stats !== null && (stats.isSymbolicLink() || !stats.isDirectory())) {
      throw new Refusal("The project's .caztor is not a plain folder, so a collaborator's turn could not have it hidden.");
    }
  }

  /**
   * Whether `relative` (below the project) may be a bind source: every component from the project down is there and is
   * no link, and its real path is itself, inside the project. A missing or linked one is not bound.
   */
  async function plainInProject(root: string, relative: string): Promise<boolean> {
    let path = root;
    for (const part of relative.split("/")) {
      path = `${path}/${part}`;
      const stats = await fs.lstat(path).catch(() => null);
      if (stats === null || stats.isSymbolicLink()) return false;
    }
    const resolved = await fs.realpath(path).catch(() => null);
    return resolved === path && within(resolved, root);
  }

  /**
   * The profile with what of the project and the private home a spec built now may bind. Checked again on every call,
   * never remembered: a collaborator's turn writes the project and their home, so it can leave a link for the next one.
   */
  async function current(profile: AgentSandboxProfile): Promise<AgentSandboxProfile> {
    await plainCaztor(profile.root);
    const sharedFolders: string[] = [];
    for (const name of SHARED_TURN_FOLDERS) if (await plainInProject(profile.root, `.caztor/${name}`)) sharedFolders.push(name);
    const agentConfig: string[] = [];
    for (const name of AGENT_CONFIG_PATHS) if (await plainInProject(profile.root, name)) agentConfig.push(name);
    const personal = await personalFolder(profile.home, profile.root);
    return { ...profile, personal, sharedFolders, agentConfig };
  }


  return {
    async wrapper({ binary, home, terminal }) {
      const key = `${binary}\u0000${home}`;
      let pending = ready.get(key);
      if (pending === undefined) {
        pending = prepare(binary, home);
        ready.set(key, pending);
        pending.catch(() => ready.delete(key));
      }
      try {
        const profile = await current(await pending);
        const program = terminal === true ? await terminalProgram(fs) : undefined;
        if (program === null) return { ok: false, reason: TERMINAL_MISSING };
        return { ok: true, value: (spec) => buildAgentSandboxedSpec(profile, spec, program === undefined ? {} : { terminal: program }) };
      } catch (error) {
        return { ok: false, reason: error instanceof Refusal ? error.message : "The sandbox could not be prepared." };
      }
    },
  };
}

/**
 * The spec a turn runs: the host's turn unchanged, a collaborator's (one with `sandbox` or `env` set) inside bubblewrap.
 * A collaborator's turn that cannot be sandboxed is refused, never run without it.
 */
export async function placeTurn(sandbox: AgentSandbox | undefined, req: TurnRequest, spec: SpawnSpec): Promise<{ spec: SpawnSpec } | { stop: AgentEvent[] }> {
  if (req.sandbox === undefined && req.env === undefined) return { spec };
  const refuse = (reason: string) => ({ stop: failed("isolation_failed", `Your turn was not started because it could not run in the sandbox: ${reason}`) });
  if (req.sandbox === undefined) return refuse("the turn names no private folder.");
  if (sandbox === undefined) return refuse("this server has no sandbox for collaborators' turns.");
  const wrapper = await sandbox.wrapper({ binary: spec.file, home: req.sandbox.home });
  if (!wrapper.ok) return refuse(wrapper.reason);
  return { spec: wrapper.value(spec) };
}
