import type { ProjectEntry } from "@caztor/core";
import type { FileSystem } from "./infra.ts";

const PROJECTS_FILE = "caztor/projects.json";
const MAX_REMEMBERED = 100;
const MAX_TITLE_CHARS = 200;

export interface ProjectCatalogOptions {
  fs: FileSystem;
  /** Scanned for PaperSmith workspaces. PaperSmith has no list of its own; its docs recommend `~/papers`. */
  papersDir: string | null;
  /** Where the folders opened before are remembered. Null: only the scan. */
  configHome: string | null;
}

export interface ProjectCatalog {
  /** The workspaces of the papers folder and the folders opened before that still exist, by name. */
  list(): Promise<ProjectEntry[]>;
  /** What a folder is, or null when it is not a folder. */
  describe(path: string): Promise<ProjectEntry | null>;
  /** Adds a folder to the remembered ones. A failure only means it is not remembered. */
  remember(path: string): Promise<void>;
}

/** The folder a papers path or a user's own path means: the papers folder of `HOME` unless `CAZTOR_PAPERS_DIR` says otherwise. */
export function papersDirOf(env: Readonly<Record<string, string | undefined>>): string | null {
  const chosen = env["CAZTOR_PAPERS_DIR"];
  if (chosen !== undefined && chosen.startsWith("/")) return chosen.replace(/(.)\/+$/, "$1");
  const home = env["HOME"];
  return home !== undefined && home.startsWith("/") ? `${home.replace(/\/+$/, "")}/papers` : null;
}

function titleIn(yaml: string): string | undefined {
  const raw = /^title:[ \t]*(.*)$/m.exec(yaml)?.[1]?.trim();
  if (raw === undefined) return undefined;
  const title = raw.replace(/^(["'])(.*)\1$/, "$2").trim();
  return title === "" || title === "null" || title === "~" ? undefined : title.slice(0, MAX_TITLE_CHARS);
}

export function createProjectCatalog(options: ProjectCatalogOptions): ProjectCatalog {
  const { fs, papersDir, configHome } = options;
  const listFile = configHome === null ? null : `${configHome}/${PROJECTS_FILE}`;
  const isFile = (path: string) => fs.stat(path).then((stats) => !stats.isDirectory(), () => false);

  async function describe(path: string): Promise<ProjectEntry | null> {
    const folder = await fs.stat(path).then((stats) => stats.isDirectory(), () => false);
    if (!folder) return null;
    const name = path.slice(path.lastIndexOf("/") + 1);
    const yaml = await fs.readFile(`${path}/papersmith.yaml`).then((bytes) => new TextDecoder().decode(bytes), () => null);
    if (yaml === null && !(await isFile(`${path}/.papersmith/config.json`))) return { path, name, kind: "folder" };
    const title = yaml === null ? undefined : titleIn(yaml);
    const hasMain = (await isFile(`${path}/paper/main.tex`)) || (await isFile(`${path}/main.tex`));
    return { path, name, kind: "papersmith", ...(title === undefined ? {} : { title }), ...(hasMain ? {} : { missingMain: true }) };
  }

  async function remembered(): Promise<string[]> {
    if (listFile === null) return [];
    try {
      const parsed = JSON.parse(new TextDecoder().decode(await fs.readFile(listFile))) as { paths?: unknown };
      return Array.isArray(parsed.paths) ? parsed.paths.filter((path): path is string => typeof path === "string" && path.startsWith("/")) : [];
    } catch {
      return [];
    }
  }

  async function scanned(): Promise<string[]> {
    if (papersDir === null) return [];
    const children = await fs.readdir(papersDir).catch(() => []);
    return children.filter((child) => !child.name.startsWith(".")).map((child) => `${papersDir}/${child.name}`);
  }

  return {
    describe,
    async list() {
      const scan = await Promise.all((await scanned()).map(describe));
      const workspaces = scan.filter((entry): entry is ProjectEntry => entry?.kind === "papersmith");
      const known = new Set(workspaces.map((entry) => entry.path));
      const others = await Promise.all((await remembered()).filter((path) => !known.has(path)).map(describe));
      const all = [...workspaces, ...others.filter((entry): entry is ProjectEntry => entry !== null)];
      return all.sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path));
    },
    async remember(path) {
      if (listFile === null || configHome === null) return;
      const paths = [path, ...(await remembered()).filter((known) => known !== path)].slice(0, MAX_REMEMBERED);
      const temp = `${listFile}.${Date.now()}.tmp`;
      try {
        // The keys and the users share this folder, and their stores refuse it unless only this user can enter it.
        await fs.mkdir(`${configHome}/caztor`, { recursive: true, mode: 0o700 });
        await fs.writeFile(temp, new TextEncoder().encode(`${JSON.stringify({ version: 1, paths }, null, 2)}\n`), { exclusive: true, mode: 0o600 });
        await fs.rename(temp, listFile);
      } catch {
        // The list is a convenience; the project itself is open.
        await fs.rm(temp, { force: true }).catch(() => {});
      }
    },
  };
}
