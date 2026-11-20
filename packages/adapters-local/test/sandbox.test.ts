import { describe, expect, it } from "vitest";
import { buildSandboxedSpec, createSandbox, parseLddPaths, sandboxStartFailure, type SandboxProfile } from "../src/sandbox.ts";
import type { SpawnSpec } from "../src/infra.ts";
import { FakeClock } from "./fakes/fake-clock.ts";
import { FakeSpawner } from "./fakes/fake-spawner.ts";
import { MemoryFileSystem } from "./fakes/memory-fs.ts";

const LDD = `\tlinux-vdso.so.1 (0x0000707e10fa5000)
\tlibstdc++.so.6 => /opt/brew/opt/gcc/lib/libstdc++.so.6 (0x0000707e0f400000)
\tlibm.so.6 => /usr/lib/x86_64-linux-gnu/libm.so.6 (0x0000707e0ee7d000)
\t/opt/brew/lib/ld.so => /lib64/ld-linux-x86-64.so.2 (0x0000707e10fa7000)
\tlibz.so.1 => not found
`;

const profile: SandboxProfile = {
  bwrap: "/usr/bin/bwrap",
  tool: "/opt/brew/bin/tectonic",
  root: "/work/proj",
  cacheDirs: ["/home/u/.cache/tectonic"],
  libraries: ["/opt/brew/opt/gcc/lib/libstdc++.so.6", "/opt/brew/lib/ld.so", "/usr/lib/x86_64-linux-gnu/libm.so.6"],
};
const spec: SpawnSpec = {
  file: "tectonic",
  args: ["-X", "compile", "./main.tex"],
  cwd: "/work/proj",
  env: { PATH: "/usr/bin", HOME: "/home/u", TMPDIR: "/var/folders/x" },
};

const at = (args: readonly string[], ...sequence: string[]) =>
  args.findIndex((_, index) => sequence.every((part, offset) => args[index + offset] === part));

describe("parseLddPaths", () => {
  it("returns the resolved library paths and the interpreter, skipping the vdso and unresolved names", () => {
    expect(parseLddPaths(LDD)).toEqual([
      "/opt/brew/opt/gcc/lib/libstdc++.so.6",
      "/usr/lib/x86_64-linux-gnu/libm.so.6",
      "/opt/brew/lib/ld.so",
      "/lib64/ld-linux-x86-64.so.2",
    ]);
  });

  it("returns nothing for a static executable", () => {
    expect(parseLddPaths("\tnot a dynamic executable\n")).toEqual([]);
  });
});

describe("buildSandboxedSpec", () => {
  const wrapped = buildSandboxedSpec(profile, spec);

  it("runs bwrap with an argument array that ends with the tool and its original arguments", () => {
    expect(wrapped.file).toBe("/usr/bin/bwrap");
    expect(wrapped.args.slice(-5)).toEqual(["--", "/opt/brew/bin/tectonic", "-X", "compile", "./main.tex"]);
    expect(wrapped.cwd).toBe("/work/proj");
  });

  it("starts in new namespaces with the network kept and dies with its parent", () => {
    expect(wrapped.args).toContain("--unshare-all");
    expect(wrapped.args).toContain("--share-net");
    expect(wrapped.args).toContain("--die-with-parent");
  });

  it("binds the project read-only and only its build folder writable", () => {
    expect(at(wrapped.args, "--ro-bind", "/work/proj", "/work/proj")).toBeGreaterThan(-1);
    const build = at(wrapped.args, "--bind", "/work/proj/.caztor/build", "/work/proj/.caztor/build");
    expect(build).toBeGreaterThan(at(wrapped.args, "--ro-bind", "/work/proj", "/work/proj"));
    const writable = wrapped.args.flatMap((arg, index) => (arg === "--bind" ? [wrapped.args[index + 1]] : []));
    expect(writable).toEqual(["/work/proj/.caztor/build", "/home/u/.cache/tectonic"]);
  });

  it("binds the tool and its libraries but not the ones the system tree already provides", () => {
    expect(at(wrapped.args, "--ro-bind", "/opt/brew/bin/tectonic", "/opt/brew/bin/tectonic")).toBeGreaterThan(-1);
    expect(at(wrapped.args, "--ro-bind-try", "/opt/brew/lib/ld.so", "/opt/brew/lib/ld.so")).toBeGreaterThan(-1);
    expect(wrapped.args).not.toContain("/usr/lib/x86_64-linux-gnu/libm.so.6");
  });

  it("never exposes the home folder, and gives the child a private /tmp", () => {
    expect(wrapped.args).not.toContain("/home/u");
    expect(at(wrapped.args, "--tmpfs", "/tmp")).toBeGreaterThan(-1);
    expect(wrapped.env["TMPDIR"]).toBe("/tmp");
    expect(wrapped.env["HOME"]).toBe("/home/u");
  });
});

describe("sandboxStartFailure", () => {
  it("recognises a message from bwrap itself", () => {
    expect(sandboxStartFailure("note: x\nbwrap: No permissions to create new namespace\n")).toBe("No permissions to create new namespace");
  });

  it("ignores engine output", () => {
    expect(sandboxStartFailure("error: halted on potentially-recoverable error\n")).toBeNull();
  });
});

