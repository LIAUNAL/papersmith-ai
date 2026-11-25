// Third-party notices for a bundle: each npm package whose code the bundle includes, with its version, its declared
// licence and the full text of its licence file. The server bundle (scripts/bundle-server.mjs) writes them beside
// apps/server-local/dist/main.mjs; the web app's come from Vite's `build.license` (apps/web/vite.config.ts), in the
// same format. PaperSmith ships both in its wheel.
import { existsSync, readdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, join, sep } from "node:path";

const LICENSE_FILE = [/^license/i, /^licence/i, /^copying/i];

/** The nearest folder above `file` holding a package.json with a name: the package the module belongs to. */
function packageOf(file, cache) {
  for (let dir = dirname(file); dir !== dirname(dir); dir = dirname(dir)) {
    if (cache.has(dir)) return cache.get(dir);
    const manifest = join(dir, "package.json");
    if (existsSync(manifest)) {
      const data = JSON.parse(readFileSync(manifest, "utf-8"));
      // A nested package.json without a name (`{"type": "module"}` in a dist folder) is not the package.
      if (typeof data.name === "string") {
        const found = { dir, data };
        cache.set(dir, found);
        return found;
      }
    }
  }
  return undefined;
}

/** The packages under node_modules that `moduleIds` come from, sorted by name and version. */
export function collectNotices(moduleIds) {
  const cache = new Map();
  const notices = new Map();
  for (const id of moduleIds) {
    if (id.startsWith("\0") || !existsSync(id)) continue;
    // A workspace package is linked into node_modules; its real path is Caztor's own source, not a dependency.
    const file = realpathSync(id);
    if (!file.split(sep).includes("node_modules")) continue;
    const pkg = packageOf(file, cache);
    if (pkg === undefined) continue;
    const { name, version = "0.0.0", license } = pkg.data;
    const key = `${name}@${version}`;
    if (notices.has(key)) continue;
    const licenseFile = readdirSync(pkg.dir).find((entry) => LICENSE_FILE.some((re) => re.test(entry)));
    notices.set(key, {
      name,
      version,
      identifier: typeof license === "string" ? license.trim() : undefined,
      text: licenseFile === undefined ? undefined : readFileSync(join(pkg.dir, licenseFile), "utf-8").trim(),
    });
  }
  return [...notices.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, notice]) => notice);
}

/** The notices as Markdown: one section per package, its licence text below its name. */
export function noticesMarkdown(notices, what) {
  if (notices.length === 0) return `# Licenses\n\n${what} does not bundle any dependencies with licenses.\n`;
  let text = `# Licenses\n\n${what} bundles dependencies which contain the following licenses:\n`;
  for (const notice of notices) {
    text += `\n## ${notice.name} - ${notice.version}${notice.identifier ? ` (${notice.identifier})` : ""}\n`;
    text += notice.text ? `\n${notice.text}\n` : "\nNo license file is shipped with this package.\n";
  }
  return text;
}

/** Writes the notices for `moduleIds` to `file` and returns them. */
export function writeNotices(moduleIds, file, what) {
  const notices = collectNotices(moduleIds);
  writeFileSync(file, noticesMarkdown(notices, what));
  return notices;
}
