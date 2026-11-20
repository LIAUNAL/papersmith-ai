import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import type { ApiClient, FileContent } from "../api/types.ts";
import { EmptyState } from "../components/EmptyState.tsx";
import { Icon } from "../components/Icon.tsx";
import { DeleteDialog } from "./DeleteDialog.tsx";
import { NameForm } from "./NameForm.tsx";
import { buildTree, classifyFile, MAX_TEXT_BYTES, type TreeNode } from "./tree.ts";
import { uploadProblem } from "./upload.ts";
import { useFileList } from "./useFileList.ts";
import "./FileTree.css";

interface FileTreeProps {
  api: ApiClient;
  /** The file open in the editor, if any. */
  selectedPath: string | null;
  /** Called with a file that was read successfully. */
  onOpen: (file: FileContent) => void;
  /** Called after a file or folder was renamed, so the app can follow an open file. */
  onRenamed?: (from: string, to: string) => void;
  /** Called after a file or folder was deleted. */
  onDeleted?: (path: string) => void;
}

type Notice = { tone: "info" | "error"; text: string };

/** Codes for which the server says the file can never be opened as text; the file is then shown as binary. */
const UNOPENABLE_CODES = new Set(["not_text", "too_large"]);

/** Above this many entries the tree starts folded, because a research workspace can hold thousands of files. */
const LARGE_PROJECT_ENTRIES = 300;

