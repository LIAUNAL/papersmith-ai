import type { spawn as nodeSpawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdirSync, mkdtempSync, renameSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough } from "node:stream";
import { afterEach, describe, expect, it } from "vitest";
import type { SpawnSpec } from "../src/infra.ts";
import { createNodeSpawner, nodeDirectoryWatcher, nodeFileSystem, systemClock } from "../src/node-infra.ts";

type SpawnImpl = typeof nodeSpawn;

class StubChild extends EventEmitter {
  pid = 4242;
  stdin = new PassThrough();
  stdout = new PassThrough();
  stderr = new PassThrough();
  stdinText = "";
  constructor() {
    super();
    this.stdin.on("data", (chunk: Buffer) => (this.stdinText += chunk.toString()));
  }
}

function harness() {
  const child = new StubChild();
  const calls: { file: string; args: readonly string[]; options: Record<string, unknown> }[] = [];
  const kills: { pid: number; signal: string }[] = [];
  const spawnImpl = ((file: string, args: readonly string[], options: Record<string, unknown>) => {
    calls.push({ file, args, options });
    return child;
  }) as unknown as SpawnImpl;
  const kill = (pid: number, signal: NodeJS.Signals | number) => {
    kills.push({ pid, signal: String(signal) });
  };
  return { child, calls, kills, spawner: createNodeSpawner({ spawn: spawnImpl, kill }) };
}

const spec: SpawnSpec = {
  file: "tectonic",
  args: ["-X", "compile", "main.tex", "; rm -rf ~"],
  cwd: "/project",
  env: { PATH: "/usr/bin", LANG: "C" },
};

describe("createNodeSpawner launch options", () => {
  it("never uses a shell, detaches into its own group and passes argv untouched", () => {
    const { spawner, calls } = harness();
    spawner.spawn(spec);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.file).toBe("tectonic");
    expect(calls[0]?.args).toEqual(["-X", "compile", "main.tex", "; rm -rf ~"]);
    expect(calls[0]?.options).toMatchObject({ shell: false, detached: true, cwd: "/project" });
  });

  it("passes exactly the allowlisted environment and nothing inherited from the server", () => {
    const previous = process.env["CAZTOR_TEST_SECRET"];
    process.env["CAZTOR_TEST_SECRET"] = "leak";
    try {
      const { spawner, calls } = harness();
      spawner.spawn(spec);
      expect(calls[0]?.options["env"]).toEqual({ PATH: "/usr/bin", LANG: "C" });
    } finally {
      if (previous === undefined) delete process.env["CAZTOR_TEST_SECRET"];
      else process.env["CAZTOR_TEST_SECRET"] = previous;
    }
  });

  it("writes stdin text and closes the pipe, or just closes it when there is none", async () => {
    const withStdin = harness();
    withStdin.spawner.spawn({ ...spec, stdin: "--not a flag; echo hi" });
    await new Promise((resolve) => setImmediate(resolve));
    expect(withStdin.child.stdinText).toBe("--not a flag; echo hi");
    expect(withStdin.child.stdin.writableEnded).toBe(true);

    const without = harness();
    without.spawner.spawn(spec);
    expect(without.child.stdin.writableEnded).toBe(true);
    expect(without.child.stdinText).toBe("");
  });
});

describe("an interactive child", () => {
  it("keeps stdin open and writes each line as it is sent, and never for a child that is not interactive", async () => {
    const open = harness();
    const handle = open.spawner.spawn({ ...spec, interactive: true });
    expect(open.child.stdin.writableEnded).toBe(false);
    handle.write?.("CODE-1234\n");
    await new Promise((resolve) => setImmediate(resolve));
    expect(open.child.stdinText).toBe("CODE-1234\n");

    const closed = harness();
    closed.spawner.spawn(spec).write?.("ignored\n");
    await new Promise((resolve) => setImmediate(resolve));
    expect(closed.child.stdinText).toBe("");
  });
});