describe("createSandbox", () => {
  function setup(options: { bwrap?: boolean } = {}) {
    const files: Record<string, string> = { "/opt/brew/bin/tectonic": "x" };
    if (options.bwrap !== false) files["/usr/bin/bwrap"] = "x";
    const fs = new MemoryFileSystem(files);
    const fake = new FakeSpawner();
    const sandbox = createSandbox({
      spawner: fake,
      clock: new FakeClock(0),
      fs,
      root: "/work/proj",
      env: { PATH: "/opt/brew/bin:/usr/bin", HOME: "/home/u" },
    });
    return { fs, fake, sandbox };
  }

  it("is available when the trivial run inside bwrap answers with a version", async () => {
    const { fake, sandbox } = setup();
    fake.enqueue({ stdout: [LDD], exit: { code: 0, signal: null } });
    fake.enqueue({ stdout: ["Tectonic 0.17.0\n"], exit: { code: 0, signal: null } });
    expect(await sandbox.probe()).toEqual({ ok: true, version: "bubblewrap, Tectonic 0.17.0" });
    expect(fake.calls[0]).toMatchObject({ file: "ldd", args: ["/opt/brew/bin/tectonic"] });
    expect(fake.calls[1]?.file).toBe("/usr/bin/bwrap");
    expect(fake.calls[1]?.args.slice(-3)).toEqual(["--", "/opt/brew/bin/tectonic", "--version"]);
    expect(fake.calls[1]?.args).toContain("/opt/brew/lib/ld.so");
  });

  it("creates the project build folder and the cache folder the profile binds", async () => {
    const { fs, fake, sandbox } = setup();
    fake.enqueue({ stdout: [LDD], exit: { code: 0, signal: null } });
    fake.enqueue({ stdout: ["Tectonic 0.17.0\n"], exit: { code: 0, signal: null } });
    await sandbox.probe();
    expect((await fs.stat("/work/proj/.caztor/build")).isDirectory()).toBe(true);
    expect((await fs.stat("/home/u/.cache/tectonic")).isDirectory()).toBe(true);
  });

  it("is unavailable, with the reason, when bwrap is not installed", async () => {
    const { fake, sandbox } = setup({ bwrap: false });
    const probe = await sandbox.probe();
    expect(probe.ok).toBe(false);
    expect(probe.reason).toMatch(/bwrap.*not (found|installed)/i);
    expect(fake.calls).toEqual([]);
  });

  it("is unavailable when the kernel refuses user namespaces, and says so", async () => {
    const { fake, sandbox } = setup();
    fake.enqueue({ stdout: [LDD], exit: { code: 0, signal: null } });
    fake.enqueue({ stderr: ["bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.\n"], exit: { code: 1, signal: null } });
    const probe = await sandbox.probe();
    expect(probe.ok).toBe(false);
    expect(probe.reason).toMatch(/user namespaces/i);
  });

  it("remembers a successful probe and wraps a later spec without probing again", async () => {
    const { fake, sandbox } = setup();
    fake.enqueue({ stdout: [LDD], exit: { code: 0, signal: null } });
    fake.enqueue({ stdout: ["Tectonic 0.17.0\n"], exit: { code: 0, signal: null } });
    const wrap = await sandbox.wrapper();
    await sandbox.probe();
    expect(fake.calls).toHaveLength(2);
    const wrapped = wrap(spec);
    expect(wrapped.file).toBe("/usr/bin/bwrap");
    expect(wrapped.args.slice(-4)).toEqual(["/opt/brew/bin/tectonic", "-X", "compile", "./main.tex"]);
  });

  it("refuses to wrap when the sandbox is unavailable", async () => {
    const { sandbox } = setup({ bwrap: false });
    await expect(sandbox.wrapper()).rejects.toThrow(/bwrap/);
  });
});

describe("the Tectonic spec, byte for byte", () => {
  it("keeps the exact argument list, environment, file and folder", () => {
    const systemFiles = ["/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf", "/etc/ld.so.cache", "/etc/localtime", "/etc/ssl/certs", "/etc/ca-certificates", "/etc/pki", "/etc/fonts"];
    expect(buildSandboxedSpec(profile, { ...spec, stdin: "in" })).toEqual({
      file: "/usr/bin/bwrap",
      cwd: "/work/proj",
      stdin: "in",
      env: { PATH: "/usr/bin", HOME: "/home/u", TMPDIR: "/tmp" },
      args: [
        "--unshare-all", "--share-net", "--die-with-parent",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64", "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/sbin", "/sbin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        ...systemFiles.flatMap((file) => ["--ro-bind-try", file, file]),
        "--ro-bind-try", "/opt/brew/opt/gcc/lib/libstdc++.so.6", "/opt/brew/opt/gcc/lib/libstdc++.so.6",
        "--ro-bind-try", "/opt/brew/lib/ld.so", "/opt/brew/lib/ld.so",
        "--ro-bind", "/opt/brew/bin/tectonic", "/opt/brew/bin/tectonic",
        "--ro-bind", "/work/proj", "/work/proj", "--bind", "/work/proj/.caztor/build", "/work/proj/.caztor/build",
        "--bind", "/home/u/.cache/tectonic", "/home/u/.cache/tectonic",
        "--chdir", "/work/proj", "--", "/opt/brew/bin/tectonic", "-X", "compile", "./main.tex",
      ],
    });
  });
});

describe("what the sandbox binds", () => {
  it("binds neither the home folder nor the configuration folder that holds keys and collaborators", () => {
    const wrapped = buildSandboxedSpec(profile, spec);
    const sources: string[] = [];
    wrapped.args.forEach((arg, index) => {
      if (arg === "--bind" || arg === "--ro-bind" || arg === "--ro-bind-try" || arg === "--bind-try") sources.push(wrapped.args[index + 1]!);
    });
    expect(sources.length).toBeGreaterThan(0);
    for (const source of sources) {
      expect(source).not.toBe("/home/u");
      expect(source.startsWith("/home/u/.config")).toBe(false);
      expect("/home/u/.config/caztor".startsWith(`${source}/`)).toBe(false);
    }
  });
});
