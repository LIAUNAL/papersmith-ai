import { Dialog } from "../components/Dialog.tsx";
import type { UndoConflict } from "../api/types.ts";
import "./UndoConflictDialog.css";

interface UndoConflictDialogProps {
  conflicts: UndoConflict[];
  onCancel: () => void;
  /** Undo every other file and leave the changed ones as they are. */
  onKeepMine: () => void;
  /** Undo everything, replacing the later edits. */
  onOverwrite: () => void;
}

/** The three choices when files changed after the turn. Cancel comes first and takes Escape. */
export function UndoConflictDialog({ conflicts, onCancel, onKeepMine, onOverwrite }: UndoConflictDialogProps) {
  return (
    <Dialog
      title="Some files changed after this turn"
      onDismiss={onCancel}
      actions={
        <>
          <button type="button" className="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="button" onClick={onKeepMine}>
            Undo the rest and keep my edits
          </button>
          <button type="button" className="button button--danger" onClick={onOverwrite}>
            Overwrite my edits
          </button>
        </>
      }
    >
      <p>Undoing the whole turn would replace changes made after it:</p>
      <ul className="undo-conflicts">
        {conflicts.map((conflict) => (
          <li key={conflict.path}>{conflict.path}</li>
        ))}
      </ul>
      <p>Overwriting loses those edits, but Caztor takes a safety snapshot of the current state first.</p>
    </Dialog>
  );
}
