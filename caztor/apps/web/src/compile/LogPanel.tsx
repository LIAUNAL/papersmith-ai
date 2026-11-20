import { useEffect, useRef, useState } from "react";
import type { ApiClient, CompileResult, Diagnostic } from "../api/types.ts";
import { Icon } from "../components/Icon.tsx";
import type { CompileState } from "./compile-state.ts";
import { boundLogText, MAX_SHOWN_LOG_CHARS } from "./log-text.ts";
import "./LogPanel.css";

interface LogPanelProps {
  api: Pick<ApiClient, "readLog">;
  /** The latest finished compile, or null before the first one. */
  last: CompileState["last"];
  /** Opens `file` in the editor at `line`. Resolves to a readable message when it could not. */
  onOpen: (file: string, line: number) => Promise<string | null>;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The file and line a diagnostic can jump to; null when it lacks either. */
function target(entry: Diagnostic): { file: string; line: number } | null {
  return entry.file !== null && entry.line !== null ? { file: entry.file, line: entry.line } : null;
}

function Entry({ entry, onJump }: { entry: Diagnostic; onJump: (file: string, line: number) => void }) {
  const place = target(entry);
  const label = entry.severity === "error" ? "Error" : "Warning";
  const body = (
    <>
      <span className={`log-entry__severity log-entry__severity--${entry.severity}`}>{label}</span>
      <span className="log-entry__text">
        <span className="log-entry__message">{entry.message}</span>
        {entry.detail === undefined ? null : <span className="log-entry__detail">{entry.detail}</span>}
      </span>
      {place === null ? null : <span className="log-entry__place">{`${place.file}:${place.line}`}</span>}
    </>
  );
  return (
    <li className={`log-entry log-entry--${entry.severity}`}>
      {place === null ? (
        <div className="log-entry__row">{body}</div>
      ) : (
        <button type="button" className="log-entry__row log-entry__row--action" aria-label={`Go to ${place.file} line ${place.line}`} onClick={() => onJump(place.file, place.line)}>
          {body}
        </button>
      )}
    </li>
  );
}

function RawLog({ text }: { text: string }) {
  const shown = boundLogText(text);
  return (
    <>
      {shown.hidden === 0 ? null : (
        <p className="log-panel__empty">
          {`Showing the last ${MAX_SHOWN_LOG_CHARS.toLocaleString("en-US")} characters of ${text.length.toLocaleString("en-US")}.`}
        </p>
      )}
      <pre className="log-panel__raw-text" tabIndex={0} aria-label="Raw compile log">
        {shown.text}
      </pre>
    </>
  );
}

/** The errors and warnings of the last compile, each a jump to its line, and the engine's raw log. */
export function LogPanel({ api, last, onOpen }: LogPanelProps) {
  const result: CompileResult | null = last?.result ?? null;
  const diagnostics = result?.diagnostics ?? [];
  const errors = diagnostics.filter((entry) => entry.severity === "error").length;
  const warnings = diagnostics.length - errors;
  const [open, setOpen] = useState(true);
  const [raw, setRaw] = useState<{ state: "closed" } | { state: "loading" } | { state: "shown"; text: string } | { state: "failed"; message: string }>({ state: "closed" });
  const [problem, setProblem] = useState<string | null>(null);

  // A new compile: errors open the panel again; the raw log on screen belongs to the previous run, so it is read again.
  const compileId = last?.compileId ?? null;
  const seen = useRef<string | null>(compileId);
  const showingRaw = raw.state !== "closed";
  useEffect(() => {
    if (seen.current === compileId) return;
    seen.current = compileId;
    setProblem(null);
    if (errors > 0) setOpen(true);
    if (showingRaw) void loadRaw();
  });

  async function loadRaw(): Promise<void> {
    setRaw({ state: "loading" });
    try {
      setRaw({ state: "shown", text: await api.readLog() });
    } catch (error) {
      setRaw({ state: "failed", message: error instanceof Error ? error.message : "The log could not be read." });
    }
  }

  async function jump(file: string, line: number): Promise<void> {
    setProblem(await onOpen(file, line));
  }

  const counts = [errors > 0 ? plural(errors, "error") : null, warnings > 0 ? plural(warnings, "warning") : null].filter((part) => part !== null);

  return (
    <div className="log-panel" role="group" aria-label="Compile log">
      <h3 className="log-panel__heading">
        <button type="button" className="log-panel__toggle" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
          <Icon name="chevron" className={`log-panel__chevron${open ? " log-panel__chevron--open" : ""}`} />
          Log
          {errors > 0 ? <span className="log-panel__count log-panel__count--error">{plural(errors, "error")}</span> : null}
          {warnings > 0 ? <span className="log-panel__count log-panel__count--warning">{plural(warnings, "warning")}</span> : null}
          {counts.length === 0 && result !== null ? <span className="log-panel__count">No problems</span> : null}
        </button>
      </h3>
      {!open ? null : (
        <div className="log-panel__body">
          <div className="log-panel__tools">
            <button
              type="button"
              className="button log-panel__raw"
              disabled={result === null || !result.logAvailable}
              onClick={() => (showingRaw ? setRaw({ state: "closed" }) : void loadRaw())}
            >
              {showingRaw ? "Show errors and warnings" : "Show raw log"}
            </button>
          </div>
          {problem === null ? null : (
            <p role="alert" className="log-panel__problem">
              {problem}
            </p>
          )}
          {raw.state === "loading" ? <p className="log-panel__empty">Reading the log</p> : null}
          {raw.state === "failed" ? (
            <p role="alert" className="log-panel__problem">
              {raw.message}
            </p>
          ) : null}
          {raw.state === "shown" ? <RawLog text={raw.text} /> : null}
          {!showingRaw ? (
            result === null ? (
              <p className="log-panel__empty">Compile the project to see errors and warnings here.</p>
            ) : diagnostics.length === 0 ? (
              <p className="log-panel__empty">No errors or warnings.</p>
            ) : (
              <ul className="log-panel__list" aria-label="Errors and warnings">
                {diagnostics.map((entry, index) => (
                  <Entry key={`${index}:${entry.file ?? ""}:${entry.line ?? ""}:${entry.message}`} entry={entry} onJump={(file, line) => void jump(file, line)} />
                ))}
              </ul>
            )
          ) : null}
        </div>
      )}
    </div>
  );
}
