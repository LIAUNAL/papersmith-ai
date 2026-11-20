import type { ApiClient, Capability, Settings } from "../api/types.ts";
import type { PassageFocus } from "../explain/focus.ts";
import { CompileOptions } from "../compile/CompileOptions.tsx";
import { LogPanel } from "../compile/LogPanel.tsx";
import type { CompileState } from "../compile/compile-state.ts";
import type { PdfEngine } from "./engine.ts";
import type { PdfSelection } from "../embed/bridge.ts";
import { PdfPreview } from "./PdfPreview.tsx";
import type { PrefsStore } from "./prefs.ts";
import "./PreviewPane.css";

/** Why compiling is impossible, in words the user can act on. */
export const ENGINE_MISSING_MESSAGE =
  "The LaTeX engine (Tectonic) was not found. Install Tectonic and make sure it is on the PATH, then reload this page.";

interface PreviewPaneProps {
  api: Pick<ApiClient, "readPdf" | "readLog">;
  engine: PdfEngine;
  engineStatus: Capability;
  sandboxStatus: Capability;
  compile: CompileState;
  settings: Settings;
  onSettingsChange: (patch: Partial<Settings>) => Promise<string | null>;
  prefs: PrefsStore;
  /** Opens a file at a line in the editor, for a clicked diagnostic. Resolves to a message when it could not. */
  onOpenDiagnostic: (file: string, line: number) => Promise<string | null>;
  /** Makes the PDF text selectable and reports each selection. */
  onTextSelected?: (selection: PdfSelection) => void;
  /** Passages to mark in soft yellow on the pages. */
  highlights?: readonly string[];
  focus?: PassageFocus | null;
}

/** The body of the preview pane: compile switches, notices, the PDF and the log panel below it. */
export function PreviewPane({ api, engine, engineStatus, sandboxStatus, compile, settings, onSettingsChange, prefs, onOpenDiagnostic, onTextSelected, highlights, focus }: PreviewPaneProps) {
  return (
    <div className="preview-pane">
      <CompileOptions settings={settings} sandbox={sandboxStatus} onChange={onSettingsChange} />
      {!engineStatus.available ? (
        <p role="alert" className="preview-pane__notice">
          {ENGINE_MISSING_MESSAGE}
          {engineStatus.reason === undefined ? null : <span className="preview-pane__reason">{` ${engineStatus.reason}`}</span>}
        </p>
      ) : compile.problem !== null ? (
        <p role="alert" className="preview-pane__notice">
          {compile.problem}
        </p>
      ) : null}
      <div className="preview-pane__body">
        <PdfPreview api={api} engine={engine} compile={compile} prefs={prefs} {...(onTextSelected === undefined ? {} : { onTextSelected })} {...(highlights === undefined ? {} : { highlights })} {...(focus === undefined ? {} : { focus })} />
      </div>
      <LogPanel api={api} last={compile.last} onOpen={onOpenDiagnostic} />
    </div>
  );
}
