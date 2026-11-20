import { parseRelPath } from "@caztor/core";
import type { CompileRequest } from "@caztor/core";

export const BUILD_DIR = ".caztor/build";
/** Where the engine writes. Only this folder is ever cleared before a run. */
export const OUT_DIR = `${BUILD_DIR}/out`;
/** The last PDF a run produced; it stays available when a later run produces none. */
export const PREVIEW_PDF = `${BUILD_DIR}/preview.pdf`;
export const LAST_LOG = `${BUILD_DIR}/last-compile.log`;

/**
 * The only variables the engine inherits. `PATH` finds the binary; `HOME`, `XDG_CACHE_HOME` and
 * `TECTONIC_CACHE_DIR` locate the support-file cache; `TMPDIR` its scratch space; the proxy variables let a
 * first-run download pass through a proxy. Everything else, API keys included, stays out of the child.
 */
export const COMPILE_ENV_ALLOWLIST: readonly string[] = [
  "PATH",
  "HOME",
  "XDG_CACHE_HOME",
  "TECTONIC_CACHE_DIR",
  "TMPDIR",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "ALL_PROXY",
  "NO_PROXY",
  "http_proxy",
  "https_proxy",
  "all_proxy",
  "no_proxy",
];

export function buildCompileEnv(parent: Readonly<Record<string, string | undefined>>): Record<string, string> {
  const env: Record<string, string> = {};
  for (const name of COMPILE_ENV_ALLOWLIST) {
    const value = parent[name];
    if (value !== undefined) env[name] = value;
  }
  env["TECTONIC_UNTRUSTED_MODE"] = "1";
  return env;
}

/**
 * The argument list after the binary name. Shell escape is never enabled and `--synctex` is not passed.
 * The main file is validated again here and placed as `./path`, so no project path can be read as an option.
 */
export function buildCompileArgs(req: CompileRequest): string[] {
  const parsed = parseRelPath(req.main);
  if (!parsed.ok || parsed.value !== req.main) {
    throw new Error(`The main file "${req.main}" is not a valid project path.`);
  }
  const args = ["-X", "compile", `./${req.main}`, "--outdir", OUT_DIR, "--keep-logs", "--untrusted"];
  if (!req.stopOnFirstError) args.push("-Z", "continue-on-errors");
  return args;
}
