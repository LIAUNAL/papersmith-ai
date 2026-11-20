import type { BufferView } from "./session.ts";
import "./ConflictBanner.css";

interface ConflictBannerProps {
  buffer: BufferView;
  comparing: boolean;
  onKeepMine: () => void;
  onLoadDisk: () => void;
  onSaveCopy: () => void;
  onToggleCompare: () => void;
}

/** Tells the user that the file changed on disk under their unsaved edits and offers the ways out. */
export function ConflictBanner({ buffer, comparing, onKeepMine, onLoadDisk, onSaveCopy, onToggleCompare }: ConflictBannerProps) {
  const conflict = buffer.conflict;
  if (conflict === null) return null;
  const canCompare = !conflict.deleted && conflict.disk !== null;
  return (
    <div role="alert" className="conflict">
      <p className="conflict__message">
        {conflict.deleted
          ? `${buffer.path} was deleted on disk while you have unsaved changes.`
          : `${buffer.path} changed on disk while you have unsaved changes.`}{" "}
        Autosave is paused until you choose.
      </p>
      {conflict.copiedTo === null ? null : <p className="conflict__note">Your version was saved as {conflict.copiedTo}.</p>}
      {conflict.problem === null ? null : <p className="conflict__problem">{conflict.problem}</p>}
      <div className="conflict__actions">
        <button type="button" className="button" onClick={onKeepMine}>
          Keep mine
        </button>
        <button type="button" className="button" onClick={onLoadDisk}>
          {conflict.deleted ? "Close file" : "Load disk version"}
        </button>
        <button type="button" className="button" onClick={onSaveCopy}>
          Save a copy
        </button>
        {canCompare ? (
          <button type="button" className="button" aria-pressed={comparing} onClick={onToggleCompare}>
            {comparing ? "Hide comparison" : "Compare"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
