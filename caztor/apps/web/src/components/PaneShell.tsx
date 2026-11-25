import type { ReactNode } from "react";
import "./PaneShell.css";

interface PaneShellProps {
  /** The pane's visible title; also its accessible name. */
  title: string;
  /** Controls shown at the right end of the header. */
  actions?: ReactNode;
  children: ReactNode;
}

/** The frame every pane shares: one header style, one body. */
export function PaneShell({ title, actions, children }: PaneShellProps) {
  return (
    <section className="pane" aria-label={title} tabIndex={-1} data-focus-home>
      <header className="pane__header">
        <h2 className="pane__title">{title}</h2>
        {actions === undefined ? null : <div className="pane__actions">{actions}</div>}
      </header>
      <div className="pane__body">{children}</div>
    </section>
  );
}
