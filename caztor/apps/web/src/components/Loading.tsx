import "./Loading.css";

interface LoadingProps {
  /** What is loading, read aloud and shown under the spinner. */
  label: string;
}

/** The centered spinner of a pane whose content is still on its way. */
export function Loading({ label }: LoadingProps) {
  return (
    <div className="loading" role="status" aria-label={label}>
      <span className="loading__spinner" aria-hidden="true" />
      <span className="loading__label">{label}…</span>
    </div>
  );
}
