import type { FileSystem, FsDirent, FsStats } from "../../src/infra.ts";

type Node =
  | { kind: "file"; bytes: Uint8Array; mtimeMs: number; ctimeMs: number; mode: number }
  | { kind: "dir"; mtimeMs: number; ctimeMs: number; mode: number }
  | { kind: "symlink"; target: string; mtimeMs: number; ctimeMs: number; mode: number }
  | { kind: "special"; mtimeMs: number; ctimeMs: number; mode: number };

/** The owner of every object in the fake. */
export const MEMORY_FS_UID = 1000;
const FILE_MODE = 0o644;
const DIR_MODE = 0o755;
const LINK_MODE = 0o777;

const MAX_SYMLINK_DEPTH = 40;

function fsError(code: string, path: string): Error {
  return Object.assign(new Error(`${code}: ${path}`), { code });
}

function parent(path: string): string {
  const index = path.lastIndexOf("/");
  return index <= 0 ? "/" : path.slice(0, index);
}

function join(base: string, name: string): string {
  return base === "/" ? `/${name}` : `${base}/${name}`;
}

const nodeIds = new WeakMap<Node, string>();
let nextNodeId = 1;

/** Every node object is one file system object; a node created again is a different one. */
function idOf(node: Node): string {
  let id = nodeIds.get(node);
  if (id === undefined) {
    id = `memory:${nextNodeId++}`;
    nodeIds.set(node, id);
  }
  return id;
}

function describe(node: Node, size: number): FsStats & FsDirent {
  return {
    name: "",
    size,
    id: idOf(node),
    mtimeMs: node.mtimeMs,
    ctimeMs: node.ctimeMs,
    mode: node.mode,
    uid: MEMORY_FS_UID,
    isFile: () => node.kind === "file",
    isDirectory: () => node.kind === "dir",
    isSymbolicLink: () => node.kind === "symlink",
  };
}

/**
 * In-memory `FileSystem` with POSIX absolute paths, symbolic links and Node-style error codes.
 * Modification times are a deterministic counter that grows on every mutation.
 */
export class MemoryFileSystem implements FileSystem {
  private nodes = new Map<string, Node>([["/", { kind: "dir", mtimeMs: 0, ctimeMs: 0, mode: DIR_MODE }]]);
  private clock = 1000;

  constructor(files: Record<string, string> = {}) {
    for (const [path, text] of Object.entries(files)) {
      this.mkdirSync(parent(path));
      this.nodes.set(path, { kind: "file", bytes: new TextEncoder().encode(text), ...this.stamps(), mode: FILE_MODE });
    }
  }

  /** Test helper: creates a symbolic link at `path` pointing at the absolute `target`. */
  symlink(target: string, path: string): void {
    this.mkdirSync(parent(path));
    this.nodes.set(path, { kind: "symlink", target, ...this.stamps(), mode: LINK_MODE });
  }

  /** Test helper: creates an entry that is not a regular file, directory or link (a socket or pipe on disk). */
  special(path: string): void {
    this.mkdirSync(parent(path));
    this.nodes.set(path, { kind: "special", ...this.stamps(), mode: FILE_MODE });
  }

  private tick(): number {
    return ++this.clock;
  }

  /** A new object: modified and changed now. */
  private stamps(): { mtimeMs: number; ctimeMs: number } {
    const now = this.tick();
    return { mtimeMs: now, ctimeMs: now };
  }

  /** Test helper, like `touch -d`: sets the modification time and moves the change time forward, as a real disk does. */
  setMtime(path: string, mtimeMs: number): void {
    const { node } = this.require(path);
    node.mtimeMs = mtimeMs;
    node.ctimeMs = this.tick();
  }

  /** Creates `path` and every missing ancestor, following links and resolving `.` and `..` like `mkdir -p`. */
  private mkdirSync(path: string, depth = 0): string {
    if (depth > MAX_SYMLINK_DEPTH) throw fsError("ELOOP", path);
    let current = "/";
    for (const part of path.split("/").filter((name) => name !== "" && name !== ".")) {
      if (part === "..") {
        current = parent(current);
        continue;
      }
      const next = join(current, part);
      const node = this.nodes.get(next);
      if (node === undefined) {
        this.nodes.set(next, { kind: "dir", ...this.stamps(), mode: DIR_MODE });
        current = next;
      } else if (node.kind === "symlink") {
        current = this.mkdirSync(node.target, depth + 1);
      } else if (node.kind === "file" || node.kind === "special") {
        throw fsError("EEXIST", path);
      } else {
        current = next;
      }
    }
    return current;
  }

  /** Canonical path of `path` with every link resolved; the final link only when `followFinal`. */
  private canonical(path: string, followFinal: boolean, depth = 0): string {
    if (depth > MAX_SYMLINK_DEPTH) throw fsError("ELOOP", path);
    const parts = path.split("/").filter((part) => part !== "" && part !== ".");
    let current = "/";
    for (const [index, part] of parts.entries()) {
      const isLast = index === parts.length - 1;
      if (part === "..") {
        // The kernel applies `..` to the already resolved directory, so links before it are followed.
        current = parent(current);
        continue;
      }
      const next = join(current, part);
      const node = this.nodes.get(next);
      if (node === undefined) {
        if (!isLast) throw fsError("ENOENT", path);
        return next;
      }
      if (node.kind === "symlink" && (!isLast || followFinal)) {
        current = this.canonical(node.target, true, depth + 1);
      } else if ((node.kind === "file" || node.kind === "special") && !isLast) {
        throw fsError("ENOTDIR", path);
      } else {
        current = next;
      }
    }
    return current;
  }