/** The project's files as a tree: select a text file to open it. */
export function FileTree({ api, selectedPath, onOpen, onRenamed, onDeleted }: FileTreeProps) {
  const { list, reload } = useFileList(api);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [learnedBinary, setLearnedBinary] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<Notice | null>(null);
  const [contextDir, setContextDir] = useState("");
  const [creating, setCreating] = useState<"file" | "dir" | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<TreeNode | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
  const foldedOnce = useRef(false);

  // Decided while rendering, so a very large tree is never drawn unfolded first.
  if (list.status === "ready" && !foldedOnce.current) {
    foldedOnce.current = true;
    if (list.entries.length > LARGE_PROJECT_ENTRIES) {
      setCollapsed(new Set(list.entries.filter((entry) => entry.kind === "dir" && entry.path !== "paper").map((entry) => entry.path as string)));
    }
  }

  if (list.status === "loading") {
    return (
      <p role="status" className="file-tree__message">
        Loading files
      </p>
    );
  }
  if (list.status === "failed") {
    return (
      <div role="alert" className="file-tree__message file-tree__message--error">
        <p>{list.message}</p>
        <button type="button" className="button" onClick={reload}>
          Try again
        </button>
      </div>
    );
  }

  const entries = list.entries;
  const tree = buildTree(entries);

  function toggle(path: string): void {
    setContextDir(path);
    setCollapsed((current) => {
      const next = new Set(current);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  }

  const folderPaths = new Set(entries.filter((entry) => entry.kind === "dir").map((entry) => entry.path as string));
  // A folder that was renamed or deleted since it was selected no longer exists: new entries then go to the root.
  const targetDir = folderPaths.has(contextDir) ? contextDir : "";
  const parentOf = (path: string) => path.slice(0, Math.max(path.lastIndexOf("/"), 0));
  const join = (dir: string, name: string) => (dir === "" ? name : `${dir}/${name}`);

  /** The message to show in a form when an API call fails, or null when it worked. */
  async function attempt(run: () => Promise<void>): Promise<string | null> {
    try {
      await run();
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : "The operation failed.";
    }
  }

  async function create(kind: "file" | "dir", name: string): Promise<string | null> {
    const failure = await attempt(() => api.createEntry(join(targetDir, name), kind));
    if (failure === null) {
      setCreating(null);
      // Show the new entry even when its folder was collapsed.
      setCollapsed((current) => new Set([...current].filter((path) => path !== targetDir)));
      reload();
    }
    return failure;
  }

  async function rename(node: TreeNode, name: string): Promise<string | null> {
    const to = join(parentOf(node.path), name);
    if (to === node.path) {
      setRenaming(null);
      return null;
    }
    const failure = await attempt(() => api.renameEntry(node.path, to));
    if (failure === null) {
      setRenaming(null);
      reload();
      onRenamed?.(node.path, to);
    }
    return failure;
  }

  async function remove(node: TreeNode): Promise<string | null> {
    const failure = await attempt(() => api.deleteEntry(node.path, { recursive: node.kind === "dir" }));
    if (failure === null) {
      setDeleting(null);
      reload();
      onDeleted?.(node.path);
    }
    return failure;
  }

  async function upload(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = [...(event.target.files ?? [])];
    event.target.value = "";
    const existing = new Set<string>(entries.map((entry) => entry.path));
    const problems: string[] = [];
    let uploaded = false;
    for (const file of files) {
      const destination = join(targetDir, file.name);
      const problem = uploadProblem(file, destination, existing);
      if (problem !== null) {
        problems.push(problem);
        continue;
      }
      const failure = await attempt(async () => api.uploadFile(destination, new Uint8Array(await file.arrayBuffer())));
      if (failure === null) uploaded = true;
      else problems.push(failure);
    }
    if (uploaded) reload();
    setNotice(problems.length === 0 ? null : { tone: "error", text: problems.join(" ") });
  }

  async function open(node: TreeNode): Promise<void> {
    setNotice(null);
    setContextDir(parentOf(node.path));
    const kind = learnedBinary.has(node.path) ? "binary" : classifyFile(node);
    if (kind === "binary") {
      setNotice({ tone: "info", text: `${node.name} is a binary file and cannot be opened in the editor.` });
      return;
    }
    if (kind === "large") {
      setNotice({ tone: "info", text: `${node.name} is larger than ${MAX_TEXT_BYTES / (1024 * 1024)} MB and cannot be opened in the editor.` });
      return;
    }
    try {
      onOpen(await api.readFile(node.path));
    } catch (error) {
      const message = error instanceof Error ? error.message : `${node.name} could not be opened.`;
      const code = (error as { code?: string }).code ?? "";
      if (UNOPENABLE_CODES.has(code)) setLearnedBinary((current) => new Set(current).add(node.path));
      setNotice({ tone: UNOPENABLE_CODES.has(code) ? "info" : "error", text: message });
    }
  }

  function rowActions(node: TreeNode): ReactNode {
    return (
      <span className="file-tree__actions">
        <button type="button" className="icon-button" aria-label={`Rename ${node.path}`} title="Rename" onClick={() => setRenaming(node.path)}>
          <Icon name="pencil" />
        </button>
        <button type="button" className="icon-button" aria-label={`Delete ${node.path}`} title="Delete" onClick={() => setDeleting(node)}>
          <Icon name="trash" />
        </button>
      </span>
    );
  }

  function renameForm(node: TreeNode): ReactNode {
    return (
      <NameForm
        label={`New name for ${node.path}`}
        initial={node.name}
        submitLabel="Rename"
        onSubmit={(name) => rename(node, name)}
        onCancel={() => setRenaming(null)}
      />
    );
  }

  function renderNode(node: TreeNode): ReactNode {
    if (node.kind === "dir") {
      const expanded = !collapsed.has(node.path);
      return (
        <li key={node.path}>
          {renaming === node.path ? (
            renameForm(node)
          ) : (
            <div className="file-tree__item">
              <button type="button" className="file-tree__row" aria-expanded={expanded} onClick={() => toggle(node.path)}>
                <Icon name="chevron" className={expanded ? "file-tree__chevron file-tree__chevron--open" : "file-tree__chevron"} />
                <Icon name="folder" />
                <span className="file-tree__name">{node.name}</span>
              </button>
              {rowActions(node)}
            </div>
          )}
          {expanded && node.children.length > 0 ? <ul className="file-tree__list">{node.children.map(renderNode)}</ul> : null}
        </li>
      );
    }
    const kind = learnedBinary.has(node.path) ? "binary" : classifyFile(node);
    return (
      <li key={node.path}>
        {renaming === node.path ? (
          renameForm(node)
        ) : (
          <div className="file-tree__item">
            <button
              type="button"
              className={kind === "text" ? "file-tree__row" : "file-tree__row file-tree__row--unopenable"}
              aria-current={node.path === selectedPath ? "true" : undefined}
              onClick={() => void open(node)}
            >
              <span className="file-tree__spacer" />
              <Icon name="file" />
              <span className="file-tree__name">{node.name}</span>
              {kind === "text" ? null : <span className="file-tree__badge">{kind === "binary" ? "Binary" : "Too large"}</span>}
            </button>
            {rowActions(node)}
          </div>
        )}
      </li>
    );
  }

  return (
    <div className="file-tree">
      <div className="file-tree__toolbar" role="toolbar" aria-label="File actions">
        <button type="button" className="icon-button" aria-label="New file" title="New file" onClick={() => setCreating("file")}>
          <Icon name="file-plus" />
        </button>
        <button type="button" className="icon-button" aria-label="New folder" title="New folder" onClick={() => setCreating("dir")}>
          <Icon name="folder-plus" />
        </button>
        <button type="button" className="icon-button" aria-label="Upload files" title="Upload files" onClick={() => uploadInput.current?.click()}>
          <Icon name="upload" />
        </button>
        <input ref={uploadInput} type="file" multiple className="visually-hidden" tabIndex={-1} aria-label="Choose files to upload" onChange={(event) => void upload(event)} />
      </div>
      {creating === null ? null : (
        <NameForm
          key={creating}
          label={creating === "file" ? "New file name" : "New folder name"}
          caption={`${creating === "file" ? "New file" : "New folder"} in ${targetDir === "" ? "the project root" : targetDir}`}
          submitLabel="Create"
          onSubmit={(name) => create(creating, name)}
          onCancel={() => setCreating(null)}
        />
      )}
      {tree.length === 0 ? (
        <EmptyState title="This project has no files yet">Create a file or upload one to get started.</EmptyState>
      ) : (
        <nav aria-label="Project files">
          <ul className="file-tree__list file-tree__list--root">{tree.map(renderNode)}</ul>
        </nav>
      )}
      {deleting === null ? null : (
        <DeleteDialog node={deleting} onConfirm={() => remove(deleting)} onCancel={() => setDeleting(null)} />
      )}
      {notice === null ? null : (
        <p role={notice.tone === "error" ? "alert" : "status"} className={`file-tree__notice file-tree__notice--${notice.tone}`}>
          {notice.text}
        </p>
      )}
    </div>
  );
}
