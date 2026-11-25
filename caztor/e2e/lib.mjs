// Helpers shared by the opt-in browser checks. Nothing here is machine specific: Playwright is found through
// the CAZTOR_PLAYWRIGHT environment variable (the path of its `index.mjs`, or of the package folder).
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export async function loadPlaywright() {
  const location = process.env.CAZTOR_PLAYWRIGHT;
  if (!location) throw new Error("Set CAZTOR_PLAYWRIGHT to the path of playwright/index.mjs (see e2e/README.md).");
  const entry = location.endsWith(".mjs") || location.endsWith(".js") ? location : join(location, "index.mjs");
  return import(pathToFileURL(entry).href);
}

/** A temporary project holding the given files. */
export function makeProject(files) {
  const dir = mkdtempSync(join(tmpdir(), "caztor-e2e-"));
  for (const [name, text] of Object.entries(files)) writeFileSync(join(dir, name), text);
  return dir;
}

/** Starts the local server (the web app must be built) and resolves with its address and a function that stops it. */
export function startServer(projectDir, { entry = "apps/server-local/src/main.ts", env = {} } = {}) {
  const child = spawn(process.execPath, [entry, projectDir], { cwd: repo, env: { ...process.env, ...env }, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolveStart, reject) => {
    let output = "";
    const timer = setTimeout(() => reject(new Error(`The server did not start: ${output}`)), 15000);
    const onData = (chunk) => {
      output += chunk;
      const match = /http:\/\/127\.0\.0\.1:\d+/.exec(output);
      if (match === null) return;
      clearTimeout(timer);
      resolveStart({
        url: match[0],
        pid: child.pid,
        stop: () =>
          new Promise((done) => {
            child.once("exit", () => done());
            child.kill("SIGTERM");
          }),
      });
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.once("exit", (code) => reject(new Error(`The server exited with ${code}: ${output}`)));
  });
}

/** Opens the app, collects console errors, and acknowledges the first-use notice when it shows. */
export async function openApp(browser, url, viewport = { width: 1440, height: 900 }, colorScheme = "light") {
  const page = await browser.newPage({ viewport, colorScheme });
  const problems = [];
  page.on("console", (message) => message.type() === "error" && problems.push(`console: ${message.text()}`));
  page.on("pageerror", (error) => problems.push(`pageerror: ${error}`));
  await page.goto(url, { waitUntil: "load" });
  const notice = page.getByRole("dialog", { name: "Before you start" });
  await notice.waitFor({ timeout: 5000 }).catch(() => {});
  if ((await notice.count()) > 0) await notice.getByRole("button", { name: "I understand" }).click();
  await notice.waitFor({ state: "detached", timeout: 5000 }).catch(() => {});
  return { page, problems };
}
