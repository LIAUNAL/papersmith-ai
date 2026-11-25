import type { ChangedFile, ChatTurn } from "@caztor/core";
import { Icon } from "../components/Icon.tsx";
import "./TurnSummary.css";

interface TurnSummaryProps {
  turn: ChatTurn;
  /** This is the turn undo applies to. */
  canUndo: boolean;
  /** The undo of this turn restored everything. */
  undone: boolean;
  onUndo: () => void;
  onOpenFile: (path: string) => void;
}

const CHANGE_LABEL: Record<ChangedFile["change"], string> = { created: "Created", modified: "Modified", deleted: "Deleted" };

/** What a finished turn did to the project: the changed files, each one opening in the editor, and Undo on the undoable turn. */
export function TurnSummary({ turn, canUndo, undone, onUndo, onOpenFile }: TurnSummaryProps) {
  if (turn.status === "running" || turn.files === null) return null;
  const files = turn.files;
  return (
    <div className="turn-summary">
      <div className="turn-summary__head">
        <span className="turn-summary__title">{files.length === 0 ? "No files changed" : "Changed files"}</span>
        {undone ? <span className="turn-summary__undone">Undone</span> : null}
        {canUndo && !undone && files.length > 0 ? (
          <button type="button" className="button turn-summary__undo" onClick={onUndo}>
            <Icon name="undo" />
            Undo this turn
          </button>
        ) : null}
      </div>
      {files.length === 0 ? null : (
        <ul className="turn-summary__files">
          {files.map((file) => (
            <li key={file.path} className="turn-summary__file">
              <span className={`turn-summary__change turn-summary__change--${file.change}`}>{CHANGE_LABEL[file.change]}</span>
              {file.change === "deleted" ? (
                <span className="turn-summary__path">{file.path}</span>
              ) : (
                <button type="button" className="turn-summary__path turn-summary__path--link" onClick={() => onOpenFile(file.path)}>
                  {file.path}
                </button>
              )}
              {file.mixed ? <span className="turn-summary__flag">also edited by you during the turn</span> : null}
              {file.undoable ? null : <span className="turn-summary__flag">not covered by undo</span>}
            </li>
          ))}
        </ul>
      )}
      {turn.notCovered.length === 0 ? null : <p className="turn-summary__warning">Not covered by undo (names Caztor cannot read): {turn.notCovered.join(", ")}</p>}
      {files.length === 0 || turn.unprotected.length === 0 ? null : <Unprotected named={turn.unprotected} total={Math.max(turn.unprotectedCount ?? 0, turn.unprotected.length)} />}
    </div>
  );
}

/** The files the turn's snapshot could not protect, folded away: they matter only when the turn changed something. */
function Unprotected({ named, total }: { named: readonly string[]; total: number }) {
  const more = total - named.length;
  return (
    <details className="turn-summary__unprotected">
      <summary>{total === 1 ? "1 file not protected by undo" : `${total} files not protected by undo`}</summary>
      <ul>
        {named.map((path) => (
          <li key={path}>{path}</li>
        ))}
        {more > 0 ? <li className="turn-summary__more">and {more} more</li> : null}
      </ul>
    </details>
  );
}
