import type { Capability } from "../api/types.ts";
import { Icon } from "../components/Icon.tsx";
import { describeCompile, type CompileState } from "./compile-state.ts";
import "./CompileToolbar.css";

interface CompileToolbarProps {
  state: CompileState;
  engine: Capability;
  onCompile: () => void;
  onCancel: () => void;
  /** The file open in the editor, offered for compiling when it is LaTeX and not the main file. */
  currentFile?: string | null;
  /** The project's main file setting; null means Caztor picks it (`main.tex` first). */
  mainFile?: string | null;
  onCompileFile?: (path: string) => void;
}

/** The compile control in the preview pane's header: what is happening, and Compile, which becomes Cancel while a run is going. */
export function CompileToolbar({ state, engine, onCompile, onCancel, currentFile = null, mainFile = null, onCompileFile }: CompileToolbarProps) {
  const busy = state.running;
  const other =
    currentFile !== null && onCompileFile !== undefined && currentFile.toLowerCase().endsWith(".tex") && currentFile !== (mainFile ?? "main.tex")
      ? currentFile
      : null;
  const label = engine.available ? describeCompile(state) : "LaTeX engine not found";
  return (
    <div className="compile-toolbar">
      <span role="status" className={`compile-toolbar__status${busy ? " compile-toolbar__status--busy" : ""}`} title={label}>
        {label}
      </span>
      {busy ? (
        <button type="button" className="button compile-toolbar__button" onClick={onCancel}>
          <Icon name="stop" />
          Cancel
        </button>
      ) : (
        <>
          {other === null ? null : (
            <button
              type="button"
              className="button compile-toolbar__button"
              disabled={!engine.available}
              title={`Compile ${other} instead of the main file`}
              onClick={() => onCompileFile?.(other)}
            >
              Compile {other.slice(other.lastIndexOf("/") + 1)}
            </button>
          )}
          <button type="button" className="button button--primary compile-toolbar__button" disabled={!engine.available} onClick={onCompile}>
            <Icon name="play" />
            Compile
          </button>
        </>
      )}
    </div>
  );
}
