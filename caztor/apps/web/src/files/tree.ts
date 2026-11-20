import { RESERVED_ROOTS, type FileEntry } from "@caztor/core";

/** Largest file the editor opens; bigger files are listed but not opened. */
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;

export interface TreeNode {
  /** Project-relative path, which is also the node's identity. */
  path: string;
  name: string;
  kind: "file" | "dir";
  size: number;
  children: TreeNode[];
}

/** How the editor treats a file: `text` opens, `large` is text over 2 MB, `binary` is known not to be text. */
export type FileClass = "text" | "large" | "binary";

const BINARY_EXTENSIONS = new Set([
  "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "ico", "heic",
  "pdf", "eps", "ps", "zip", "gz", "tgz", "bz2", "xz", "7z", "rar", "tar",
  "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "mp3", "mp4", "mov", "wav", "ttf", "otf", "woff", "woff2",
]);

const reserved: readonly string[] = RESERVED_ROOTS;

function extensionOf(path: string): string {
  const name = path.slice(path.lastIndexOf("/") + 1);
  const dot = name.lastIndexOf(".");
  return dot <= 0 ? "" : name.slice(dot + 1).toLowerCase();
}

/** A first guess from the name and size; the server has the last word when the file is opened. */
export function classifyFile(entry: { path: string; size: number }): FileClass {
  if (BINARY_EXTENSIONS.has(extensionOf(entry.path))) return "binary";
  return entry.size > MAX_TEXT_BYTES ? "large" : "text";
}

const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

function compare(a: TreeNode, b: TreeNode): number {
  if (a.kind !== b.kind) return a.kind === "dir" ? -1 : 1;
  return collator.compare(a.name, b.name) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
}

/** Turns the server's flat list into nested, sorted folders. Folders missing from the list are created. */
export function buildTree(entries: readonly FileEntry[]): TreeNode[] {
  const roots: TreeNode[] = [];
  const folders = new Map<string, TreeNode>();

  function folder(path: string): TreeNode {
    const existing = folders.get(path);
    if (existing !== undefined) return existing;
    const slash = path.lastIndexOf("/");
    const node: TreeNode = { path, name: path.slice(slash + 1), kind: "dir", size: 0, children: [] };
    folders.set(path, node);
    (slash === -1 ? roots : folder(path.slice(0, slash)).children).push(node);
    return node;
  }

  for (const entry of entries) {
    const slash = entry.path.lastIndexOf("/");
    const top = entry.path.split("/")[0]?.toLowerCase() ?? "";
    if (reserved.includes(top)) continue;
    if (entry.kind === "dir") {
      folder(entry.path);
      continue;
    }
    const node: TreeNode = { path: entry.path, name: entry.path.slice(slash + 1), kind: "file", size: entry.size, children: [] };
    (slash === -1 ? roots : folder(entry.path.slice(0, slash)).children).push(node);
  }

  const sortAll = (nodes: TreeNode[]) => {
    nodes.sort(compare);
    for (const node of nodes) sortAll(node.children);
  };
  sortAll(roots);
  return roots;
}

/** Where `path` is after `from` was renamed to `to`: the path itself, or a file inside the renamed folder. */
export function movedPath(path: string, from: string, to: string): string {
  if (path === from) return to;
  return path.startsWith(`${from}/`) ? `${to}${path.slice(from.length)}` : path;
}

/** Whether `path` is `removed` itself or lies inside the folder `removed`. */
export function isWithin(path: string, removed: string): boolean {
  return path === removed || path.startsWith(`${removed}/`);
}