describe("createNodeSpawner child handle", () => {
  it("exposes the output streams as async iterables of bytes", async () => {
    const { spawner, child } = harness();
    const handle = spawner.spawn(spec);
    child.stdout.write("out-1");
    child.stdout.end("out-2");
    child.stderr.end("err");

    const read = async (stream: AsyncIterable<Uint8Array>) => {
      const decoder = new TextDecoder();
      let text = "";
      for await (const chunk of stream) text += decoder.decode(chunk, { stream: true });
      return text;
    };
    expect(await read(handle.stdout)).toBe("out-1out-2");
    expect(await read(handle.stderr)).toBe("err");
  });

  it("resolves exit with the code and signal once the process closes", async () => {
    const exited = harness();
    const first = exited.spawner.spawn(spec);
    exited.child.emit("close", 3, null);
    expect(await first.exit).toEqual({ code: 3, signal: null });

    const killed = harness();
    const second = killed.spawner.spawn(spec);
    killed.child.emit("close", null, "SIGTERM");
    expect(await second.exit).toEqual({ code: null, signal: "SIGTERM" });
  });

  it("rejects exit when the process cannot be started", async () => {
    const { spawner, child } = harness();
    const handle = spawner.spawn(spec);
    child.emit("error", Object.assign(new Error("spawn tectonic ENOENT"), { code: "ENOENT" }));
    await expect(handle.exit).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("signals the whole process group by negating the pid", () => {
    const { spawner, kills } = harness();
    const handle = spawner.spawn(spec);
    handle.killGroup("SIGTERM");
    handle.killGroup("SIGKILL");
    expect(kills).toEqual([
      { pid: -4242, signal: "SIGTERM" },
      { pid: -4242, signal: "SIGKILL" },
    ]);
  });

  it("ignores a group that is already gone but surfaces other failures", () => {
    const child = new StubChild();
    const spawnImpl = (() => child) as unknown as SpawnImpl;
    const gone = createNodeSpawner({
      spawn: spawnImpl,
      kill: () => {
        throw Object.assign(new Error("no such process"), { code: "ESRCH" });
      },
    });
    expect(() => gone.spawn(spec).killGroup("SIGTERM")).not.toThrow();

    const denied = createNodeSpawner({
      spawn: spawnImpl,
      kill: () => {
        throw Object.assign(new Error("not permitted"), { code: "EPERM" });
      },
    });
    expect(() => denied.spawn(spec).killGroup("SIGTERM")).toThrow("not permitted");
  });
});

describe("createNodeSpawner failure containment", () => {
  it("turns a synchronous spawn throw into a rejecting exit with empty output", async () => {
    const throwing = createNodeSpawner({
      spawn: (() => {
        throw Object.assign(new TypeError("The argument 'args[0]' must be a string without null bytes"), {
          code: "ERR_INVALID_ARG_VALUE",
        });
      }) as unknown as SpawnImpl,
    });

    const handle = throwing.spawn(spec);
    await expect(handle.exit).rejects.toMatchObject({ code: "ERR_INVALID_ARG_VALUE" });
    const drain = async (stream: AsyncIterable<Uint8Array>) => {
      const chunks: Uint8Array[] = [];
      for await (const chunk of stream) chunks.push(chunk);
      return chunks;
    };
    expect(await drain(handle.stdout)).toEqual([]);
    expect(await drain(handle.stderr)).toEqual([]);
    expect(() => handle.killGroup("SIGKILL")).not.toThrow();
  });

  it("rejects a NUL byte in the arguments without spawning anything", async () => {
    const handle = createNodeSpawner().spawn({ file: process.execPath, args: ["-e", "a\0b"], cwd: tmpdir(), env: {} });
    await expect(handle.exit).rejects.toMatchObject({ code: "ERR_INVALID_ARG_VALUE" });
  });

  it("rejects exit for a binary that does not exist", async () => {
    const handle = createNodeSpawner().spawn({
      file: join(tmpdir(), "caztor-no-such-binary"),
      args: [],
      cwd: tmpdir(),
      env: {},
    });
    await expect(handle.exit).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not signal the process group once the child has exited", () => {
    const exited = harness();
    const first = exited.spawner.spawn(spec);
    exited.child.emit("exit", 0, null);
    first.killGroup("SIGKILL");
    expect(exited.kills).toEqual([]);

    const closed = harness();
    const second = closed.spawner.spawn(spec);
    closed.child.emit("close", 0, null);
    second.killGroup("SIGTERM");
    expect(closed.kills).toEqual([]);

    const running = harness();
    running.spawner.spawn(spec).killGroup("SIGTERM");
    expect(running.kills).toEqual([{ pid: -4242, signal: "SIGTERM" }]);
  });
});

describe("systemClock", () => {
  it("reports wall-clock time and fires or cancels timers", async () => {
    expect(Math.abs(systemClock.now() - Date.now())).toBeLessThan(50);

    const fired: string[] = [];
    systemClock.setTimeout(() => fired.push("kept"), 5);
    const cancel = systemClock.setTimeout(() => fired.push("cancelled"), 5);
    cancel();
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(fired).toEqual(["kept"]);
  });
});

describe("nodeFileSystem", () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });
  const temp = () => {
    const dir = mkdtempSync(join(tmpdir(), "caztor-fs-"));
    dirs.push(dir);
    return dir;
  };

  it("round-trips bytes, enforces exclusive writes and lists entry kinds", async () => {
    const root = temp();
    await nodeFileSystem.mkdir(join(root, "sub", "deep"), { recursive: true });
    await nodeFileSystem.writeFile(join(root, "a.tex"), new TextEncoder().encode("hello"));

    expect(new TextDecoder().decode(await nodeFileSystem.readFile(join(root, "a.tex")))).toBe("hello");
    expect((await nodeFileSystem.stat(join(root, "a.tex"))).size).toBe(5);
    await expect(
      nodeFileSystem.writeFile(join(root, "a.tex"), new Uint8Array(), { exclusive: true }),
    ).rejects.toMatchObject({ code: "EEXIST" });
    await expect(nodeFileSystem.readFile(join(root, "missing"))).rejects.toMatchObject({ code: "ENOENT" });

    const kinds = (await nodeFileSystem.readdir(root)).map((e) => `${e.name}:${e.isDirectory() ? "dir" : "file"}`).sort();
    expect(kinds).toEqual(["a.tex:file", "sub:dir"]);
  });

  it("reads a range of bytes, shorter at the end of the file, and tells a replaced folder from the old one", async () => {
    const root = temp();
    await nodeFileSystem.writeFile(join(root, "a.log"), new TextEncoder().encode("0123456789"));
    expect(new TextDecoder().decode(await nodeFileSystem.readRange(join(root, "a.log"), 3, 4))).toBe("3456");
    expect(new TextDecoder().decode(await nodeFileSystem.readRange(join(root, "a.log"), 8, 10))).toBe("89");
    await expect(nodeFileSystem.readRange(join(root, "missing"), 0, 1)).rejects.toMatchObject({ code: "ENOENT" });

    await nodeFileSystem.mkdir(join(root, "d"));
    const first = (await nodeFileSystem.stat(join(root, "d"))).id;
    expect((await nodeFileSystem.stat(join(root, "d"))).id).toBe(first);
    await nodeFileSystem.rm(join(root, "d"), { recursive: true });
    await nodeFileSystem.mkdir(join(root, "e"));
    await nodeFileSystem.mkdir(join(root, "d"));
    expect((await nodeFileSystem.stat(join(root, "d"))).id).not.toBe(first);
  });

  it("renames, copies and removes recursively", async () => {
    const root = temp();
    await nodeFileSystem.mkdir(join(root, "d"));
    await nodeFileSystem.writeFile(join(root, "d", "a.tex"), new TextEncoder().encode("x"));
    await nodeFileSystem.rename(join(root, "d"), join(root, "e"));
    await nodeFileSystem.copyFile(join(root, "e", "a.tex"), join(root, "copy.tex"));
    expect(new TextDecoder().decode(await nodeFileSystem.readFile(join(root, "copy.tex")))).toBe("x");

    await nodeFileSystem.rm(join(root, "e"), { recursive: true });
    await expect(nodeFileSystem.stat(join(root, "e"))).rejects.toMatchObject({ code: "ENOENT" });
    await expect(nodeFileSystem.rm(join(root, "e"))).rejects.toMatchObject({ code: "ENOENT" });
    await expect(nodeFileSystem.rm(join(root, "e"), { force: true })).resolves.toBeUndefined();
  });

  it("resolves links with realpath and tells lstat apart from stat", async () => {
    const root = temp();
    const outside = temp();
    await nodeFileSystem.writeFile(join(outside, "secret.txt"), new TextEncoder().encode("s"));
    symlinkSync(outside, join(root, "escape"));

    expect(await nodeFileSystem.realpath(join(root, "escape", "secret.txt"))).toBe(join(await nodeFileSystem.realpath(outside), "secret.txt"));
    expect((await nodeFileSystem.lstat(join(root, "escape"))).isSymbolicLink()).toBe(true);
    expect((await nodeFileSystem.stat(join(root, "escape"))).isDirectory()).toBe(true);
  });
});

