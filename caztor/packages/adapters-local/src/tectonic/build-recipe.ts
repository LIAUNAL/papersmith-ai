import { createHash, createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import { parseRelPath, type CompileEvent, type CompileRequest, type CompileResult, type CompilerPort, type Diagnostic, type RelPath } from "@caztor/core";
import type { Clock, FileSystem, ProcessSpawner } from "../infra.ts";
import { buildCompileEnv } from "./command.ts";

/**
 * A project whose source is not itself a LaTeX document can declare how it is built, in `.caztor/build.json`:
 *
 *     { "when": ["paper/main.tex"], "before": ["python3", "paper/build_preview.py"], "root": "paper/preview.tex" }
 *
 * Compiling a file listed in `when` first runs `before` (an argument list, no shell) in the project folder, then
 * compiles `root` instead. A project can arrive with its own `.caztor/` (a clone, a shared folder, an archive), so
 * the step runs only once the host confirmed exactly this file on this computer (`trust-build`): the confirmation is
 * an HMAC, in `.caztor/build.seal`, with Caztor's private trust key, and any change to the file voids it. The step gets the engine's allowlisted environment, never API keys, and does not run in a
 * sandboxed compile: it is the project's own code, run as the host.
 */
export const RECIPE_FILE = ".caztor/build.json";
export const SEAL_FILE = ".caztor/build.seal";
export const RECIPE_TIME_LIMIT_MS = 120_000;
const SEAL_PREFIX = "hmac1:";
const MAX_OUTPUT_BYTES = 16 * 1024;

export interface BuildRecipe {
  when: RelPath[];
  before: string[];
  root: RelPath;
}

export interface BuildRecipeOptions {
  fs: FileSystem;
  spawner: ProcessSpawner;
  clock: Clock;
  /** Absolute path of the project folder. */
  root: string;
  /** The server's environment. Only the engine's allowlisted names reach the step. */
  parentEnv: Readonly<Record<string, string | undefined>>;
  /** Caztor's trust key (`createTrustKey`); null when it cannot be used, and then no recipe runs. */
  trustKey: () => Promise<Uint8Array | null>;
  timeoutMs?: number;
}

/** The confirmation of these exact recipe bytes in this project folder. */
export function sealOf(key: Uint8Array, root: string, recipe: Uint8Array): string {
  const digest = createHash("sha256").update(recipe).digest("hex");
  return SEAL_PREFIX + createHmac("sha256", key).update(`caztor-build-recipe\0${root}\0${digest}`).digest("base64url");
}

/** Whether `.caztor`, the recipe and its seal are plain entries of the project, never links that could lead elsewhere. */
async function plainRecipePaths(fs: FileSystem, root: string): Promise<boolean> {
  const folder = await fs.lstat(`${root}/.caztor`).catch(() => null);
  if (folder === null || folder.isSymbolicLink() || !folder.isDirectory()) return false;
  for (const file of [RECIPE_FILE, SEAL_FILE]) {
    const stats = await fs.lstat(`${root}/${file}`).catch(() => null);
    if (stats !== null && (stats.isSymbolicLink() || !stats.isFile())) return false;
  }
  return true;
}

/** `trust-build`: checks the recipe and records the host's confirmation of it. Returns the recipe confirmed. */
export async function confirmRecipe(options: { fs: FileSystem; root: string; trustKey: () => Promise<Uint8Array | null> }): Promise<{ ok: true; recipe: BuildRecipe } | { ok: false; message: string }> {
  if (!(await plainRecipePaths(options.fs, options.root))) return { ok: false, message: `.caztor, ${RECIPE_FILE} and ${SEAL_FILE} must be plain files and folders of the project, not links.` };
  let bytes: Uint8Array;
  try {
    bytes = await options.fs.readFile(`${options.root}/${RECIPE_FILE}`);
  } catch {
    return { ok: false, message: `There is no ${RECIPE_FILE} in ${options.root}.` };
  }
  const parsed = parseRecipe(new TextDecoder().decode(bytes));
  if (!parsed.ok) return { ok: false, message: `${RECIPE_FILE} is not valid: ${parsed.message}.` };
  const key = await options.trustKey();
  if (key === null) return { ok: false, message: "Caztor's trust key cannot be used (see ~/.config/caztor/trust.key), so the confirmation cannot be kept." };
  await options.fs.writeFile(`${options.root}/${SEAL_FILE}`, new TextEncoder().encode(sealOf(key, options.root, bytes)));
  return { ok: true, recipe: parsed.recipe };
}

type Parsed = { ok: true; recipe: BuildRecipe } | { ok: false; message: string };

export function parseRecipe(text: string): Parsed {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, message: "it is not valid JSON" };
  }
  if (typeof value !== "object" || value === null) return { ok: false, message: "it must be an object" };
  const { when, before, root } = value as Record<string, unknown>;
  if (!Array.isArray(when) || when.length === 0 || !when.every((item) => typeof item === "string")) return { ok: false, message: '"when" must list the files it applies to' };
  if (!Array.isArray(before) || before.length === 0 || !before.every((item) => typeof item === "string" && item !== "")) return { ok: false, message: '"before" must be a command as a list of arguments, for example ["python3", "build.py"]' };
  if (typeof root !== "string") return { ok: false, message: '"root" must be the file to compile' };
  const paths: RelPath[] = [];
  for (const path of [...(when as string[]), root]) {
    const parsed = parseRelPath(path);
    if (!parsed.ok) return { ok: false, message: `"${path}" is not a path inside the project` };
    paths.push(parsed.value);
  }
  return { ok: true, recipe: { when: paths.slice(0, -1), before: before as string[], root: paths[paths.length - 1]! } };
}

