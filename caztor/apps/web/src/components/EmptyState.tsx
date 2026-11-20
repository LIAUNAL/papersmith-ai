import type { ReactNode } from "react";
import "./EmptyState.css";

interface EmptyStateProps {
  title: string;
  children: ReactNode;
}

/** The centered message of a pane that has nothing to show yet. */
export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__text">{children}</p>
    </div>
  );
}
