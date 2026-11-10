// Node-gate tests for the generated Pi "refuse off-path push" extension.
//
// These run under `node --test "tests/**/*.mjs"` and are deliberately NOT
// `test_*.py`, so `pytest tests/` never collects them.
//
// The plugin under test is the real generated artifact: a throwaway workspace is
// produced by the real `smith init`, and the plugin bytes are imported from
// `<workspace>/.pi/extensions/refuse-offpath-push.js`. The workspace's
// adapters directory is then replaced with one trivially importable synthetic
// adapter so the surface set — and therefore every assertion — is deterministic
// and independent of whether the real kaggle adapter's optional dependency is
// importable in this environment.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PLUGIN_RELATIVE = ".pi/extensions/refuse-offpath-push.js";
const HOOK_RELATIVE = "skills/remote-execution/scripts/hooks/refuse_offpath_push.py";
const ADAPTERS_RELATIVE = "skills/remote-execution/scripts/adapters";
const SURFACE_TOKEN = "zz_plugin_test_surface";

function makeTmp(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function generateWorkspace() {
  const destination = makeTmp("papersmith-pi-ext-");
  const consoleScript = path.join(REPO_ROOT, ".venv", "bin", "smith");
  // `--no-env` keeps this offline-fast: `init` provisions a micromamba
  // environment by default, and a test that performed a multi-gigabyte
  // network install per run would leak it into the temp dir and make the
  // Node half depend on the network.
  // `--allow-dirty-kit`: the kit is this checkout, which may carry uncommitted
  // edits; without it `init` refuses and every test here would skip.
  const args = ["init", destination, "--remote", "local", "--no-npm", "--no-env", "--allow-dirty-kit"];
  let result;
  if (fs.existsSync(consoleScript)) {
    result = spawnSync(consoleScript, args, { cwd: REPO_ROOT, encoding: "utf8" });
  } else {
    const program = 'from papersmith.cli import main; raise SystemExit(main(' + JSON.stringify(args) + "))";
    result = spawnSync("python3", ["-c", program], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, "src") },
    });
  }
  if (result.error || result.status !== 0) {
    return null;
  }
  if (!fs.existsSync(path.join(destination, PLUGIN_RELATIVE))) {
    return null;
  }
  return destination;
}

//: Built once: the corpus generator is an environment precondition, not the
//: subject under test, so an absent interpreter skips rather than fails.
const WORKSPACE = generateWorkspace();
const UNAVAILABLE = WORKSPACE ? false : "smith init unavailable in this environment";

function plantAdapters(root, modules) {
  const directory = path.join(root, ADAPTERS_RELATIVE);
  fs.rmSync(directory, { recursive: true, force: true });
  fs.mkdirSync(directory, { recursive: true });
  for (const [name, body] of Object.entries(modules)) {
    fs.writeFileSync(path.join(directory, name), body, "utf8");
  }
}

function copyWorkspace(source) {
  const destination = makeTmp("papersmith-pi-ext-copy-");
  // `fs.cpSync` keeps the layout; node_modules may be large, so exclude it.
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (entry) => !entry.includes(`${path.sep}node_modules`),
  });
  return destination;
}

async function loadExtension(root) {
  const url = pathToFileURL(path.join(root, PLUGIN_RELATIVE)).href;
  const module = await import(url);
  assert.equal(typeof module.default, "function", "the extension must default-export a factory");
  const handlers = {};
  module.default({ on: (name, handler) => { handlers[name] = handler; } });
  assert.equal(typeof handlers.tool_call, "function", "the factory must register a tool_call handler");
  return handlers.tool_call;
}

function bash(command) {
  return { toolName: "bash", toolCallId: "t1", input: { command } };
}

function plantSurface(root) {
  plantAdapters(root, { "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n` });
}

test("extension registers a tool_call handler and allows a clean bash call", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  assert.equal(await handler(bash("ls -la")), undefined);
  assert.equal(await handler(bash("echo hello")), undefined);
});

test("extension ignores non-bash tools and empty or malformed events", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  assert.equal(await handler({ toolName: "read", input: { command: `x ${SURFACE_TOKEN}` } }), undefined);
  assert.equal(await handler(bash("")), undefined);
  assert.equal(await handler({ toolName: "bash", input: { command: 42 } }), undefined);
  assert.equal(await handler({ toolName: "bash", input: null }), undefined);
  assert.equal(await handler({ toolName: "bash" }), undefined);
  assert.equal(await handler(null), undefined);
  assert.equal(await handler(undefined), undefined);
});

test("extension BLOCKS an off-path push with a reason naming the surface", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  const result = await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`));
  assert.equal(result.block, true);
  assert.match(result.reason, new RegExp(SURFACE_TOKEN));
  assert.match(result.reason, /refuse-offpath-push/);
});

test("extension allows the same surface when the command routes through remote_cli.py", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  assert.equal(await handler(bash(`python3 remote_cli.py submit --note ${SURFACE_TOKEN}`)), undefined);
});

test("extension anchors on its own file, not the process cwd", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  const elsewhere = makeTmp("papersmith-pi-ext-cwd-");
  const previous = process.cwd();
  process.chdir(elsewhere);
  try {
    const result = await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`));
    assert.equal(result.block, true);
  } finally {
    process.chdir(previous);
  }
});

test("extension fails open, loudly and once, when the guard is missing", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  fs.rmSync(path.join(root, HOOK_RELATIVE));
  const handler = await loadExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1, "exactly one warning per process");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("extension fails open when python cannot be spawned", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  const saved = { PATH: process.env.PATH, VIRTUAL_ENV: process.env.VIRTUAL_ENV };
  fs.rmSync(path.join(root, ".venv"), { recursive: true, force: true });
  process.env.PATH = path.join(root, "no-such-bin");
  delete process.env.VIRTUAL_ENV;
  try {
    assert.equal(await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  } finally {
    process.env.PATH = saved.PATH;
    if (saved.VIRTUAL_ENV !== undefined) process.env.VIRTUAL_ENV = saved.VIRTUAL_ENV;
  }
  assert.equal(errors.mock.callCount(), 1);
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("extension fails open when the guard hangs past the timeout", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const hookPath = path.join(root, HOOK_RELATIVE);
  const source = fs.readFileSync(hookPath, "utf8");
  const withoutMain = source.slice(0, source.indexOf("if __name__ == \"__main__\":"));
  fs.writeFileSync(hookPath, `${withoutMain}\nimport time\n\ntime.sleep(30)\n`, "utf8");
  const handler = await loadExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1);
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("extension fails open when a declared surface fails to load", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_broken.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\nraise RuntimeError("adapter cannot import")\n`,
  });
  const handler = await loadExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await handler(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1);
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("extension never throws: an unexpected exception degrades to allow", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantSurface(root);
  const handler = await loadExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  const hostile = { toolName: "bash", get input() { throw new Error("boom"); } };
  assert.equal(await handler(hostile), undefined);
  assert.equal(errors.mock.callCount(), 1);
});
