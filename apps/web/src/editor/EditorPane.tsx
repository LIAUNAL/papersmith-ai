import { endOfDocumentMisplaced, moveEndOfDocument } from "@caztor/core";
import { useEffect, useState, useSyncExternalStore } from "react";
import { EmptyState } from "../components/EmptyState.tsx";
import { CodeEditor } from "./CodeEditor.tsx";
import { CompareView } from "./CompareView.tsx";
import { ConflictBanner } from "./ConflictBanner.tsx";
import type { BufferStatus, EditorSession } from "./session.ts";
import "./EditorPane.css";

interface EditorPaneProps {
  session: EditorSession;
  /** Passages to mark in soft yellow in the file shown. */
  highlights?: readonly string[];
}

const STATUS_LABEL: Record<BufferStatus, string> = {
  saved: "Saved",
  saving: "Saving",
  dirty: "Unsaved changes",
  conflict: "Conflict",
  error: "Not saved",
};

/** The editor for the file the session has active: its name, save state and the text itself. */
export function EditorPane({ session, highlights }: EditorPaneProps) {
  const { buffers, active, jump } = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const buffer = active === null ? undefined : buffers.get(active);
  const [comparing, setComparing] = useState(false);
  const inConflict = buffer?.conflict != null;
  // The comparison belongs to one conflict: a later conflict starts with the plain editor.
  useEffect(() => {
    if (!inConflict) setComparing(false);
  }, [inConflict]);

  if (buffer === undefined) {
    return <EmptyState title="No file open">Select a LaTeX file in the project to start editing.</EmptyState>;
  }

  return (
    <div className="editor">
      <div className="editor__bar">
        <span className="editor__path" title={buffer.path}>
          {buffer.path}
        </span>
        <span role="status" className={`editor__status editor__status--${buffer.status}`}>
          {STATUS_LABEL[buffer.status]}
        </span>
      </div>
      {buffer.status === "error" ? (
        <div role="alert" className="editor__problem">
          <span>Not saved: {buffer.error}</span>
          <button type="button" className="button" onClick={() => void session.saveNow(buffer.path)}>
            Save again
          </button>
        </div>
      ) : null}
      {buffer.path.toLowerCase().endsWith(".tex") && endOfDocumentMisplaced(buffer.text) ? (
        <div role="alert" className="editor__problem">
          <span>PaperSmith added a block after \end{"{document}"}, where LaTeX no longer reads.</span>
          <button type="button" className="button" onClick={() => session.edit(buffer.path, moveEndOfDocument(buffer.text))}>
            Move \end{"{document}"} to the end
          </button>
        </div>
      ) : null}
      <ConflictBanner
        buffer={buffer}
        comparing={comparing}
        onKeepMine={() => void session.keepMine(buffer.path)}
        onLoadDisk={() => void session.takeDisk(buffer.path)}
        onSaveCopy={() => void session.saveCopy(buffer.path)}
        onToggleCompare={() => setComparing((current) => !current)}
      />
      <div className="editor__body">
        {comparing && buffer.conflict?.disk != null ? (
          <CompareView path={buffer.path} disk={buffer.conflict.disk.text} mine={buffer.text} />
        ) : (
          <CodeEditor
            path={buffer.path}
            text={buffer.text}
            label={buffer.path}
            onChange={(text) => session.edit(buffer.path, text)}
            onSave={() => void session.saveNow(buffer.path)}
            {...(highlights === undefined ? {} : { highlights })}
            {...(jump !== null && jump.path === buffer.path ? { reveal: { line: jump.line, id: jump.id } } : {})}
          />
        )}
      </div>
    </div>
  );
}
