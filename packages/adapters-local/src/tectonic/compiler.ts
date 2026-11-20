import { biblatexNotice } from "@caztor/core";
import type {
  CompileEvent,
  CompileRequest,
  CompileResult,
  CompilerPort,
  Diagnostic,
  ProjectStorePort,
  RelPath,
  TexSource,
} from "@caztor/core";
import type { ChildHandle, Clock, CommandWrapper, FileSystem, ProcessSpawner } from "../infra.ts";
import { buildCompileArgs, buildCompileEnv, LAST_LOG, OUT_DIR, PREVIEW_PDF } from "./command.ts";
import { explainBiberFailure, finalizeRun, parseStderr, stderrTail, type FileResolver } from "./diagnostics.ts";
import { mergedLines, phaseOfLine } from "./line-reader.ts";
import { readBoundedLog, readLogForParsing } from "./log-bounds.ts";
import { outsideReads, parseLog } from "./log-parser.ts";
import { sandboxStartFailure, type Sandbox } from "../sandbox.ts";

/** Wall-clock limit of a run, in milliseconds. */
export const TIME_LIMIT_MS = 180_000;
/** The limit once the run reports downloading support files, counted from the start of the run. */
export const DOWNLOAD_TIME_LIMIT_MS = 600_000;
/** How long the engine gets to stop after SIGTERM before the group is killed. */
export const KILL_GRACE_MS = 2_000;
/** Stderr beyond this is not kept. */
export const MAX_STDERR_BYTES = 2 * 1024 * 1024;
const PROBE_LIMIT_MS = 5_000;
const MAX_SOURCE_FILES = 200;
const MAX_SOURCE_BYTES = 1024 * 1024;
const TEX_SOURCE = /\.(tex|sty|cls)$/;

export interface TectonicCompilerOptions {
  spawner: ProcessSpawner;
  clock: Clock;
  fs: FileSystem;
  /** Absolute path of the project folder. The engine runs there. */
  root: string;
  /** The project's files, used to attribute diagnostics and to scan for biblatex. */
  store: Pick<ProjectStorePort, "list" | "read">;
  /** The server's environment. Only the allowlisted names reach the engine. */
  parentEnv: Readonly<Record<string, string | undefined>>;
  binary?: string;
  /** Runs the engine inside bubblewrap for requests with `sandboxed: true`. Without it such a request is refused. */
  sandbox?: Sandbox;
  newCompileId?: () => string;
}

const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

function isMissing(error: unknown): boolean {
  return (error as { code?: string } | null)?.code === "ENOENT";
}

async function drainQuietly(stream: AsyncIterable<Uint8Array>): Promise<void> {
  try {
    for await (const chunk of stream) void chunk;
  } catch {
    // Output that cannot be read is simply not read.
  }
}

