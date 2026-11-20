import { readdirSync, readFileSync, statSync } from "node:fs";
import { builtinModules } from "node:module";
import { join, relative, sep } from "node:path";

export interface ForbiddenImport {
  file: string;
  specifier: string;
}

const builtins = new Set(builtinModules.filter((name) => !name.startsWith("_")));

// Matches `from "x"`, side-effect `import "x"`, dynamic `import("x")` and `require("x")`.
const SPECIFIER = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;

function isForbidden(specifier: string): boolean {
  if (specifier.startsWith("node:")) return true;
  const root = specifier.split("/")[0] ?? specifier;
  return builtins.has(specifier) || builtins.has(root);
}

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (/\.(ts|tsx|mts|js|mjs)$/.test(name)) yield full;
  }
}

/** Lists every import of a Node built-in found in the sources under `dir`. */
export function findForbiddenImports(dir: string): ForbiddenImport[] {
  const found: ForbiddenImport[] = [];
  for (const file of walk(dir)) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(SPECIFIER)) {
      const specifier = match[1];
      if (specifier !== undefined && isForbidden(specifier)) {
        found.push({ file: relative(dir, file).split(sep).join("/"), specifier });
      }
    }
  }
  return found;
}