  private require(path: string, followFinal = true): { path: string; node: Node } {
    const canonical = this.canonical(path, followFinal);
    const node = this.nodes.get(canonical);
    if (node === undefined) throw fsError("ENOENT", path);
    return { path: canonical, node };
  }

  private requireParentDir(path: string): void {
    const dir = this.nodes.get(this.canonical(parent(path), true));
    if (dir === undefined) throw fsError("ENOENT", path);
    if (dir.kind !== "dir") throw fsError("ENOTDIR", path);
  }

  private children(dirPath: string): string[] {
    const prefix = dirPath === "/" ? "/" : `${dirPath}/`;
    return [...this.nodes.keys()].filter((key) => key !== dirPath && key.startsWith(prefix) && !key.slice(prefix.length).includes("/"));
  }

  async readRange(path: string, start: number, length: number): Promise<Uint8Array> {
    return (await this.readFile(path)).slice(start, start + length);
  }

  async readFile(path: string): Promise<Uint8Array> {
    const { node } = this.require(path);
    if (node.kind === "dir") throw fsError("EISDIR", path);
    if (node.kind !== "file") throw fsError("ENXIO", path);
    return node.bytes.slice();
  }

  async writeFile(path: string, data: Uint8Array, opts?: { exclusive?: boolean; mode?: number }): Promise<void> {
    // `O_EXCL` never follows a final link: a dangling link already counts as existing.
    const target = this.canonical(path, !opts?.exclusive);
    this.requireParentDir(target);
    const existing = this.nodes.get(target);
    if (existing !== undefined && opts?.exclusive) throw fsError("EEXIST", path);
    if (existing?.kind === "dir") throw fsError("EISDIR", path);
    // Writing into an existing file keeps its permission bits, like open(2) with O_TRUNC.
    const mode = existing?.kind === "file" ? existing.mode : opts?.mode !== undefined ? opts.mode & 0o7777 : FILE_MODE;
    this.nodes.set(target, { kind: "file", bytes: data.slice(), ...this.stamps(), mode });
  }

  async mkdir(path: string, opts?: { recursive?: boolean; mode?: number }): Promise<void> {
    const mode = opts?.mode !== undefined ? opts.mode & 0o7777 : DIR_MODE;
    if (opts?.recursive) {
      const before = new Set(this.nodes.keys());
      this.mkdirSync(path);
      // Like mkdir(2) with a mode: the folders this call created get it.
      for (const [key, node] of this.nodes) if (!before.has(key)) node.mode = mode;
      return;
    }
    const target = this.canonical(path, true);
    const existing = this.nodes.get(target);
    if (existing !== undefined) throw fsError("EEXIST", path);
    this.requireParentDir(target);
    this.nodes.set(target, { kind: "dir", ...this.stamps(), mode });
  }

  async readdir(path: string): Promise<FsDirent[]> {
    const { path: dir, node } = this.require(path);
    if (node.kind !== "dir") throw fsError("ENOTDIR", path);
    return this.children(dir).map((child) => ({ ...describe(this.nodes.get(child)!, 0), name: child.slice(child.lastIndexOf("/") + 1) }));
  }

  async stat(path: string): Promise<FsStats> {
    const { node } = this.require(path);
    return describe(node, node.kind === "file" ? node.bytes.length : 0);
  }

  async lstat(path: string): Promise<FsStats> {
    const { node } = this.require(path, false);
    return describe(node, node.kind === "file" ? node.bytes.length : 0);
  }

  async realpath(path: string): Promise<string> {
    return this.require(path).path;
  }

  async rename(from: string, to: string): Promise<void> {
    const source = this.require(from, false).path;
    const target = this.canonical(to, false);
    this.requireParentDir(target);
    const existing = this.nodes.get(target);
    const moving = this.nodes.get(source);
    if (existing?.kind === "dir" && moving?.kind !== "dir") throw fsError("EISDIR", to);
    if (existing !== undefined && existing.kind !== "dir" && moving?.kind === "dir") throw fsError("ENOTDIR", to);
    if (existing?.kind === "dir" && this.children(target).length > 0) throw fsError("ENOTEMPTY", to);
    const moved = [...this.nodes.entries()].filter(([key]) => key === source || key.startsWith(`${source}/`));
    for (const [key] of moved) this.nodes.delete(key);
    this.nodes.delete(target);
    for (const [key, node] of moved) this.nodes.set(target + key.slice(source.length), node);
  }

  async rm(path: string, opts?: { recursive?: boolean; force?: boolean }): Promise<void> {
    let resolved: { path: string; node: Node };
    try {
      resolved = this.require(path, false);
    } catch (error) {
      if (opts?.force && (error as { code?: string }).code === "ENOENT") return;
      throw error;
    }
    if (resolved.node.kind === "dir" && !opts?.recursive) throw fsError("ERR_FS_EISDIR", path);
    for (const key of [...this.nodes.keys()]) {
      if (key === resolved.path || key.startsWith(`${resolved.path}/`)) this.nodes.delete(key);
    }
  }

  async chmod(path: string, mode: number): Promise<void> {
    const { node } = this.require(path);
    node.mode = mode & 0o7777;
    node.ctimeMs = this.tick();
  }

  private tempCounter = 0;

  async mkdtemp(prefix: string): Promise<string> {
    const path = `${prefix}${(this.tempCounter += 1).toString(36).padStart(6, "0")}`;
    await this.mkdir(path, { recursive: true });
    await this.chmod(path, 0o700);
    return path;
  }

  async copyFile(from: string, to: string): Promise<void> {
    const bytes = await this.readFile(from);
    await this.writeFile(to, bytes);
  }
}
