import { confirmRecipe, createTrustKey, createUserStore, credentialConfigHome, INVITE_DEFAULT_MINUTES, RECIPE_FILE, type FileSystem, type InviteView } from "@caztor/adapters-local";
import { parseLifetime, type Command } from "./cli.ts";
import { checkExposure } from "./server.ts";

type UserCommand = Extract<Command, { command: "invite" | "users" | "revoke" | "trust-build" }>;

const MINUTE_MS = 60_000;
const plural = (count: number, unit: string) => `${count} ${unit}${count === 1 ? "" : "s"}`;

/** A span of minutes in the largest whole unit: `90 minutes`, `24 hours`, `7 days`. */
function spanOf(minutes: number): string {
  if (minutes % (24 * 60) === 0) return plural(minutes / (24 * 60), "day");
  if (minutes % 60 === 0) return plural(minutes / 60, "hour");
  return plural(minutes, "minute");
}

/** How long is left, rounded to the nearest whole unit: `in 6 days`, `in 5 hours`, `in 12 minutes`. */
function leftOf(ms: number): string {
  const minutes = Math.max(1, Math.round(ms / MINUTE_MS));
  if (minutes < 60) return `in ${plural(minutes, "minute")}`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `in ${plural(hours, "hour")}`;
  return `in ${plural(Math.round(minutes / (24 * 60)), "day")}`;
}

function keyLine(invite: InviteView, now: number): string {
  const until = new Date(invite.expiresAt).toISOString();
  const state =
    invite.status === "old"
      ? "old invite, create a new one"
      : invite.status === "expired"
        ? `expired ${until}`
        : invite.status === "locked"
          ? "locked after 10 wrong keys"
          : `expires ${until} (${leftOf(invite.expiresAt - now)})`;
  return `  key ${invite.id}  ${state}${invite.status === "old" ? "" : `  signed in: ${invite.sessions}`}`;
}

/**
 * `invite`, `users` and `revoke` change the users store directly, under its lock, rather than asking the running
 * server: no new channel and no launch token on disk are needed, and the server reads the store on every check,
 * so a revoke signs the collaborator out at once.
 */
export async function runUserCommand(
  command: UserCommand,
  deps: { fs: FileSystem; env: Readonly<Record<string, string | undefined>>; now?: () => number },
): Promise<{ code: number; lines: string[] }> {
  const configHome = credentialConfigHome(deps.env);
  if (configHome === null) return { code: 1, lines: ["Caztor cannot tell where your configuration folder is (set HOME or XDG_CONFIG_HOME)."] };
  if (command.command === "trust-build") {
    let root: string;
    try {
      root = await deps.fs.realpath(command.projectDir);
    } catch {
      return { code: 1, lines: [`The project folder does not exist: ${command.projectDir}`] };
    }
    const confirmed = await confirmRecipe({ fs: deps.fs, root, trustKey: createTrustKey({ fs: deps.fs, configHome, uid: process.getuid?.() ?? null }) });
    if (!confirmed.ok) return { code: 1, lines: [confirmed.message] };
    const { recipe } = confirmed;
    return {
      code: 0,
      lines: [
        `Confirmed ${RECIPE_FILE} in ${root} on this computer.`,
        `Compiling ${recipe.when.join(", ")} now runs \`${recipe.before.join(" ")}\` in that folder, then compiles ${recipe.root}.`,
        "Any change to the file needs a new confirmation.",
      ],
    };
  }
  const now = deps.now ?? Date.now;
  const store = createUserStore({ fs: deps.fs, configHome, uid: process.getuid?.() ?? null, now });

  if (command.command === "invite") {
    let publicNames: string[];
    try {
      publicNames = checkExposure(command.exposure.host, command.exposure.publicNames).publicNames;
    } catch (error) {
      return { code: 1, lines: [error instanceof Error ? error.message : String(error)] };
    }
    if (publicNames.length === 0) return { code: 1, lines: ["Give the name collaborators reach Caztor by, the same as the server's: --public-name <name[:port]> (and --secure behind a TLS proxy)."] };
    const minutes = command.lifetime === undefined ? INVITE_DEFAULT_MINUTES : parseLifetime(command.lifetime, now());
    if (minutes === null) return { code: 1, lines: [`--for takes a span such as 90m, 24h or 7d, or the date and time the key ends, such as 2026-12-01T18:00; "${command.lifetime}" is neither.`] };
    const made = await store.createInvite(command.name, minutes);
    if (!made.ok) return { code: 1, lines: [made.error.message] };
    const { user, id, key, expiresAt } = made.value;
    const link = `${command.exposure.secure ? "https" : "http"}://${publicNames[0]}/invite/${id}`;
    return {
      code: 0,
      lines: [
        `Invite for ${user.name}, until ${new Date(expiresAt).toISOString()} (${spanOf(minutes)}):`,
        `  Link: ${link}`,
        `  Access key: ${key}`,
        `The key is shown only now. Send ${user.name} the link and the key, apart if you can: the link opens a page that asks for the key, which signs in any number of browsers until it expires.`,
      ],
    };
  }

  if (command.command === "users") {
    const listed = await store.list();
    if (!listed.ok) return { code: 1, lines: [listed.error.message] };
    const collaborators = listed.value.filter((user) => user.role === "collaborator");
    if (collaborators.length === 0) return { code: 0, lines: ["No collaborators yet."] };
    const at = now();
    return { code: 0, lines: collaborators.flatMap((user) => [`${user.id}  ${user.name}  signed in: ${user.sessions}`, ...user.invites.map((invite) => keyLine(invite, at))]) };
  }

  // A person's id revokes the person; an access key's id (from `users`) revokes that key alone.
  const revoked = await store.revoke(command.id);
  if (revoked.ok) return { code: 0, lines: [`Revoked ${command.id}. Their browsers are signed out.`] };
  if (revoked.error.code !== "not_found") return { code: 1, lines: [revoked.error.message] };
  const key = await store.revokeInvite(command.id);
  if (key.ok) return { code: 0, lines: [`Revoked key ${command.id}. The browsers signed in with it are signed out.`] };
  return { code: 1, lines: [key.error.code === "not_found" ? "There is no collaborator or access key with that id." : key.error.message] };
}