/** Wraps a compiler so that a project's build recipe runs before the files it names are compiled. */
export function withBuildRecipe(inner: CompilerPort, options: BuildRecipeOptions): CompilerPort {
  const { fs, spawner, clock, root } = options;
  const env = buildCompileEnv(options.parentEnv);
  const limit = options.timeoutMs ?? RECIPE_TIME_LIMIT_MS;

  async function load(): Promise<(Parsed & { bytes: Uint8Array }) | null> {
    const recipe = await fs.lstat(`${root}/${RECIPE_FILE}`).catch(() => null);
    if (recipe === null) return null;
    if (!(await plainRecipePaths(fs, root))) return { ok: false, message: "it, its seal or .caztor is a link", bytes: new Uint8Array() };
    let bytes: Uint8Array;
    try {
      bytes = await fs.readFile(`${root}/${RECIPE_FILE}`);
    } catch {
      return null;
    }
    return { ...parseRecipe(new TextDecoder().decode(bytes)), bytes };
  }

  async function confirmed(bytes: Uint8Array): Promise<boolean> {
    const key = await options.trustKey();
    if (key === null) return false;
    let stored: Uint8Array;
    try {
      stored = await fs.readFile(`${root}/${SEAL_FILE}`);
    } catch {
      return false;
    }
    const expected = new TextEncoder().encode(sealOf(key, root, bytes));
    const actual = new TextEncoder().encode(new TextDecoder().decode(stored).trim());
    return actual.length === expected.length && timingSafeEqual(actual, expected);
  }

  type StepOutcome = { status: "ok" } | { status: Exclude<CompileResult["status"], "success">; diagnostic?: Diagnostic };

  async function runStep(recipe: BuildRecipe, signal: AbortSignal): Promise<StepOutcome> {
    const [file, ...args] = recipe.before;
    const shown = recipe.before.join(" ");
    const child = spawner.spawn({ file: file!, args, cwd: root, env });
    let output = "";
    const collect = async (stream: AsyncIterable<Uint8Array>) => {
      const decoder = new TextDecoder();
      for await (const chunk of stream) {
        if (output.length < MAX_OUTPUT_BYTES) output += decoder.decode(chunk, { stream: true });
      }
    };
    let ended: "timed-out" | "cancelled" | null = null;
    const stop = (why: "timed-out" | "cancelled") => {
      ended ??= why;
      child.killGroup("SIGTERM");
      clock.setTimeout(() => child.killGroup("SIGKILL"), 2000);
    };
    const cancelTimer = clock.setTimeout(() => stop("timed-out"), limit);
    const onAbort = () => stop("cancelled");
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
    try {
      const [exit] = await Promise.all([child.exit, collect(child.stdout), collect(child.stderr)]);
      if (ended === "cancelled") return { status: "cancelled" };
      if (ended === "timed-out") return { status: "timed-out", diagnostic: problem(`The build step \`${shown}\` took longer than ${Math.round(limit / 1000)} s and was stopped.`, output) };
      if (exit.code !== 0) return { status: "failed", diagnostic: problem(`The build step \`${shown}\` from ${RECIPE_FILE} failed with exit code ${exit.code ?? exit.signal}.`, output) };
      return { status: "ok" };
    } catch (error) {
      return { status: "failed", diagnostic: problem(`The build step \`${shown}\` from ${RECIPE_FILE} could not start: ${error instanceof Error ? error.message : String(error)}.`) };
    } finally {
      cancelTimer();
      signal.removeEventListener("abort", onAbort);
    }
  }

  async function* compile(req: CompileRequest, signal: AbortSignal): AsyncGenerator<CompileEvent> {
    const loaded = await load();
    if (loaded === null || (loaded.ok && !loaded.recipe.when.includes(req.main))) {
      yield* inner.compile(req, signal);
      return;
    }
    const compileId = randomUUID();
    const startedAt = clock.now();
    const finish = (status: CompileResult["status"], diagnostic?: Diagnostic): CompileEvent => ({
      type: "finished",
      compileId,
      result: { status, pdfRev: null, diagnostics: diagnostic === undefined ? [] : [diagnostic], durationMs: clock.now() - startedAt, logAvailable: false },
    });
    if (!loaded.ok) {
      yield { type: "started", compileId };
      yield finish("failed", problem(`The build recipe ${RECIPE_FILE} is not valid: ${loaded.message}.`));
      return;
    }
    const { recipe } = loaded;
    if (!(await confirmed(loaded.bytes))) {
      yield { type: "started", compileId };
      yield finish("failed", problem(`${RECIPE_FILE} would run \`${recipe.before.join(" ")}\` before compiling ${req.main}, and it is not confirmed on this computer. Read it, then confirm it from the Caztor folder with: npm start -- trust-build "${root}"`));
      return;
    }
    if (req.sandboxed === true) {
      yield { type: "started", compileId };
      yield finish("failed", problem(`${RECIPE_FILE} runs a project command before compiling ${req.main}, which a sandboxed compile does not allow. Turn off "Sandboxed compile", or compile ${recipe.root} directly.`));
      return;
    }
    yield { type: "started", compileId };
    const step = await runStep(recipe, signal);
    if (step.status !== "ok") {
      yield finish(step.status, step.diagnostic);
      return;
    }
    // The inner compiler announces its own run; the step's id is not reused for it.
    for await (const event of inner.compile({ ...req, main: recipe.root }, signal)) {
      if (event.type === "started") continue;
      yield event.type === "finished" ? { ...event, compileId } : event;
    }
  }

  return { available: () => inner.available(), readArtifact: (kind) => inner.readArtifact(kind), compile };
}

function problem(message: string, output?: string): Diagnostic {
  const detail = output?.trim();
  return { severity: "error", file: null, line: null, message, ...(detail === undefined || detail === "" ? {} : { detail: detail.slice(-4000) }), source: "caztor" };
}