/** The compile adapter: runs `tectonic`, reports phases, derives the status and keeps the last good PDF. */
export function createTectonicCompiler(options: TectonicCompilerOptions): CompilerPort {
  const { spawner, clock, fs, root, store } = options;
  const binary = options.binary ?? "tectonic";
  const env = buildCompileEnv(options.parentEnv);
  const newId = options.newCompileId ?? (() => crypto.randomUUID());
  let lastRev = 0;

  const path = (relative: string) => `${root}/${relative}`;
  const jobName = (main: string) => (main.split("/").pop() ?? main).replace(/\.[^.]*$/, "");

  async function readIfPresent(file: string): Promise<Uint8Array | null> {
    try {
      return await fs.readFile(file);
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
  }

  async function exists(file: string): Promise<boolean> {
    try {
      return (await fs.stat(file)).isFile();
    } catch {
      return false;
    }
  }

  async function projectFiles(): Promise<{ resolve: FileResolver; sources: TexSource[] }> {
    const entries = (await store.list()).filter((entry) => entry.kind === "file");
    const known = new Set<string>(entries.map((entry) => entry.path));
    const resolve: FileResolver = (raw) => {
      const name = raw.startsWith("./") ? raw.slice(2) : raw;
      for (const candidate of [name, `${name}.tex`]) if (known.has(candidate)) return candidate as RelPath;
      return null;
    };
    const sources: TexSource[] = [];
    for (const entry of entries.filter((candidate) => TEX_SOURCE.test(candidate.path) && candidate.size <= MAX_SOURCE_BYTES)) {
      if (sources.length >= MAX_SOURCE_FILES) break;
      const read = await store.read(entry.path);
      if (read.ok) sources.push({ path: entry.path, text: decode(read.value.bytes) });
    }
    return { resolve, sources };
  }

  /** Copies the PDF beside the preview and renames it over it, so readers never see a half-written file. */
  async function promote(job: string): Promise<string | null> {
    const temporary = `${path(PREVIEW_PDF)}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.copyFile(path(`${OUT_DIR}/${job}.pdf`), temporary);
      await fs.rename(temporary, path(PREVIEW_PDF));
    } catch {
      await fs.rm(temporary, { force: true }).catch(() => {});
      return null;
    }
    lastRev = Math.max(lastRev + 1, clock.now());
    return String(lastRev);
  }

  async function copyLog(job: string): Promise<boolean> {
    const temporary = `${path(LAST_LOG)}.${crypto.randomUUID()}.tmp`;
    try {
      const log = await readBoundedLog(fs, path(`${OUT_DIR}/${job}.log`));
      if (log === null) return false;
      await fs.writeFile(temporary, log.bytes);
      await fs.rename(temporary, path(LAST_LOG));
      return true;
    } catch {
      await fs.rm(temporary, { force: true }).catch(() => {});
      return false;
    }
  }

  async function* compile(req: CompileRequest, signal: AbortSignal): AsyncGenerator<CompileEvent> {
    const compileId = newId();
    const startedAt = clock.now();
    yield { type: "started", compileId };

    const finished = (status: CompileResult["status"], diagnostics: Diagnostic[], extra: Partial<CompileResult> = {}): CompileEvent => ({
      type: "finished",
      compileId,
      result: { status, pdfRev: null, diagnostics, durationMs: clock.now() - startedAt, logAvailable: false, ...extra },
    });
    const failure = (message: string, detail?: string): Diagnostic => ({
      severity: "error",
      file: null,
      line: null,
      message,
      ...(detail === undefined ? {} : { detail }),
      source: "caztor",
    });

    const sandboxFailure = (detail?: string): Diagnostic =>
      failure("The sandbox could not start. Turn off \"Sandboxed compile\" in the compile options to compile without it.", detail);

    let args: string[];
    try {
      args = buildCompileArgs(req);
    } catch (error) {
      yield finished("failed", [failure(error instanceof Error ? error.message : "The main file is not valid.")]);
      return;
    }
    if (signal.aborted) {
      yield finished("cancelled", []);
      return;
    }

    let wrap: CommandWrapper = (spec) => spec;
    if (req.sandboxed === true) {
      try {
        if (options.sandbox === undefined) throw new Error("This build has no sandbox.");
        wrap = await options.sandbox.wrapper();
      } catch (error) {
        yield finished("failed", [sandboxFailure(error instanceof Error ? error.message : undefined)]);
        return;
      }
    }

    let files: Awaited<ReturnType<typeof projectFiles>>;
    try {
      await fs.rm(path(OUT_DIR), { recursive: true, force: true });
      await fs.mkdir(path(OUT_DIR), { recursive: true });
      files = await projectFiles();
    } catch (error) {
      yield finished("failed", [failure("Could not prepare the build folder.", error instanceof Error ? error.message : undefined)]);
      return;
    }
    const job = jobName(req.main);

    // The limit, the kill escalation and the abort listener all end the same child; the first cause wins.
    let killed: "cancelled" | "timed-out" | null = null;
    let downloading = false;
    let child: ChildHandle | undefined;
    let cancelLimit: () => void = () => {};
    let cancelKill: () => void = () => {};
    let spawnedAt = clock.now();

    const terminate = (cause: "cancelled" | "timed-out"): void => {
      killed ??= cause;
      if (child === undefined) return;
      child.killGroup("SIGTERM");
      cancelKill();
      const handle = child;
      cancelKill = clock.setTimeout(() => handle.killGroup("SIGKILL"), KILL_GRACE_MS);
    };
    const armLimit = (totalMs: number): void => {
      cancelLimit();
      cancelLimit = clock.setTimeout(() => terminate("timed-out"), Math.max(0, totalMs - (clock.now() - spawnedAt)));
    };
    const onAbort = () => terminate("cancelled");
    signal.addEventListener("abort", onAbort, { once: true });

    const lines: string[] = [];
    let storedBytes = 0;
    let truncated = false;
    let phase: string | null = null;
    const phases: CompileEvent[] = [];
    const take = (line: string): void => {
      if (storedBytes <= MAX_STDERR_BYTES) {
        lines.push(line);
        storedBytes += line.length + 1;
      } else {
        truncated = true;
      }
      const next = phaseOfLine(line);
      if (next !== null && next !== phase) {
        phase = next;
        phases.push({ type: "phase", phase: next });
        if (next === "downloading" && !downloading) {
          downloading = true;
          if (killed === null) armLimit(DOWNLOAD_TIME_LIMIT_MS);
        }
      }
    };

    let exit: { code: number | null; signal: string | null } | { error: unknown };
    try {
      spawnedAt = clock.now();
      child = spawner.spawn(wrap({ file: binary, args, cwd: root, env }));
      armLimit(TIME_LIMIT_MS);
      if (signal.aborted) terminate("cancelled");
      const settled = child.exit.then(
        (value) => value,
        (error: unknown) => ({ error }),
      );
      // tectonic prints notes on stdout and warnings and errors on stderr when they are separate pipes.
      for await (const line of mergedLines([child.stderr, child.stdout])) {
        take(line);
        while (phases.length > 0) yield phases.shift()!;
      }
      exit = await settled;
    } finally {
      cancelLimit();
      cancelKill();
      signal.removeEventListener("abort", onAbort);
    }

    if ("error" in exit) {
      if (isMissing(exit.error)) {
        yield finished("engine-missing", [
          failure("Tectonic was not found. Install Tectonic and make sure it is on the PATH, then compile again."),
        ]);
      } else {
        yield finished("failed", [failure("The LaTeX engine could not be started.", exit.error instanceof Error ? exit.error.message : undefined)]);
      }
      return;
    }

    const stderr = lines.join("\n");
    const refused = killed === null && req.sandboxed === true ? sandboxStartFailure(stderr) : null;
    if (refused !== null) {
      yield finished("failed", [sandboxFailure(refused)]);
      return;
    }
    const hasPdf = killed === null && (await exists(path(`${OUT_DIR}/${job}.pdf`)));
    const logRead = killed === null ? await readLogForParsing(fs, path(`${OUT_DIR}/${job}.log`)).catch(() => null) : null;
    const log = parseLog(logRead?.text ?? "", files.resolve);

    let diagnostics: Diagnostic[] = [
      ...parseStderr(stderr, files.resolve),
      ...log.diagnostics,
      ...outsideReads({ root, stderr, openedFiles: log.openedFiles }),
    ];
    const notice = biblatexNotice(files.sources);
    if (notice !== null) diagnostics.push(notice);
    diagnostics = explainBiberFailure(diagnostics, stderr, notice !== null);
    if (logRead !== null && logRead.skippedBytes > 0) {
      const total = logRead.text.length + logRead.skippedBytes;
      diagnostics.push({
        severity: "warning",
        file: null,
        line: null,
        message: `The compile log is ${(total / (1024 * 1024)).toFixed(1)} MB; only the last ${Math.round(logRead.text.length / (1024 * 1024))} MB was read for warnings.`,
        source: "caztor",
      });
    }
    if (truncated) {
      diagnostics.push({
        severity: "warning",
        file: null,
        line: null,
        message: "The engine printed more than 2 MB of messages; the rest was ignored.",
        source: "caztor",
      });
    }

    let pdfRev: string | null = null;
    if (hasPdf) {
      pdfRev = await promote(job);
      if (pdfRev === null) diagnostics.push(failure("The PDF was produced but could not be saved as the preview."));
    }
    const logAvailable = killed === null && logRead !== null ? await copyLog(job) : false;

    const outcome = finalizeRun({ killed, exitCode: exit.code, hasPdf, diagnostics, stderr, downloading });
    const ordered = [...outcome.diagnostics.filter((d) => d.severity === "error"), ...outcome.diagnostics.filter((d) => d.severity === "warning")];
    yield finished(outcome.status, ordered, { pdfRev, logAvailable });
  }

  return {
    async available() {
      const child = spawner.spawn({ file: binary, args: ["--version"], cwd: root, env });
      let output = "";
      let errorOutput = "";
      const collect = (async () => {
        const decoder = new TextDecoder();
        try {
          for await (const chunk of child.stdout) output += decoder.decode(chunk, { stream: true });
        } catch {
          // Treated as no output.
        }
      })();
      const collectErrors = (async () => {
        const decoder = new TextDecoder();
        try {
          for await (const chunk of child.stderr) errorOutput += decoder.decode(chunk, { stream: true });
        } catch {
          // Treated as no output.
        }
      })();
      let timedOut = false;
      const cancelProbeLimit = clock.setTimeout(() => {
        timedOut = true;
        child.killGroup("SIGTERM");
      }, PROBE_LIMIT_MS);
      try {
        const result = await child.exit;
        await Promise.all([collect, collectErrors]);
        if (timedOut) return { ok: false, reason: "Tectonic did not answer --version within 5 seconds." };
        if (result.code !== 0) {
          const detail = stderrTail(errorOutput, 1);
          return {
            ok: false,
            reason: `Tectonic was found but failed to run (exit code ${result.code ?? "none"})${detail === "" ? "" : `: ${detail}`}`,
          };
        }
        const version = /Tectonic\s+(\S+)/.exec(output)?.[1];
        if (version === undefined) {
          const seen = output.trim().split(/\r?\n/)[0]?.slice(0, 100) ?? "";
          return { ok: false, reason: `Tectonic answered --version with output that was not recognised: "${seen}"` };
        }
        return { ok: true, version };
      } catch (error) {
        if (timedOut) return { ok: false, reason: "Tectonic did not answer --version within 5 seconds." };
        if (isMissing(error)) return { ok: false, reason: "Tectonic was not found on the PATH." };
        return { ok: false, reason: `Tectonic could not be started${error instanceof Error ? `: ${error.message}` : "."}` };
      } finally {
        cancelProbeLimit();
      }
    },
    compile,
    async readArtifact(kind) {
      if (kind === "log") return (await readBoundedLog(fs, path(LAST_LOG)))?.bytes ?? null;
      return readIfPresent(path(PREVIEW_PDF));
    },
  };
}
