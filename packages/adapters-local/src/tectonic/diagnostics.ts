import { parseRelPath } from "@caztor/core";
import type { Diagnostic, RelPath } from "@caztor/core";

/** Maps a file name as the engine printed it to a project file, or null when it is not one. */
export type FileResolver = (raw: string) => RelPath | null;

/** Accepts a name that is already a valid project path (a leading `./` is ignored). */
export const defaultFileResolver: FileResolver = (raw) => {
  const parsed = parseRelPath(raw.startsWith("./") ? raw.slice(2) : raw);
  return parsed.ok ? parsed.value : null;
};

const LOCATED = /^(.+?):(\d+): (.*)$/;
const TRANSCRIPT_RULE = /^={20,}$/;
const WRAPPER_START = "something bad happened inside XeTeX; its output follows:";
const WRAPPER_END = "the XeTeX engine had an unrecoverable error";
const IGNORED_ERRORS_MARKER = "errors were issued by the TeX engine, but were ignored";
const WARNINGS_MARKER = "warnings were issued by the TeX engine";
const CAUSED_BY = "caused by: ";
/** Reported by `outsideReads`, which can tell a file outside the project from one inside it. */
const ABSOLUTE_PATH_WARNING = "accessing absolute path ";

interface Entry {
  diagnostic: Diagnostic;
  located: boolean;
  causes: string[];
}

/** `! LaTeX Error: File ...` reads better as `File ...`; the severity already says it is an error. */
function plainMessage(message: string): string {
  return message.replace(/^(?:! )?LaTeX Error: /, "").replace(/^! /, "");
}

const PARAGRAPH_LINES = /\bat lines (\d+)--\d+/;
/** A box reported "in paragraph at lines A--B" is reported at B by the engine; the paragraph starts at A. */
function firstLine(message: string, reported: number): number {
  const match = PARAGRAPH_LINES.exec(message);
  return match === null ? reported : Number(match[1]);
}