const watchDirs: string[] = [];
afterEach(() => {
  for (const dir of watchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("nodeDirectoryWatcher", () => {
  it("can be closed more than once", () => {
    const root = mkdtempSync(join(tmpdir(), "caztor-watch-"));
    watchDirs.push(root);
    const close = nodeDirectoryWatcher.watch(root, () => {}, () => {});
    expect(() => {
      close();
      close();
    }).not.toThrow();
  });
});

describe.skipIf(process.env["CAZTOR_REAL_BIN"] !== "1")("real process harness (opt-in)", () => {
  const spawner = createNodeSpawner();
  const env = { PATH: process.env["PATH"] ?? "" };

  it("runs node -e '' and reports a clean exit", async () => {
    const child = spawner.spawn({ file: process.execPath, args: ["-e", ""], cwd: tmpdir(), env });
    expect(await child.exit).toEqual({ code: 0, signal: null });
  });

  it("gives the child only the allowlisted environment", async () => {
    process.env["CAZTOR_TEST_SECRET"] = "leak";
    const child = spawner.spawn({
      file: process.execPath,
      args: ["-e", "process.stdout.write(Object.keys(process.env).includes('CAZTOR_TEST_SECRET') ? 'LEAK' : 'CLEAN')"],
      cwd: tmpdir(),
      env,
    });
    let out = "";
    for await (const chunk of child.stdout) out += new TextDecoder().decode(chunk);
    delete process.env["CAZTOR_TEST_SECRET"];
    expect(out).toBe("CLEAN");
  });

  it("kills a hung child through its process group", async () => {
    const child = spawner.spawn({
      file: process.execPath,
      args: ["-e", "setInterval(() => {}, 1000)"],
      cwd: tmpdir(),
      env,
    });
    child.killGroup("SIGTERM");
    expect(await child.exit).toEqual({ code: null, signal: "SIGTERM" });
  });

  it("reports nested file changes from a recursive watch and stops after close", async () => {
    const root = mkdtempSync(join(tmpdir(), "caztor-watch-"));
    watchDirs.push(root);
    mkdirSync(join(root, "chapters"));
    const seen: Array<string | null> = [];
    const close = nodeDirectoryWatcher.watch(root, (path) => seen.push(path), () => {});
    writeFileSync(join(root, "chapters", "intro.tex"), "x");
    const until = Date.now() + 3000;
    while (!seen.some((path) => path !== null && path.endsWith("intro.tex")) && Date.now() < until) await new Promise((r) => setTimeout(r, 50));
    expect(seen.some((path) => path !== null && path.endsWith("intro.tex"))).toBe(true);
    close();
    const count = seen.length;
    writeFileSync(join(root, "chapters", "later.tex"), "y");
    await new Promise((r) => setTimeout(r, 300));
    expect(seen.length).toBe(count);
  });

  async function until(check: () => boolean, ms = 3000): Promise<boolean> {
    const limit = Date.now() + ms;
    while (!check() && Date.now() < limit) await new Promise((r) => setTimeout(r, 20));
    return check();
  }

  it("still sees in-place writes to a file after it was replaced by rename (the store's own atomic save)", async () => {
    const root = mkdtempSync(join(tmpdir(), "caztor-watch-"));
    watchDirs.push(root);
    mkdirSync(join(root, "chapters"));
    writeFileSync(join(root, "main.tex"), "one");
    writeFileSync(join(root, "chapters", "intro.tex"), "one");
    const seen: Array<string | null> = [];
    const close = nodeDirectoryWatcher.watch(root, (path) => seen.push(path), () => {});
    for (const name of ["main.tex", "chapters/intro.tex"]) {
      writeFileSync(join(root, `${name}.tmp`), "two");
      renameSync(join(root, `${name}.tmp`), join(root, name));
      await new Promise((r) => setTimeout(r, 200));
      seen.length = 0;
      writeFileSync(join(root, name), "three");
      expect(await until(() => seen.some((path) => path === name), 500), `in-place write to ${name}`).toBe(true);
    }
    close();
  });

  it("reports an error when the watched folder is removed and created again, so the caller opens a new watcher", async () => {
    const root = mkdtempSync(join(tmpdir(), "caztor-watch-"));
    watchDirs.push(root);
    writeFileSync(join(root, "a.tex"), "one");
    const errors: Error[] = [];
    const close = nodeDirectoryWatcher.watch(root, () => {}, (error) => errors.push(error));
    rmSync(root, { recursive: true });
    mkdirSync(root);
    writeFileSync(join(root, "b.tex"), "two");
    expect(await until(() => errors.length > 0)).toBe(true);
    close();
  });

  it("watches folders created later, stops reporting for removed ones and skips reserved folders", async () => {
    const root = mkdtempSync(join(tmpdir(), "caztor-watch-"));
    watchDirs.push(root);
    mkdirSync(join(root, ".caztor"));
    const seen: Array<string | null> = [];
    const close = nodeDirectoryWatcher.watch(root, (path) => seen.push(path), () => {});
    mkdirSync(join(root, "later", "deep"), { recursive: true });
    await new Promise((r) => setTimeout(r, 200));
    writeFileSync(join(root, "later", "deep", "x.tex"), "x");
    expect(await until(() => seen.some((path) => path === "later/deep/x.tex"))).toBe(true);
    seen.length = 0;
    writeFileSync(join(root, ".caztor", "state.json"), "{}");
    await new Promise((r) => setTimeout(r, 300));
    expect(seen.some((path) => path !== null && path.startsWith(".caztor/"))).toBe(false);
    rmSync(join(root, "later"), { recursive: true });
    await new Promise((r) => setTimeout(r, 300));
    seen.length = 0;
    mkdirSync(join(root, "later"));
    // The folder's own watch is opened when its creation is reported; the project watcher scans new folders itself.
    await new Promise((r) => setTimeout(r, 200));
    writeFileSync(join(root, "later", "y.tex"), "y");
    expect(await until(() => seen.some((path) => path === "later/y.tex"))).toBe(true);
    close();
  });
});

describe("nodeFileSystem.mkdtemp", () => {
  it("creates a new private folder each time, readable by nobody else, and it can be removed again", async () => {
    const { mkdtempSync, statSync, existsSync, rmSync, realpathSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const { join } = await import("node:path");
    const { nodeFileSystem } = await import("../src/node-infra.ts");
    const parent = realpathSync(mkdtempSync(join(tmpdir(), "caztor-mkdtemp-")));
    try {
      const a = await nodeFileSystem.mkdtemp(join(parent, "box-"));
      const b = await nodeFileSystem.mkdtemp(join(parent, "box-"));
      expect(a).not.toBe(b);
      expect(a.startsWith(join(parent, "box-"))).toBe(true);
      expect(statSync(a).mode & 0o777).toBe(0o700);
      await nodeFileSystem.rm(a, { recursive: true, force: true });
      expect(existsSync(a)).toBe(false);
      expect(existsSync(b)).toBe(true);
    } finally {
      rmSync(parent, { recursive: true, force: true });
    }
  });
});
