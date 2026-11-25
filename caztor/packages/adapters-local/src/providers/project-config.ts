import { hashBytes } from "@caztor/core";
import type { ProjectConfigFinding } from "@caztor/core";
import type { FileSystem } from "../infra.ts";

export { antigravityDefinitionProblem } from "../agent-definition.ts";

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_FOLDER_ENTRIES = 500;
const encoder = new TextEncoder();

/** JSON with comments and trailing commas, as opencode reads its configuration; null when it is not valid. */
export function parseJsonc(text: string): unknown {
  let out = "";
  let inString = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i]!;
    if (inString) {
      out += char;
      if (char === "\\") out += text[++i] ?? "";
      else if (char === '"') inString = false;
    } else if (char === '"') {
      inString = true;
      out += char;
    } else if (char === "/" && text[i + 1] === "/") {
      while (i < text.length && text[i] !== "\n") i++;
      out += "\n";
    } else if (char === "/" && text[i + 1] === "*") {
      const end = text.indexOf("*/", i + 2);
      i = end === -1 ? text.length : end + 1;
    } else {
      out += char;
    }
  }
  try {
    return JSON.parse(out.replace(/,(\s*[}\]])/g, "$1"));
  } catch {
    return null;
  }
}

async function read(fs: FileSystem, path: string): Promise<Uint8Array | null> {
  try {
    const stats = await fs.lstat(path);
    if (stats.isSymbolicLink()) {
      // What the link points to is what the CLI loads, so its content counts too, not only where it points.
      const target = await fs.stat(path).catch(() => null);
      const label = encoder.encode(`link:${await fs.realpath(path).catch(() => "?")}\0`);
      if (target === null || !target.isFile()) return label;
      const body = target.size > MAX_FILE_BYTES ? encoder.encode(`large:${target.size}:${target.mtimeMs}`) : await fs.readFile(path);
      const both = new Uint8Array(label.length + body.length);
      both.set(label);
      both.set(body, label.length);
      return both;
    }
    if (!stats.isFile()) return null;
    return stats.size > MAX_FILE_BYTES ? encoder.encode(`large:${stats.size}:${stats.mtimeMs}`) : await fs.readFile(path);
  } catch {
    return null;
  }
}

/** Whether `path` is a folder, also when reached through a link: the CLI follows links, so the trust gate does too. */
const isFolder = (fs: FileSystem, path: string) => fs.stat(path).then((stats) => stats.isDirectory(), () => false);

/**
 * Every file below `folder` (bounded), as [path, content]. Links to folders are followed, each real folder once, so a
 * change behind a link changes the fingerprint; the link itself is recorded with where it points.
 */
async function filesBelow(fs: FileSystem, folder: string): Promise<Array<[string, Uint8Array]>> {
  const found: Array<[string, Uint8Array]> = [];
  const seen = new Set<string>();
  const queue = [folder];
  while (queue.length > 0 && found.length < MAX_FOLDER_ENTRIES) {
    const dir = queue.shift()!;
    const real = await fs.realpath(dir).catch(() => dir);
    if (seen.has(real)) continue;
    seen.add(real);
    const entries = await fs.readdir(dir).catch(() => []);
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) queue.push(path);
      else if (entry.isSymbolicLink() && (await isFolder(fs, path))) {
        found.push([path, encoder.encode(`link:${await fs.realpath(path).catch(() => "?")}`)]);
        queue.push(path);
      } else found.push([path, (await read(fs, path)) ?? new Uint8Array()]);
    }
  }
  return found;
}

async function fingerprintOf(parts: Array<[string, Uint8Array]>): Promise<string> {
  const chunks: Uint8Array[] = [];
  for (const [label, content] of parts) chunks.push(encoder.encode(`${label}\0${content.length}\0`), content);
  const all = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    all.set(chunk, offset);
    offset += chunk.length;
  }
  return await hashBytes(all);
}

/** The files and folders of a project that Claude Code reads and that can start programs (MCP servers, hooks). */
const CLAUDE_FILES = [".mcp.json", ".claude/settings.json", ".claude/settings.local.json"];

export async function scanClaudeProjectConfig(fs: FileSystem, root: string): Promise<ProjectConfigFinding | null> {
  const files: string[] = [];
  const parts: Array<[string, Uint8Array]> = [];
  for (const name of CLAUDE_FILES) {
    if (!(await fs.lstat(`${root}/${name}`).then(() => true, () => false))) continue;
    files.push(name);
    parts.push([name, (await read(fs, `${root}/${name}`)) ?? new Uint8Array()]);
  }
  return files.length === 0 ? null : { files, fingerprint: await fingerprintOf(parts) };
}

