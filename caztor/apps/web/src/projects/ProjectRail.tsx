import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ProjectEntry } from "../api/types.ts";
import type { StorageLike } from "../layout/storage.ts";
import "./ProjectRail.css";

export const RAIL_KEY = "caztor.rail.v1";

interface ProjectRailProps {
  list: () => Promise<ProjectEntry[]>;
  /** Moves to a folder. Answers null, or the readable reason it could not. */
  onOpen: (path: string) => Promise<string | null>;
  /** Makes a new project and moves to it. Answers null, or the readable reason it could not. */
  onCreate: (name: string) => Promise<string | null>;
  storage: StorageLike | null;
}

function savedCollapsed(storage: StorageLike | null): boolean {
  try {
    return storage?.getItem(RAIL_KEY) === "collapsed";
  } catch {
    return false;
  }
}

/** The projects at the left of the window: click, or move with the arrows and press Enter, to go to one. */
export function ProjectRail({ list, onOpen, onCreate, storage }: ProjectRailProps) {
  const [collapsed, setCollapsed] = useState(() => savedCollapsed(storage));
  const [projects, setProjects] = useState<ProjectEntry[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [folder, setFolder] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const rows = useRef<HTMLUListElement>(null);
  const newButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let current = true;
    list().then(
      (listed) => current && setProjects(listed),
      (error: unknown) => current && setProblem(error instanceof Error ? error.message : "The projects could not be read."),
    );
    return () => {
      current = false;
    };
  }, [list]);

  function fold(next: boolean) {
    setCollapsed(next);
    try {
      storage?.setItem(RAIL_KEY, next ? "collapsed" : "open");
    } catch {
      // Remembering this is a convenience; blocked or full storage must never break the app.
    }
  }

  async function attempt(step: () => Promise<string | null>) {
    setBusy(true);
    setProblem(null);
    const refused = await step();
    setBusy(false);
    setProblem(refused);
  }
  const open = (path: string) => attempt(() => onOpen(path));

  function closeNewProject() {
    setCreating(false);
    setNewName("");
    setProblem(null);
  }

  function moveWithKeys(event: KeyboardEvent<HTMLUListElement>) {
    const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const buttons = [...(rows.current?.querySelectorAll("button") ?? [])];
    const from = buttons.indexOf(document.activeElement as HTMLButtonElement);
    buttons[(from + step + buttons.length) % buttons.length]?.focus();
  }

  if (collapsed) {
    return (
      <nav className="rail rail--collapsed" aria-label="Projects">
        <button type="button" className="rail__fold" aria-expanded={false} aria-label="Show projects" title="Show projects" onClick={() => fold(false)}>
          »
        </button>
      </nav>
    );
  }

  return (
    <nav className="rail" aria-label="Projects">
      <div className="rail__header">
        <span className="rail__heading">Projects</span>
        <button ref={newButton} type="button" className="rail__fold rail__new" aria-label="New project" title="New project" onClick={() => setCreating(true)}>
          +
        </button>
        <button type="button" className="rail__fold" aria-expanded={true} aria-label="Hide projects" title="Hide projects" onClick={() => fold(true)}>
          «
        </button>
      </div>
      {creating ? (
        <form
          className="rail__add rail__create"
          onSubmit={(event) => {
            event.preventDefault();
            if (newName.trim() !== "") void attempt(() => onCreate(newName.trim()));
          }}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            closeNewProject();
            setTimeout(() => newButton.current?.focus());
          }}
        >
          <input autoFocus aria-label="Project name" placeholder="Project name" value={newName} onChange={(event) => setNewName(event.target.value)} />
          <button type="submit" className="button" disabled={busy || newName.trim() === ""}>
            Create
          </button>
          <button type="button" className="button" onClick={closeNewProject}>
            Cancel
          </button>
        </form>
      ) : null}
      {projects !== null && projects.length === 0 ? <p className="rail__empty">No PaperSmith workspaces found in your papers folder.</p> : null}
      <ul ref={rows} className="rail__list" onKeyDown={moveWithKeys}>
        {(projects ?? []).map((project) => (
          <li key={project.path}>
            <button
              type="button"
              className="rail__project"
              {...(project.active ? { "aria-current": "true" as const } : {})}
              title={project.title === undefined ? project.path : `${project.title}\n${project.path}`}
              disabled={busy}
              onClick={() => {
                if (!project.active) void open(project.path);
              }}
            >
              <span className="rail__name">{project.name}</span>
              {project.kind === "papersmith" ? <span className="rail__badge">PaperSmith</span> : null}
              {project.missingMain === true ? <span className="rail__note">No paper/main.tex yet</span> : null}
            </button>
          </li>
        ))}
      </ul>
      {problem === null ? null : (
        <p role="alert" className="rail__problem">
          {problem}
        </p>
      )}
      <form
        className="rail__add"
        onSubmit={(event) => {
          event.preventDefault();
          if (folder.trim() !== "") void open(folder.trim());
        }}
      >
        <input aria-label="Folder path" placeholder="~/papers/my-paper" value={folder} onChange={(event) => setFolder(event.target.value)} />
        <button type="submit" className="button" disabled={busy || folder.trim() === ""}>
          Open
        </button>
      </form>
    </nav>
  );
}
