import { posix } from "node:path";
import type { Diagnostic } from "@caztor/core";
import type { FileResolver } from "./diagnostics.ts";

/** The engine breaks log lines at this many characters, in the middle of words and paths. */
const LOG_LINE_WIDTH = 79;

const WARNING_START = /^(LaTeX(?: Font)?|Package (\S+)|Class (\S+)|Module (\S+)) Warning: ?(.*)$/;
const CONTINUATION = /^\((\S+)\)\s*(.*)$/;
const INPUT_LINE = /\s+on input line (\d+)\.?$/;
/** Summaries that only repeat the per-reference warnings or ask for a rerun the engine already does. */
const SUMMARIES = [/^There were undefined references\.?$/, /^Label\(s\) may have changed\. Rerun to get cross-references right\.?$/];

/** Joins lines the engine wrapped at the line width. */
function logicalLines(text: string): string[] {
  const physical = text.split(/\r?\n/);
  const joined: string[] = [];
  for (let i = 0; i < physical.length; i += 1) {
    let piece = physical[i]!;
    let line = piece;
    while (piece.length >= LOG_LINE_WIDTH && i + 1 < physical.length) {
      i += 1;
      piece = physical[i]!;
      line += piece;
    }
    joined.push(line);
  }
  return joined;
}

function warningMessage(match: RegExpExecArray, body: string): string {
  const owner = match[2] ?? match[3] ?? match[4];
  return owner === undefined ? body : `${owner}: ${body}`;
}

export interface LogReport {
  diagnostics: Diagnostic[];
  /** Every name the engine opened, as printed: `main.tex`, `../outside/x.tex`, `/abs/y.tex`. */
  openedFiles: string[];
}

/**
 * Reads the kept `.log`: LaTeX, package and class warnings (which appear only here), each attributed to the file
 * being read through the log's open-file parentheses. Attribution is best effort; without a project file the
 * warning has no jump target. TeX errors are not read from the log, stderr reports them.
 */
export function parseLog(text: string, resolve: FileResolver): LogReport {
  const diagnostics: Diagnostic[] = [];
  const seen = new Set<string>();
  const opened: string[] = [];
  const stack: string[] = [];
  const lines = logicalLines(text);

  const currentFile = () => {
    for (let depth = stack.length - 1; depth >= 0; depth -= 1) {
      const file = resolve(stack[depth]!);
      if (file !== null) return file;
    }
    return null;
  };

  const addWarning = (match: RegExpExecArray, block: string[]): void => {
    const joined = [match[5] ?? "", ...block].join(" ").replace(/\s+/g, " ").trim();
    if (SUMMARIES.some((summary) => summary.test(joined))) return;
    const located = INPUT_LINE.exec(joined);
    const body = located === null ? joined : joined.slice(0, located.index);
    const file = located === null ? null : currentFile();
    const fileLine = located !== null && file !== null ? Number(located[1]) : null;
    const known = located === null ? currentFile() : file;
    const message =
      located !== null && file === null ? `${warningMessage(match, body)} on input line ${located[1]}` : warningMessage(match, body);
    const diagnostic: Diagnostic = { severity: "warning", file: known, line: fileLine, message, source: "log" };
    const key = `${diagnostic.file}|${diagnostic.line}|${diagnostic.message}`;
    if (seen.has(key)) return;
    seen.add(key);
    diagnostics.push(diagnostic);
  };

  let skippingErrorBlock = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    if (line === "") {
      skippingErrorBlock = false;
      continue;
    }
    if (line.startsWith("! ")) skippingErrorBlock = true;
    if (skippingErrorBlock) continue;

    const start = WARNING_START.exec(line);
    if (start !== null) {
      const block: string[] = [];
      while (index + 1 < lines.length && lines[index + 1] !== "") {
        index += 1;
        const continuation = CONTINUATION.exec(lines[index]!);
        block.push(continuation === null ? lines[index]! : continuation[2]!);
      }
      addWarning(start, block);
      continue;
    }

    for (let at = 0; at < line.length; at += 1) {
      const char = line[at];
      if (char === "(") {
        const end = line.slice(at + 1).search(/[\s()]/);
        const token = end === -1 ? line.slice(at + 1) : line.slice(at + 1, at + 1 + end);
        stack.push(token);
        if (token !== "" && !opened.includes(token)) opened.push(token);
        at += token.length;
      } else if (char === ")") {
        stack.pop();
      }
    }
  }

  return { diagnostics, openedFiles: opened };
}

const ABSOLUTE_PATH_WARNING = /^warning: accessing absolute path `(.+)`; build may not be reproducible/;
const OUTSIDE_DETAIL =
  "Compiling can read any file you can read, and its content can end up in the PDF and the log. Shell escape stays disabled.";

function isInside(root: string, absolute: string): boolean {
  return absolute === root || absolute.startsWith(`${root}/`);
}

/**
 * Warnings for files the engine read from outside the project: the engine's own absolute-path warning, and any file
 * the log shows opening outside the root (a `../` path gives no engine warning). Best effort: reads through `\openin`
 * and graphics are not covered. Each file is named once, as its absolute path.
 */
export function outsideReads(input: { root: string; stderr: string; openedFiles: readonly string[] }): Diagnostic[] {
  const root = posix.normalize(input.root).replace(/\/+$/, "");
  const found = new Map<string, Diagnostic>();

  const note = (name: string, source: "stderr" | "log"): void => {
    const absolute = posix.resolve(root, name);
    if (isInside(root, absolute) || found.has(absolute)) return;
    found.set(absolute, {
      severity: "warning",
      file: null,
      line: null,
      message: `The document reads a file outside the project: ${absolute}`,
      detail: OUTSIDE_DETAIL,
      source,
    });
  };

  for (const line of input.stderr.split(/\r?\n/)) {
    const match = ABSOLUTE_PATH_WARNING.exec(line);
    if (match !== null) note(match[1]!, "stderr");
  }
  for (const name of input.openedFiles) note(name, "log");
  return [...found.values()];
}