const MISSING_FILE = /^(?:File `.*' not found\.|I can't find file)/;
/** Errors that a missing file or package causes further on: the macros it should have defined are unknown. */
const CASCADE = /^(?:Undefined control sequence|File `\.' not found\.|Environment .+ undefined\.|Missing \\begin\{document\})/;

/** Drops the errors that follow the first missing file and only repeat its consequences. */
function withoutCascades(entries: Entry[]): Entry[] {
  const first = entries.findIndex((entry) => entry.diagnostic.severity === "error" && MISSING_FILE.test(entry.diagnostic.message));
  if (first === -1) return entries;
  return entries.filter((entry, index) => index <= first || entry.diagnostic.severity !== "error" || !CASCADE.test(entry.diagnostic.message));
}

function located(severity: Diagnostic["severity"], rest: string, resolve: FileResolver): Entry | null {
  const match = LOCATED.exec(rest);
  if (match === null || match[1]!.includes("`")) return null;
  const raw = match[1]!;
  const message = plainMessage(match[3]!);
  const file = resolve(raw);
  const diagnostic: Diagnostic =
    file === null
      ? { severity, file: null, line: null, message: `${raw}: ${message}`, source: "stderr" }
      : { severity, file, line: firstLine(message, Number(match[2])), message, source: "stderr" };
  return { diagnostic, located: file !== null, causes: [] };
}

function unlocated(severity: Diagnostic["severity"], message: string): Entry {
  return { diagnostic: { severity, file: null, line: null, message, source: "stderr" }, located: false, causes: [] };
}

const keyOf = ({ diagnostic: d }: Entry): string => `${d.severity}|${d.file}|${d.line}|${d.message}`;

/**
 * Reads the engine's stderr. TeX errors arrive as `error: <file>:<line>: <message>`; the engine's own wrapper lines
 * and the transcript it prints on a halt are not user errors and are dropped when a located error explains the failure.
 * A rerun repeats its errors, so identical diagnostics are listed once.
 */
export function parseStderr(text: string, resolve: FileResolver = defaultFileResolver): Diagnostic[] {
  const entries: Entry[] = [];
  let wrapper: Entry | null = null;
  let last: Entry | null = null;
  let awaitingTranscript = false;
  let inTranscript = false;

  const add = (entry: Entry): void => {
    last = entry;
    if (!entries.some((existing) => keyOf(existing) === keyOf(entry))) entries.push(entry);
  };

  for (const line of text.split(/\r?\n/)) {
    if (TRANSCRIPT_RULE.test(line)) {
      if (awaitingTranscript) inTranscript = true;
      else inTranscript = false;
      awaitingTranscript = false;
      continue;
    }
    if (inTranscript) continue;

    if (line.startsWith("error: ")) {
      const rest = line.slice("error: ".length);
      if (rest === WRAPPER_START) {
        awaitingTranscript = true;
      } else if (rest === WRAPPER_END) {
        wrapper = unlocated("error", rest);
        last = wrapper;
      } else {
        add(located("error", rest, resolve) ?? unlocated("error", rest));
      }
    } else if (line.startsWith("warning: ")) {
      const rest = line.slice("warning: ".length);
      if (rest.startsWith(IGNORED_ERRORS_MARKER) || rest.startsWith(WARNINGS_MARKER)) continue;
      if (rest.startsWith(ABSOLUTE_PATH_WARNING)) continue;
      add(located("warning", rest, resolve) ?? unlocated("warning", rest));
    } else if (line.startsWith(CAUSED_BY)) {
      (last as Entry | null)?.causes.push(line.slice(CAUSED_BY.length));
    }
  }

  entries.splice(0, entries.length, ...withoutCascades(entries));
  const explained = entries.some((entry) => entry.diagnostic.severity === "error" && entry.located);
  const lastError = [...entries].reverse().find((entry) => entry.diagnostic.severity === "error");
  if (wrapper !== null) {
    if (!explained) entries.push(wrapper);
    else if (lastError !== undefined) lastError.causes.push(...wrapper.causes);
  }

  return entries.map(({ diagnostic, causes }) => (causes.length === 0 ? diagnostic : { ...diagnostic, detail: causes.join("\n") }));
}

export type RunStatus = "success" | "failed-with-errors" | "failed" | "timed-out" | "cancelled";

export interface RunOutcome {
  /** Set when Caztor ended the run: the user cancelled it, or a time limit expired. */
  killed: "cancelled" | "timed-out" | null;
  exitCode: number | null;
  /** Whether this run wrote a PDF (an older one left in the output folder does not count). */
  hasPdf: boolean;
  diagnostics: Diagnostic[];
  /** The captured stderr, used to explain a failure that printed no located error. */
  stderr: string;
  /** Whether the run reported downloading support files, which lets a failure be blamed on the network. */
  downloading: boolean;
}

const TAIL_LINES = 15;
const TAIL_CHARS = 2000;

/** The last non-empty lines of the engine's stderr, bounded in length. */
export function stderrTail(text: string, maxLines = TAIL_LINES): string {
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
  return lines.slice(-maxLines).join("\n").slice(-TAIL_CHARS);
}

const DOWNLOAD_FAILURE = [
  /couldn't get it from the internet/i,
  /error sending request/i,
  /dns error|failed to lookup address|could not resolve host/i,
  /connection (refused|reset|closed)/i,
  /timed out/i,
  /network is unreachable/i,
];

export const OFFLINE_MESSAGE = "Could not download LaTeX support files. The first compile needs a network connection.";

/** Recognised from the failure texts recorded offline; a failure while downloading is blamed on the network as a fallback. */
function downloadFailed(outcome: RunOutcome): boolean {
  return outcome.downloading || DOWNLOAD_FAILURE.some((pattern) => pattern.test(outcome.stderr));
}

function synthetic(message: string, stderr: string): Diagnostic {
  const detail = stderrTail(stderr);
  return {
    severity: "error",
    file: null,
    line: null,
    message,
    ...(detail === "" ? {} : { detail }),
    source: "caztor",
  };
}

/**
 * Decides the status from what the run reported, never from the exit code alone:
 * killed runs keep their cause, a run without a PDF failed, a PDF with an error failed-with-errors, otherwise success.
 * A failure that printed no error gets one synthetic error carrying the stderr tail.
 */
export function finalizeRun(outcome: RunOutcome): { status: RunStatus; diagnostics: Diagnostic[] } {
  if (outcome.killed !== null) return { status: outcome.killed, diagnostics: outcome.diagnostics };

  const diagnostics = [...outcome.diagnostics];
  if (!diagnostics.some((d) => d.severity === "error")) {
    if (outcome.exitCode !== 0 && downloadFailed(outcome)) {
      diagnostics.push(synthetic(OFFLINE_MESSAGE, outcome.stderr));
    } else if (outcome.exitCode !== 0) {
      diagnostics.push(synthetic(`The LaTeX engine failed (exit code ${outcome.exitCode ?? "none"}) without reporting an error.`, outcome.stderr));
    } else if (!outcome.hasPdf) {
      diagnostics.push(synthetic("The LaTeX engine finished without producing a PDF.", outcome.stderr));
    }
  }
  const hasError = diagnostics.some((d) => d.severity === "error");
  if (!outcome.hasPdf) return { status: "failed", diagnostics };
  return { status: hasError ? "failed-with-errors" : "success", diagnostics };
}

export const BIBER_MISSING_MESSAGE =
  "biblatex needs biber, which is not supported here, so the bibliography could not be built. Use BibTeX instead: load natbib, or use \\bibliographystyle and \\bibliography.";
const SPAWN_ERROR = /^No such file or directory \(os error 2\)$/;
const BIBER_RUN = /Running external tool biber/;

/**
 * When the engine failed to start biber, it reports only "No such file or directory (os error 2)". If the project uses
 * biblatex (or the engine says it ran biber) that error is replaced by one that names the cause; the raw text stays as detail.
 */
export function explainBiberFailure(diagnostics: Diagnostic[], stderr: string, biblatexInUse: boolean): Diagnostic[] {
  if (!biblatexInUse && !BIBER_RUN.test(stderr)) return diagnostics;
  return diagnostics.map((d) =>
    d.severity === "error" && d.file === null && SPAWN_ERROR.test(d.message)
      ? { severity: "error", file: null, line: null, message: BIBER_MISSING_MESSAGE, detail: d.message, source: "caztor" }
      : d,
  );
}
