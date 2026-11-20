import type { ChildHandle, Clock, CommandWrapper, FileSystem, ProcessSpawner, SpawnSpec } from "./infra.ts";
import { buildCompileEnv } from "./tectonic/command.ts";

/** What the sandbox mounts. Everything else on the machine, the rest of the home folder included, is absent. */
export interface SandboxProfile {
  /** Absolute path of `bwrap`. */
  bwrap: string;
  /** Absolute path of the engine; the child runs this file. */
  tool: string;
  /** The project folder: read-only, except its build folder. */
  root: string;
  /** The engine's support-file cache folders: read-write, so a first-run download works. */
  cacheDirs: readonly string[];
  /** The shared libraries (and loader) the engine needs that the system tree does not provide. */
  libraries: readonly string[];
}

export interface SandboxProbe {
  ok: boolean;
  version?: string;
  reason?: string;
}

export interface Sandbox {
  /** Runs the engine's `--version` inside the sandbox. A successful answer is remembered. */
  probe(): Promise<SandboxProbe>;
  /** The wrapper for compile specs; rejects with the probe's reason when the sandbox cannot be used. */
  wrapper(): Promise<CommandWrapper>;
}

export interface SandboxOptions {
  spawner: ProcessSpawner;
  clock: Clock;
  fs: FileSystem;
  /** Absolute real path of the project folder. */
  root: string;
  /** The server's environment: `PATH` finds the tools, `HOME` and the cache variables locate the cache. */
  env: Readonly<Record<string, string | undefined>>;
  /** The engine's command name. */
  binary?: string;
}

/** The sandbox-relative location of the folder the engine may write. */
const BUILD_FOLDER = ".caztor/build";
const LDD_LIMIT_MS = 5_000;
const PROBE_LIMIT_MS = 20_000;
/** Mounted when present on the host: the system tree and the few files a network client needs. */
const SYSTEM_TREES = ["/lib", "/lib64", "/bin", "/sbin"];
const SYSTEM_FILES = [
  "/etc/resolv.conf",
  "/etc/hosts",
  "/etc/nsswitch.conf",
  "/etc/ld.so.cache",
  "/etc/localtime",
  "/etc/ssl/certs",
  "/etc/ca-certificates",
  "/etc/pki",
  "/etc/fonts",
];
const SYSTEM_PREFIXES = ["/usr/", "/lib/", "/lib64/", "/bin/", "/sbin/"];

/** Whether `path` lies in the system tree that every sandbox already mounts read-only. */
export function isSystemPath(path: string): boolean {
  return SYSTEM_PREFIXES.some((prefix) => path.startsWith(prefix));
}

/** What every sandbox mounts: the system tree read-only, `/proc`, `/dev`, a private `/tmp` and the network files. */
export function systemMountArgs(): string[] {
  const args = ["--ro-bind", "/usr", "/usr"];
  for (const tree of SYSTEM_TREES) args.push("--ro-bind-try", tree, tree);
  args.push("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp");
  for (const file of SYSTEM_FILES) args.push("--ro-bind-try", file, file);
  return args;
}

/** The paths in `ldd` output: resolved libraries and the loader. Names it could not resolve are skipped. */
export function parseLddPaths(output: string): string[] {
  const found: string[] = [];
  const add = (path: string | undefined) => {
    if (path !== undefined && path.startsWith("/") && !found.includes(path)) found.push(path);
  };
  for (const raw of output.split("\n")) {
    const line = raw.replace(/\s*\(0x[0-9a-f]+\)\s*$/, "").trim();
    if (line === "") continue;
    const [left, right] = line.split(" => ");
    add(left);
    add(right);
  }
  return found;
}

/** The message of a failure that bwrap itself reported (its lines start with `bwrap:`), or null. */
export function sandboxStartFailure(stderr: string): string | null {
  for (const line of stderr.split("\n")) {
    const match = /^bwrap: (.+)$/.exec(line.trim());
    if (match !== null) return match[1] ?? null;
  }
  return null;
}

/** The spec that runs `spec` inside bubblewrap. Pure: it builds an argument array and never a shell string. */
export function buildSandboxedSpec(profile: SandboxProfile, spec: SpawnSpec): SpawnSpec {
  const own = (path: string) => !isSystemPath(path);
  const build = `${profile.root}/${BUILD_FOLDER}`;
  const args = ["--unshare-all", "--share-net", "--die-with-parent", ...systemMountArgs()];
  for (const library of profile.libraries.filter(own)) args.push("--ro-bind-try", library, library);
  if (own(profile.tool)) args.push("--ro-bind", profile.tool, profile.tool);
  args.push("--ro-bind", profile.root, profile.root, "--bind", build, build);
  for (const cache of profile.cacheDirs) args.push("--bind", cache, cache);
  args.push("--chdir", spec.cwd, "--", profile.tool, ...spec.args);
  return { ...spec, file: profile.bwrap, args, env: { ...spec.env, TMPDIR: "/tmp" } };
}

export interface Run {
  code: number | null;
  stdout: string;
  stderr: string;
  error?: unknown;
}

