export type ParsedArgs = { ok: true; projectDir: string } | { ok: false; usage: string };

const USAGE = "Usage: npm start -- <projectDir>";

/** `argv` is `process.argv`: runtime, script, then the arguments. Exactly one project folder is expected. */
export function parseProjectDir(argv: readonly string[]): ParsedArgs {
  const args = argv.slice(2);
  if (args[0] === "--") args.shift();
  const [projectDir, ...rest] = args;
  if (projectDir === undefined || projectDir === "" || projectDir.startsWith("-") || rest.length > 0) {
    return { ok: false, usage: USAGE };
  }
  return { ok: true, projectDir };
}

export interface Exposure {
  /** The address to bind. */
  host: string;
  /** The names collaborators reach Caztor by, allowed in Host and Origin besides loopback. */
  publicNames: string[];
  /** A TLS proxy fronts Caztor: cookies get `Secure`, links use https. */
  secure: boolean;
}

export type Command =
  | { ok: true; command: "serve"; projectDir: string; exposure: Exposure; embedOrigins?: string[]; embedKey?: string }
  | { ok: true; command: "invite"; name: string; exposure: Exposure; lifetime?: string }
  | { ok: true; command: "users" }
  | { ok: true; command: "revoke"; id: string }
  | { ok: true; command: "trust-build"; projectDir: string }
  | { ok: false; usage: string };

const COMMAND_USAGE = [
  "Usage: npm start -- <projectDir> [--host <address>] [--public-name <name[:port]>]... [--secure]",
  "       npm start -- invite <name> [--for 7d|24h|90m|<ISO date>] [--public-name <name[:port]>] [--secure]",
  "       npm start -- users",
  "       npm start -- revoke <id>",
  "       npm start -- trust-build <projectDir>   (confirm the project's .caztor/build.json on this computer)",
  "Option --embed-origin <origin>[,<origin>]...: serve inside the page of that origin (a PaperSmith dashboard) on this one",
  "       project; repeat it (or separate with commas) for the same dashboard under another name, such as localhost.",
  "Environment: CAZTOR_HOST, CAZTOR_PUBLIC_NAME (comma separated), CAZTOR_SECURE=1, CAZTOR_EMBED_ORIGIN (comma separated),",
  "       CAZTOR_EMBED_KEY (embedded only: the page is served only to a request whose ?k= is this key).",
].join("\n");

/**
 * The command line, with exposure settings from the options or else from the environment. `invite`, `users` and
 * `revoke` come first, so a project folder with one of those names is given as `./invite`.
 */
export function parseCommand(argv: readonly string[], env: Readonly<Record<string, string | undefined>>): Command {
  const args = argv.slice(2);
  if (args[0] === "--") args.shift();
  const usage = { ok: false, usage: COMMAND_USAGE } as const;
  const positional: string[] = [];
  let host: string | undefined;
  const names: string[] = [];
  let secure = false;
  let lifetime: string | undefined;
  const embedOrigins: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]!;
    const [flag, inline] = arg.startsWith("--") && arg.includes("=") ? [arg.slice(0, arg.indexOf("=")), arg.slice(arg.indexOf("=") + 1)] : [arg, undefined];
    if (flag === "--secure" && inline === undefined) secure = true;
    else if (flag === "--host" || flag === "--public-name" || flag === "--for" || flag === "--embed-origin") {
      const value = inline ?? args[(index += 1)];
      if (value === undefined || value === "" || value.startsWith("-")) return usage;
      if (flag === "--host") host = value;
      else if (flag === "--for") lifetime = value;
      else if (flag === "--embed-origin") embedOrigins.push(...splitList(value));
      else names.push(value);
    } else if (arg.startsWith("-") || arg === "") return usage;
    else positional.push(arg);
  }
  const fromEnv = splitList(env["CAZTOR_PUBLIC_NAME"] ?? "");
  const exposure: Exposure = {
    host: host ?? (env["CAZTOR_HOST"] || "127.0.0.1"),
    publicNames: names.length > 0 ? names : fromEnv,
    secure: secure || env["CAZTOR_SECURE"] === "1",
  };
  const [first, ...rest] = positional;
  const embedded = embedOrigins.length > 0 ? [...new Set(embedOrigins)] : [...new Set(splitList(env["CAZTOR_EMBED_ORIGIN"] ?? ""))];
  const flagged = embedOrigins.length > 0;
  // `--embed-origin` belongs to serving only.
  if (flagged && (first === "invite" || first === "users" || first === "revoke")) return usage;
  if (first === "invite") return rest.length > 0 ? { ok: true, command: "invite", name: rest.join(" "), exposure, ...(lifetime === undefined ? {} : { lifetime }) } : usage;
  // `--for` belongs to an invite only.
  if (lifetime !== undefined) return usage;
  if (first === "users") return rest.length === 0 ? { ok: true, command: "users" } : usage;
  if (first === "trust-build") return rest.length === 1 && !flagged ? { ok: true, command: "trust-build", projectDir: rest[0]! } : usage;
  if (first === "revoke") return rest.length === 1 ? { ok: true, command: "revoke", id: rest[0]! } : usage;
  if (first === undefined || rest.length > 0) return usage;
  if (embedded.length === 0) return { ok: true, command: "serve", projectDir: first, exposure };
  // The frame key only means something embedded; it is never printed.
  const embedKey = env["CAZTOR_EMBED_KEY"] || undefined;
  return { ok: true, command: "serve", projectDir: first, exposure, embedOrigins: embedded, ...(embedKey === undefined ? {} : { embedKey }) };
}

/** A comma separated list, trimmed, without empty entries. */
function splitList(value: string): string[] {
  return value.split(",").map((entry) => entry.trim()).filter((entry) => entry !== "");
}

const UNIT_MINUTES = { m: 1, h: 60, d: 24 * 60 } as const;

/**
 * How many minutes `--for` asks for: `90m`, `24h`, `7d`, or the date and time the key ends (ISO 8601), counted from
 * `now` and rounded up to a whole minute. Null when the value is neither. Bounds are the users store's to check.
 */
export function parseLifetime(value: string, now: number): number | null {
  const span = /^([1-9][0-9]{0,6})([mhd])$/.exec(value);
  if (span !== null) return Number(span[1]) * UNIT_MINUTES[span[2] as keyof typeof UNIT_MINUTES];
  if (!/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$/.test(value)) return null;
  const at = Date.parse(value);
  return Number.isNaN(at) ? null : Math.ceil((at - now) / 60_000);
}
