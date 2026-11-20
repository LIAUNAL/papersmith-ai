import type { ProviderId } from "@caztor/core";
import type { FileSystem } from "../infra.ts";

/**
 * Which providers the host is already signed in to on this computer, from the sign-in files their own CLIs keep. In
 * account mode Caztor runs those CLIs with the host's home, so the same sign-in serves every project, a PaperSmith
 * workspace included. Only whether a non-empty regular file is there is checked, except Pi's `auth.json`, which Pi
 * keeps as `{}` until a provider is signed in: of it only the provider names are read, never their keys or tokens. A
 * sign-in that has expired shows up at the next turn, which reports it as before.
 */
export async function signedInProviders(fs: FileSystem, env: Readonly<Record<string, string | undefined>>): Promise<ProviderId[]> {
  const home = env["HOME"] ?? "";
  const files: Array<[ProviderId, string]> = [
    ["claude", `${env["CLAUDE_CONFIG_DIR"] || `${home}/.claude`}/.credentials.json`],
    ["pi", `${env["PI_CODING_AGENT_DIR"] || `${home}/.pi/agent`}/auth.json`],
    ["opencode", `${env["XDG_DATA_HOME"] || `${home}/.local/share`}/opencode/auth.json`],
    ["antigravity", `${home}/.gemini/antigravity-cli/antigravity-oauth-token`],
  ];
  const found: ProviderId[] = [];
  for (const [provider, file] of files) {
    if (provider === "claude" && (env["CLAUDE_CODE_OAUTH_TOKEN"] ?? "") !== "") {
      found.push(provider);
      continue;
    }
    if (home === "" && !file.startsWith("/")) continue;
    const stats = await fs.lstat(file).catch(() => null);
    if (stats === null || !stats.isFile() || stats.isSymbolicLink() || stats.size === 0) continue;
    if (provider === "pi" && !(await namesAProvider(fs, file))) continue;
    found.push(provider);
  }
  return found;
}

/** Whether Pi's auth.json holds at least one provider. Its values are never looked at. */
async function namesAProvider(fs: FileSystem, file: string): Promise<boolean> {
  try {
    const parsed: unknown = JSON.parse(new TextDecoder().decode(await fs.readFile(file)));
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) && Object.keys(parsed).length > 0;
  } catch {
    return false;
  }
}