/** Runs `spec` to read its output, ending it after `limitMs`. Never throws. */
export async function run(spawner: ProcessSpawner, clock: Clock, spec: SpawnSpec, limitMs: number): Promise<Run> {
  const child: ChildHandle = spawner.spawn(spec);
  const read = async (stream: AsyncIterable<Uint8Array>) => {
    const decoder = new TextDecoder();
    let text = "";
    try {
      for await (const chunk of stream) text += decoder.decode(chunk, { stream: true });
    } catch {
      // Treated as no output.
    }
    return text;
  };
  const cancel = clock.setTimeout(() => child.killGroup("SIGKILL"), limitMs);
  try {
    const [stdout, stderr] = await Promise.all([read(child.stdout), read(child.stderr)]);
    const exit = await child.exit;
    return { code: exit.code, stdout, stderr };
  } catch (error) {
    return { code: null, stdout: "", stderr: "", error };
  } finally {
    cancel();
  }
}

export const USERNS_HINT = /namespace|uid map|Operation not permitted|Permission denied/i;

function unavailable(reason: string): Error {
  return new Error(reason);
}

/** Feature-detects bubblewrap and builds the wrapper that runs the engine inside it. */
export function createSandbox(options: SandboxOptions): Sandbox {
  const { spawner, clock, fs, root } = options;
  const binary = options.binary ?? "tectonic";
  const env = buildCompileEnv(options.env);
  let ready: Promise<{ profile: SandboxProfile; version: string }> | undefined;

  async function find(name: string): Promise<string | null> {
    const dirs = (options.env["PATH"] ?? "").split(":").filter((dir) => dir !== "");
    for (const dir of dirs) {
      try {
        if ((await fs.stat(`${dir}/${name}`)).isFile()) return `${dir}/${name}`;
      } catch {
        // Not in this folder.
      }
    }
    return null;
  }

  async function cacheDirs(): Promise<string[]> {
    const configured = options.env["TECTONIC_CACHE_DIR"];
    if (configured !== undefined && configured !== "") return [configured];
    const base = options.env["XDG_CACHE_HOME"] ?? (options.env["HOME"] === undefined ? null : `${options.env["HOME"]}/.cache`);
    if (base === null) throw unavailable("The Tectonic cache folder could not be located because HOME is not set.");
    const dirs = [`${base}/tectonic`];
    // Older Tectonic releases kept their cache in "Tectonic"; it is mounted too when it exists.
    if (await fs.stat(`${base}/Tectonic`).then((stats) => stats.isDirectory(), () => false)) dirs.push(`${base}/Tectonic`);
    return dirs;
  }

  async function prepare(): Promise<{ profile: SandboxProfile; version: string }> {
    const bwrap = await find("bwrap");
    if (bwrap === null) throw unavailable("Bubblewrap (bwrap) was not found. Install it to use the sandbox.");
    const tool = await find(binary);
    if (tool === null) throw unavailable("Tectonic was not found on the PATH, so the sandbox has nothing to run.");
    const caches = await cacheDirs();
    for (const dir of caches) await fs.mkdir(dir, { recursive: true });
    await fs.mkdir(`${root}/${BUILD_FOLDER}`, { recursive: true });

    const listed = await run(spawner, clock, { file: "ldd", args: [tool], cwd: root, env }, LDD_LIMIT_MS);
    const libraries = listed.code === 0 ? parseLddPaths(listed.stdout) : [];
    const profile: SandboxProfile = { bwrap, tool, root, cacheDirs: caches, libraries };

    const trial = await run(spawner, clock, buildSandboxedSpec(profile, { file: binary, args: ["--version"], cwd: root, env }), PROBE_LIMIT_MS);
    if (trial.error !== undefined) throw unavailable("Bubblewrap (bwrap) could not be started.");
    const failure = sandboxStartFailure(trial.stderr) ?? trial.stderr.trim().split("\n").at(-1) ?? "";
    if (trial.code !== 0) {
      if (USERNS_HINT.test(failure)) {
        throw unavailable(`Unprivileged user namespaces are not available on this system, so the sandbox cannot start (bwrap: ${failure}).`);
      }
      throw unavailable(`The sandbox test run failed${failure === "" ? "" : `: ${failure}`}.`);
    }
    const version = /Tectonic\s+\S+/.exec(trial.stdout)?.[0];
    if (version === undefined) throw unavailable("The sandbox test run did not answer with a Tectonic version.");
    return { profile, version: `bubblewrap, ${version}` };
  }

  async function resolve() {
    ready ??= prepare().catch((error: unknown) => {
      ready = undefined;
      throw error;
    });
    return ready;
  }

  return {
    async probe() {
      try {
        return { ok: true, version: (await resolve()).version };
      } catch (error) {
        return { ok: false, reason: error instanceof Error ? error.message : "The sandbox is not available." };
      }
    },
    async wrapper() {
      const { profile } = await resolve();
      return (spec) => buildSandboxedSpec(profile, spec);
    },
  };
}
