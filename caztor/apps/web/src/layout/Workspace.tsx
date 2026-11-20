import type { ReactNode } from "react";
import { Fragment } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { EmptyState } from "../components/EmptyState.tsx";
import { PaneShell } from "../components/PaneShell.tsx";
import { PANES, type PaneId, type PaneLayout } from "./panes.ts";
import type { LayoutStore } from "./storage.ts";
import "./Workspace.css";

interface WorkspaceProps {
  layoutStore: LayoutStore;
  /** What each pane shows. A pane without content shows its empty state. */
  content?: Partial<Record<PaneId, ReactNode>>;
  /** Controls shown in a pane's header, at its right end. */
  headers?: Partial<Record<PaneId, ReactNode>>;
}

const EMPTY_STATES: Record<Exclude<PaneId, "files">, ReactNode> = {
  editor: <EmptyState title="No file open">Select a LaTeX file in the project to start editing.</EmptyState>,
  preview: <EmptyState title="No preview yet">Compile the project to see the PDF here.</EmptyState>,
  chat: <EmptyState title="Chat is not connected yet">Ask the assistant for changes to your document once a provider is available.</EmptyState>,
};

function emptyStateFor(id: PaneId): ReactNode {
  return id === "files" ? <EmptyState title="No files">The project files will appear here.</EmptyState> : EMPTY_STATES[id];
}

/** Four resizable vertical panes: file tree, editor, preview and chat. Sizes persist through `layoutStore`. */
export function Workspace({ layoutStore, content = {}, headers = {} }: WorkspaceProps) {
  const saved = layoutStore.load();

  return (
    <Group
      className="workspace"
      orientation="horizontal"
      defaultLayout={saved}
      onLayoutChanged={(layout) => layoutStore.save(layout as PaneLayout)}
    >
      {PANES.map((pane, index) => (
        <Fragment key={pane.id}>
          {index > 0 ? <Separator className="workspace__divider" /> : null}
          <Panel id={pane.id} defaultSize={`${saved[pane.id]}%`} minSize={pane.minWidth}>
            <PaneShell title={pane.title} actions={headers[pane.id]}>{content[pane.id] ?? emptyStateFor(pane.id)}</PaneShell>
          </Panel>
        </Fragment>
      ))}
    </Group>
  );
}
