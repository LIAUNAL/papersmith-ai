import { useState } from "react";
import { Dialog } from "../components/Dialog.tsx";
import type { TreeNode } from "./tree.ts";

interface DeleteDialogProps {
  node: TreeNode;
  /** Resolves to an error message when the deletion failed, or null when it worked. */
  onConfirm: () => Promise<string | null>;
  onCancel: () => void;
}

/** Asks before anything is deleted. A folder is deleted together with everything inside it. */
export function DeleteDialog({ node, onConfirm, onCancel }: DeleteDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const folder = node.kind === "dir";

  async function confirm(): Promise<void> {
    setBusy(true);
    setError(await onConfirm());
    setBusy(false);
  }

  return (
    <Dialog
      title={folder ? `Delete folder ${node.path}?` : `Delete ${node.path}?`}
      onDismiss={onCancel}
      actions={
        <>
          <button type="button" className="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="button button--danger" disabled={busy} onClick={() => void confirm()}>
            {folder ? "Delete folder" : "Delete"}
          </button>
        </>
      }
    >
      <p>{folder ? "Everything inside it is deleted too. This cannot be undone." : "This cannot be undone."}</p>
      {error === null ? null : (
        <p role="alert" className="name-form__error">
          {error}
        </p>
      )}
    </Dialog>
  );
}
