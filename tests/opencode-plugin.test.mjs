// Node-gate tests for the generated OpenCode "refuse off-path push" plugin.
//
// These run under `node --test "tests/**/*.mjs"` and are deliberately NOT
// `test_*.py`, so `pytest tests/` never collects them.
//
// The plugin under test is the real generated artifact: a throwaway workspace is
// produced by the real `smith init`, and the plugin bytes are imported from
// `<workspace>/.opencode/plugins/refuse-offpath-push.js`. The workspace's
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
const PLUGIN_RELATIVE = ".opencode/plugins/refuse-offpath-push.js";
const HOOK_RELATIVE = "skills/remote-execution/scripts/hooks/refuse_offpath_push.py";
const ADAPTERS_RELATIVE = "skills/remote-execution/scripts/adapters";
const SURFACE_TOKEN = "zz_plugin_test_surface";

function makeTmp(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function generateWorkspace() {
  const destination = makeTmp("papersmith-plugin-");
  const consoleScript = path.join(REPO_ROOT, ".venv", "bin", "papersmith");
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
  const destination = makeTmp("papersmith-plugin-copy-");
  // `fs.cpSync` keeps the layout; node_modules may be large, so exclude it.
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (entry) => !entry.includes(`${path.sep}node_modules`),
  });
  return destination;
}

async function loadPlugin(root) {
  const url = pathToFileURL(path.join(root, PLUGIN_RELATIVE)).href;
  const module = await import(url);
  assert.equal(typeof module.server, "function", "the generated module must export `server`");
  return module.server({ directory: root, worktree: root });
}

function invoke(hooks, command) {
  return hooks["tool.execute.before"]({ tool: "bash" }, { args: { command } });
}

test("generated plugin is emitted and exposes the bash pre-execution hook", { skip: UNAVAILABLE }, async () => {
  const hooks = await loadPlugin(WORKSPACE);
  assert.equal(typeof hooks["tool.execute.before"], "function");
});

test("plugin allows a clean command", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE: tuple[str, ...] = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await invoke(hooks, "ls -la");
  await invoke(hooks, "echo hello");
});

test("plugin ignores non-bash tools and empty commands", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await hooks["tool.execute.before"]({ tool: "read" }, { args: { command: `x ${SURFACE_TOKEN}` } });
  await invoke(hooks, "");
  await invoke(hooks, undefined);
});

test("plugin THROWS on an off-path push and the message names the surface", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await assert.rejects(
    () => invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`),
    (error) => {
      assert.ok(error instanceof Error, "refusal must be a thrown Error, not a logged string");
      assert.match(error.message, new RegExp(SURFACE_TOKEN));
      assert.match(error.message, /refuse-offpath-push/);
      return true;
    },
  );
});

test("plugin allows the same surface when the command routes through remote_cli.py", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await invoke(hooks, `python3 remote_cli.py submit --note ${SURFACE_TOKEN}`);
});

test("plugin degrades loudly, once, and allows when the hook hangs past the timeout", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  // Keep the real hook's module (so the capability probe succeeds) but hang when
  // it is executed as a program, which is how the relay invokes it.
  const hookPath = path.join(root, HOOK_RELATIVE);
  const source = fs.readFileSync(hookPath, "utf8");
  const withoutMain = source.slice(0, source.indexOf("if __name__ == \"__main__\":"));
  fs.writeFileSync(hookPath, `${withoutMain}\nimport time\n\ntime.sleep(30)\n`, "utf8");

  const hooks = await loadPlugin(root);
  const errors = t.mock.method(console, "error", () => {});
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  assert.equal(errors.mock.callCount(), 1, "exactly one warning per process");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("plugin degrades loudly when a declared surface fails to load", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_broken.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\nraise RuntimeError("adapter cannot import")\n`,
  });
  const hooks = await loadPlugin(root);
  const errors = t.mock.method(console, "error", () => {});
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  assert.equal(errors.mock.callCount(), 1, "a non-empty-but-incomplete surface set must not pass");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("plugin exports an OpenCode v2 default definition with id, server, and setup()", { skip: UNAVAILABLE }, async () => {
  const url = pathToFileURL(path.join(WORKSPACE, PLUGIN_RELATIVE)).href;
  const module = await import(url);
  assert.equal(typeof module.default, "object", "OpenCode v2 requires a default export object");
  assert.notEqual(module.default, null);
  assert.equal(module.default.id, "papersmith.refuse-offpath-push");
  assert.equal(module.default.server, module.server);
  assert.equal(typeof module.default.setup, "function");
});

test("OpenCode v2 setup(ctx) registers execute.before hook, enforces the tripwire, and disposes cleanly", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const url = pathToFileURL(path.join(root, PLUGIN_RELATIVE)).href;
  const module = await import(url);

  let registeredStage = null;
  let registeredHandler = null;
  let disposed = false;

  const ctx = {
    location: { directory: root, worktree: root },
    tool: {
      hook: async (stage, handler) => {
        registeredStage = stage;
        registeredHandler = handler;
        return {
          dispose: async () => {
            disposed = true;
          },
        };
      },
    },
  };

  const cleanup = await module.default.setup(ctx);
  assert.equal(registeredStage, "execute.before");
  assert.equal(typeof registeredHandler, "function");

  // Clean bash command passes
  await registeredHandler({ tool: "bash", input: { command: "echo ok" } });

  // Non-bash tool is ignored even if input mentions the surface
  await registeredHandler({ tool: "read", input: { command: `x ${SURFACE_TOKEN}` } });

  // Off-path push throws
  await assert.rejects(
    () => registeredHandler({ tool: "bash", input: { command: `python3 zz_runner.py --call ${SURFACE_TOKEN}` } }),
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(error.message, new RegExp(SURFACE_TOKEN));
      assert.match(error.message, /refuse-offpath-push/);
      return true;
    },
  );

  // Route through remote_cli.py passes
  await registeredHandler({
    tool: "bash",
    input: { command: `python3 remote_cli.py submit --note ${SURFACE_TOKEN}` },
  });

  // Cleanup disposes the hook registration
  assert.equal(typeof cleanup, "function");
  await cleanup();
  assert.equal(disposed, true);
});
