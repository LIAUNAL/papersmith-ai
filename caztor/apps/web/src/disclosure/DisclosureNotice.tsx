import { useState } from "react";
import { Dialog } from "../components/Dialog.tsx";
import "./DisclosureNotice.css";

interface DisclosureNoticeProps {
  /** Records the acknowledgement for this project. A rejection keeps the notice open and shows its message. */
  onAcknowledge: () => Promise<void>;
}

/** The first-use notice about what Caztor runs and what leaves the machine. It can only be closed by acknowledging it. */
export function DisclosureNotice({ onAcknowledge }: DisclosureNoticeProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acknowledge(): Promise<void> {
    setSaving(true);
    setError(null);
    try {
      await onAcknowledge();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The acknowledgement could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      title="Before you start"
      actions={
        <button type="button" className="button button--primary" disabled={saving} onClick={() => void acknowledge()}>
          {saving ? "Saving" : "I understand"}
        </button>
      }
    >
      <p>Caztor runs the LaTeX engine and the AI agent you select as your user, on this computer.</p>
      <ul className="disclosure__list">
        <li>Compiling can read any file you can read. Shell escape stays disabled.</li>
        <li>An AI agent works with file tools, and its reads may reach beyond the project folder.</li>
        <li>Whatever an agent reads is sent to the model provider.</li>
      </ul>
      <p>Open only projects you trust.</p>
      {error === null ? null : (
        <p role="alert" className="disclosure__error">
          {error}
        </p>
      )}
    </Dialog>
  );
}
