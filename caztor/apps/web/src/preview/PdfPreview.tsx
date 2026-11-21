import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { PassageFocus } from "../explain/focus.ts";
import type { ApiClient } from "../api/types.ts";
import type { CompileState } from "../compile/compile-state.ts";
import { EmptyState } from "../components/EmptyState.tsx";
import { Icon } from "../components/Icon.tsx";
import type { PdfDocument, PdfEngine } from "./engine.ts";
import { stepZoom, type Anchor, type Zoom } from "./layout.ts";
import { PdfViewer, type SourceJump } from "./PdfViewer.tsx";
import { INITIAL_PREVIEW_STATE, needsLoad, previewReducer } from "./preview-state.ts";
import type { PrefsStore } from "./prefs.ts";
import type { PdfSelection } from "../embed/bridge.ts";
import "./PdfPreview.css";

interface PdfPreviewProps {
  api: Pick<ApiClient, "readPdf">;
  engine: PdfEngine;
  compile: CompileState;
  prefs: PrefsStore;
  /** Makes the text selectable and reports each selection. */
  onTextSelected?: (selection: PdfSelection) => void;
  /** Passages to mark in soft yellow on the pages. */
  highlights?: readonly string[];
  focus?: PassageFocus | null;
  /** What a double click in the source asks the PDF to bring into view. */
  jump?: SourceJump | null;
}

/** Wait after the last scroll before the position is written to storage. */
const SAVE_DELAY_MS = 300;

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message !== "" ? error.message : fallback;
}

/** The preview pane: the latest PDF on canvas, zoom controls, and the empty, out-of-date and error states. */
export function PdfPreview({ api, engine, compile, prefs, onTextSelected, highlights, focus, jump }: PdfPreviewProps) {
  const initial = useMemo(() => prefs.load(), [prefs]);
  const [state, dispatch] = useReducer(previewReducer, INITIAL_PREVIEW_STATE);
  const [doc, setDoc] = useState<PdfDocument | null>(null);
  const [zoom, setZoom] = useState<Zoom>(initial.zoom);
  const [fitPercent, setFitPercent] = useState(100);
  const anchor = useRef<Anchor>(initial.anchor);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // What the server says about the preview: one may exist from an earlier run of the server, and each compile ends with a result.
  useEffect(() => {
    if (compile.pdfAvailable) dispatch({ type: "known", available: true });
  }, [compile.pdfAvailable]);
  const handled = useRef<string | null>(null);
  useEffect(() => {
    const last = compile.last;
    if (last === null || handled.current === last.compileId) return;
    handled.current = last.compileId;
    dispatch({ type: "finished", result: last.result });
  }, [compile.last]);

  // Load the wanted revision. The pane keeps showing the previous document until the new one is ready.
  const wanted = needsLoad(state) ? state.wantedRev : null;
  useEffect(() => {
    if (wanted === null) return;
    let live = true;
    void (async () => {
      let bytes: Uint8Array;
      try {
        bytes = await api.readPdf(wanted);
      } catch (error) {
        if (live) dispatch({ type: "load-failed", rev: wanted, message: messageOf(error, "The PDF could not be read.") });
        return;
      }
      let opened: PdfDocument;
      try {
        opened = await engine.open(bytes);
      } catch (error) {
        if (live) dispatch({ type: "load-failed", rev: wanted, message: `The PDF could not be shown: ${messageOf(error, "unknown problem")}` });
        return;
      }
      if (!live) {
        opened.destroy();
        return;
      }
      setDoc(opened);
      dispatch({ type: "loaded", rev: wanted });
    })();
    return () => {
      live = false;
    };
  }, [wanted, api, engine]);

  // A replaced or closed document is freed.
  useEffect(() => () => doc?.destroy(), [doc]);

  function persist(): void {
    if (saveTimer.current !== null) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveTimer.current = null;
      prefs.save({ zoom: zoomRef.current, anchor: anchor.current });
    }, SAVE_DELAY_MS);
  }
  useEffect(
    () => () => {
      if (saveTimer.current === null) return;
      clearTimeout(saveTimer.current);
      prefs.save({ zoom: zoomRef.current, anchor: anchor.current });
    },
    [prefs],
  );

  function changeZoom(next: Zoom): void {
    setZoom(next);
    zoomRef.current = next;
    persist();
  }

  const percent = zoom.mode === "percent" ? zoom.percent : fitPercent;
  const ready = doc !== null;

  return (
    <div className="preview">
      <div className="preview__bar" role="toolbar" aria-label="Preview controls">
        <div className="preview__zoom">
          <button type="button" className="icon-button" aria-label="Zoom out" title="Zoom out" disabled={!ready} onClick={() => changeZoom({ mode: "percent", percent: stepZoom(percent, "out") })}>
            <Icon name="zoom-out" />
          </button>
          <span className="preview__percent" aria-live="off">
            {ready ? `${percent}%` : "–"}
          </span>
          <button type="button" className="icon-button" aria-label="Zoom in" title="Zoom in" disabled={!ready} onClick={() => changeZoom({ mode: "percent", percent: stepZoom(percent, "in") })}>
            <Icon name="zoom-in" />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Fit width"
            title="Fit width"
            aria-pressed={zoom.mode === "fit"}
            disabled={!ready}
            onClick={() => changeZoom({ mode: "fit" })}
          >
            <Icon name="fit-width" />
          </button>
        </div>
        {state.outOfDate ? (
          <p role="status" aria-label="Preview status" className="preview__stale" title="The last compile did not produce a PDF, so this one does not match your source yet.">
            <Icon name="alert" />
            Out of date
          </p>
        ) : null}
      </div>
      {state.error === null ? null : (
        <p role="alert" className="preview__error">
          {state.error}
        </p>
      )}
      <div className="preview__body">
        {doc === null ? (
          <EmptyState title="No preview yet">Compile the project to see the PDF here.</EmptyState>
        ) : (
          <PdfViewer
            document={doc}
            zoom={zoom}
            anchor={anchor.current}
            onViewChange={(view) => {
              anchor.current = view.anchor;
              persist();
            }}
            onScaleChange={setFitPercent}
            {...(onTextSelected === undefined ? {} : { onTextSelected })}
            {...(highlights === undefined ? {} : { highlights })} {...(focus === undefined ? {} : { focus })}
            {...(jump === undefined ? {} : { jump })}
          />
        )}
      </div>
    </div>
  );
}