/** Top-level keys of an opencode configuration that cannot run a program or send data elsewhere. */
const HARMLESS_KEYS = new Set(["$schema", "theme", "username", "share", "autoupdate", "keybinds", "tui", "snapshot", "instructions"]);
const OPENCODE_CONFIG_FILES = ["opencode.json", "opencode.jsonc", ".opencode/opencode.json", ".opencode/opencode.jsonc"];
/** Folders opencode loads code or command templates from. */
const OPENCODE_CODE_FOLDERS = ["plugins", "plugin", "tools", "tool", "commands", "command"];

/** Whether an opencode configuration file would do more than change how the interface looks. */
export function runsSomething(bytes: Uint8Array): boolean {
  const parsed = parseJsonc(new TextDecoder().decode(bytes));
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return true;
  return Object.keys(parsed).some((key) => !HARMLESS_KEYS.has(key));
}

/**
 * What opencode would load from the project and its parent folders up to the repository root, when it can start
 * programs: MCP servers, plugins, formatters, tools, commands, custom providers.
 */
export async function scanOpencodeProjectConfig(fs: FileSystem, root: string): Promise<ProjectConfigFinding | null> {
  const files: string[] = [];
  const parts: Array<[string, Uint8Array]> = [];
  const base = root.replace(/\/+$/, "");
  let dir = base;
  let prefix = "";
  for (let depth = 0; depth < 32; depth++) {
    for (const name of OPENCODE_CONFIG_FILES) {
      const bytes = await read(fs, `${dir}/${name}`);
      if (bytes === null || !runsSomething(bytes)) continue;
      files.push(`${prefix}${name}`);
      parts.push([`${prefix}${name}`, bytes]);
    }
    for (const name of OPENCODE_CODE_FOLDERS) {
      const folder = `${dir}/.opencode/${name}`;
      if (!(await isFolder(fs, folder))) continue;
      const inside = await filesBelow(fs, folder);
      if (inside.length === 0) continue;
      files.push(`${prefix}.opencode/${name}/`);
      for (const [path, bytes] of inside) parts.push([`${prefix}${path.slice(dir.length + 1)}`, bytes]);
    }
    if (await fs.lstat(`${dir}/.git`).then(() => true, () => false)) break;
    const parent = dir.slice(0, dir.lastIndexOf("/"));
    if (parent === "" || parent === dir) break;
    dir = parent;
    prefix = `../${prefix}`;
  }
  return files.length === 0 ? null : { files, fingerprint: await fingerprintOf(parts) };
}

/** The one file under `.agents/` that Caztor writes; the trust gate does not count it. */
const ANTIGRAVITY_OWN_FILE = ".agents/agents/caztor.md";

/**
 * Antigravity's project folder `.agents/`. There is no documented list of what in it can run a program, so every file
 * except Caztor's own definition is reported (fail closed). A link at `.agents` itself, or inside it, is reported too.
 */
export async function scanAntigravityProjectConfig(fs: FileSystem, root: string): Promise<ProjectConfigFinding | null> {
  const base = root.replace(/\/+$/, "");
  const folder = `${base}/.agents`;
  const stats = await fs.lstat(folder).catch(() => null);
  if (stats === null) return null;
  if (stats.isSymbolicLink() && (await isFolder(fs, folder))) {
    // A linked folder counts with everything Antigravity would read through it.
    const inside = (await filesBelow(fs, folder)).map(([path, bytes]): [string, Uint8Array] => [path.slice(base.length + 1), bytes]);
    return { files: [".agents"], fingerprint: await fingerprintOf([[".agents", await readLinkMarker(fs, folder)], ...inside]) };
  }
  if (stats.isSymbolicLink() || !stats.isDirectory()) return { files: [".agents"], fingerprint: await fingerprintOf([[".agents", await readLinkMarker(fs, folder)]]) };
  const files: string[] = [];
  const parts: Array<[string, Uint8Array]> = [];
  for (const [path, bytes] of await filesBelow(fs, folder)) {
    const name = path.slice(base.length + 1);
    if (name === ANTIGRAVITY_OWN_FILE) continue;
    files.push(name);
    parts.push([name, bytes]);
  }
  return files.length === 0 ? null : { files, fingerprint: await fingerprintOf(parts) };
}

async function readLinkMarker(fs: FileSystem, path: string): Promise<Uint8Array> {
  return (await read(fs, path)) ?? encoder.encode("not-a-folder");
}

/** The error text of a turn that is refused until the user trusts the project's CLI configuration. */
export function configRefusal(cli: string, files: readonly string[]): string {
  return `This project has its own ${cli} configuration (${files.join(", ")}), which can run programs on this computer. Choose "Trust this project's CLI configuration" in the chat to allow it, or remove those files.`;
}
