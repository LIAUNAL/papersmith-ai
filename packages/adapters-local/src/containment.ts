import { isSecretPath, parseRelPath, RESERVED_ROOTS } from "@caztor/core";
import type { Result, StoreError } from "@caztor/core";
import type { FileSystem } from "./infra.ts";

export type FailureCode = Exclude<StoreError["code"], "conflict">;
export type Failure = { ok: false; error: StoreError };

export function failure(code: FailureCode, path: string): Failure {
  return { ok: false, error: { code, path } };
}

export function codeOf(error: unknown): string | undefined {
  return (error as { code?: string } | null)?.code;
}

/** Maps a Node-style file system failure onto the store's error codes. */
export function codeFromFsError(error: unknown): FailureCode {
  switch (codeOf(error)) {
    case "ENOENT":
      return "not_found";
    case "EEXIST":
      return "exists";
    case "ENOTDIR":
    case "EISDIR":
    case "ERR_FS_EISDIR":
    case "ELOOP":
    case "ENXIO":
      return "invalid_path";
    default:
      return "io";
  }
}

export function fromFsError(error: unknown, path: string): Failure {
  return failure(codeFromFsError(error), path);
}

export function dirname(path: string): string {
  const index = path.lastIndexOf("/");
  return index <= 0 ? "/" : path.slice(0, index);
}

export function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

export function joinPath(base: string, name: string): string {
  return base === "/" ? `/${name}` : `${base}/${name}`;
}

/** Real path of the deepest existing ancestor of `path`, followed by the names that do not exist yet. */
async function resolveDeep(fs: FileSystem, path: string): Promise<Result<string, FailureCode>> {
  const missing: string[] = [];
  let candidate = path;
  for (;;) {
    try {
      const real = await fs.realpath(candidate);
      return { ok: true, value: missing.reduce(joinPath, real) };
    } catch (error) {
      const code = codeOf(error);
      if (code === "ENOENT") {
        // A link whose target does not exist cannot be shown to stay inside the root.
        const dangling = await fs.lstat(candidate).then(
          () => true,
          () => false,
        );
        if (dangling) return { ok: false, error: "outside_root" };
        if (candidate === "/") return { ok: false, error: "io" };
        missing.unshift(basename(candidate));
        candidate = dirname(candidate);
      } else {
        return { ok: false, error: codeFromFsError(error) };
      }
    }
  }
}

export interface LocatorOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  /** Validates the project-relative path before any disk access. Defaults to `parseRelPath`. */
  parse?: (input: string) => Result<string, StoreError>;
  /** Top-level folders that are refused after resolution. Defaults to the reserved roots. */
  reservedRoots?: readonly string[];
  /** A path with a segment starting like this is refused as `hidden` (the store's temporary files). */
  hiddenSegmentPrefix?: string;
}

/**
 * Turns a project-relative path into its real location inside the project, or a typed refusal. The path is
 * validated, then resolved with `realpath` (links included); a location whose real path leaves the root or enters a
 * reserved folder is refused. With `followFinal: false` a final link is not resolved, so rename and remove act on the
 * link itself.
 */
export function createLocator(options: LocatorOptions) {
  const { fs, root } = options;
  const parse = options.parse ?? parseRelPath;
  const reserved: readonly string[] = options.reservedRoots ?? RESERVED_ROOTS;

  return async function locate(input: string, followFinal = true): Promise<Result<string, StoreError>> {
    const parsed = parse(input);
    if (!parsed.ok) return parsed;
    const prefix = options.hiddenSegmentPrefix;
    if (prefix !== undefined && parsed.value.split("/").some((segment) => segment.startsWith(prefix))) {
      return failure("hidden", input);
    }
    let rootReal: string;
    try {
      rootReal = await fs.realpath(root);
    } catch {
      return failure("io", input);
    }
    const full = joinPath(rootReal, parsed.value);
    const resolved = await resolveDeep(fs, followFinal ? full : dirname(full));
    if (!resolved.ok) return failure(resolved.error, input);
    const real = followFinal ? resolved.value : joinPath(resolved.value, basename(full));
    if (real !== rootReal && !real.startsWith(`${rootReal}/`)) return failure("outside_root", input);
    const relative = real.slice(rootReal.length + 1);
    const first = relative.split("/")[0] ?? "";
    if (reserved.includes(first.toLowerCase())) return failure("hidden", input);
    // Checked on the real path too, so a link cannot lead into it. Callers that name their own roots are outside the file API.
    if (options.reservedRoots === undefined && isSecretPath(relative)) return failure("hidden", input);
    return { ok: true, value: real };
  };
}
