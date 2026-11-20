import { describe, expect, it } from "vitest";
import { cleanupSandboxes, implementations, type Sandbox } from "../support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

async function codeOf(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return (error as { code?: unknown }).code;
  }
  return "no error";
}

cleanupSandboxes();

describe.each(implementations)("FileSystem contract: %s", (_name, create) => {
  async function sandbox(): Promise<Sandbox> {
    const box = create();
    await box.fs.mkdir(box.root, { recursive: true });
    return box;
  }

  it("resolves . and .. segments like the operating system", async () => {
    const { fs, root } = await sandbox();
    await fs.mkdir(`${root}/sub`);
    await fs.writeFile(`${root}/a.txt`, encode("a"));

    expect(decode(await fs.readFile(`${root}/sub/../a.txt`))).toBe("a");
    expect(decode(await fs.readFile(`${root}/./sub/./../a.txt`))).toBe("a");
    expect(await fs.realpath(`${root}/sub/..`)).toBe(root);
    expect(await codeOf(fs.readFile(`${root}/sub/../missing.txt`))).toBe("ENOENT");
    expect(await codeOf(fs.readFile(`${root}/a.txt/../a.txt`))).toBe("ENOTDIR");
  });

  it("resolves .. after a symbolic link against the link target, not the link location", async () => {
    const { fs, root, symlink } = await sandbox();
    await fs.mkdir(`${root}/outside/deep`, { recursive: true });
    await fs.writeFile(`${root}/outside/secret.txt`, encode("s"));
    await fs.mkdir(`${root}/project`);
    symlink(`${root}/outside/deep`, `${root}/project/link`);

    expect(await fs.realpath(`${root}/project/link/..`)).toBe(`${root}/outside`);
    expect(decode(await fs.readFile(`${root}/project/link/../secret.txt`))).toBe("s");
  });

  it("fails an exclusive write on an existing file and on any symbolic link, dangling or not, without following it", async () => {
    const { fs, root, symlink } = await sandbox();
    await fs.writeFile(`${root}/real.txt`, encode("real"));
    symlink(`${root}/real.txt`, `${root}/alias.txt`);
    symlink(`${root}/nowhere.txt`, `${root}/dangling.txt`);

    expect(await codeOf(fs.writeFile(`${root}/real.txt`, encode("x"), { exclusive: true }))).toBe("EEXIST");
    expect(await codeOf(fs.writeFile(`${root}/alias.txt`, encode("x"), { exclusive: true }))).toBe("EEXIST");
    expect(await codeOf(fs.writeFile(`${root}/dangling.txt`, encode("x"), { exclusive: true }))).toBe("EEXIST");
    expect(await codeOf(fs.stat(`${root}/nowhere.txt`))).toBe("ENOENT");
    expect(decode(await fs.readFile(`${root}/real.txt`))).toBe("real");

    await fs.writeFile(`${root}/fresh.txt`, encode("new"), { exclusive: true });
    expect(decode(await fs.readFile(`${root}/fresh.txt`))).toBe("new");
  });

  it("follows a symbolic link on a plain write, creating the target of a dangling link", async () => {
    const { fs, root, symlink } = await sandbox();
    symlink(`${root}/target.txt`, `${root}/dangling.txt`);
    await fs.writeFile(`${root}/dangling.txt`, encode("through"));
    expect(decode(await fs.readFile(`${root}/target.txt`))).toBe("through");
    expect((await fs.lstat(`${root}/dangling.txt`)).isSymbolicLink()).toBe(true);
  });

  it("refuses to rename a file onto a directory and a directory onto a file", async () => {
    const { fs, root } = await sandbox();
    await fs.mkdir(`${root}/empty`);
    await fs.mkdir(`${root}/full`);
    await fs.writeFile(`${root}/full/x.txt`, encode("x"));
    await fs.writeFile(`${root}/a.txt`, encode("a"));

    expect(await codeOf(fs.rename(`${root}/a.txt`, `${root}/empty`))).toBe("EISDIR");
    expect(await codeOf(fs.rename(`${root}/a.txt`, `${root}/full`))).toBe("EISDIR");
    expect(await codeOf(fs.rename(`${root}/empty`, `${root}/a.txt`))).toBe("ENOTDIR");
    expect(decode(await fs.readFile(`${root}/a.txt`))).toBe("a");
    expect((await fs.stat(`${root}/empty`)).isDirectory()).toBe(true);
  });

  it("replaces an existing file on rename and an empty directory with a directory", async () => {
    const { fs, root } = await sandbox();
    await fs.writeFile(`${root}/a.txt`, encode("a"));
    await fs.writeFile(`${root}/b.txt`, encode("b"));
    await fs.rename(`${root}/a.txt`, `${root}/b.txt`);
    expect(decode(await fs.readFile(`${root}/b.txt`))).toBe("a");

    await fs.mkdir(`${root}/src`);
    await fs.writeFile(`${root}/src/in.txt`, encode("in"));
    await fs.mkdir(`${root}/dest`);
    await fs.rename(`${root}/src`, `${root}/dest`);
    expect(decode(await fs.readFile(`${root}/dest/in.txt`))).toBe("in");
  });

  it("reports a special file as neither regular, directory nor link and refuses to read it as a file", async () => {
    const { fs, root, special } = await sandbox();
    await special(`${root}/pipe`);
    const stats = await fs.lstat(`${root}/pipe`);
    expect([stats.isFile(), stats.isDirectory(), stats.isSymbolicLink()]).toEqual([false, false, false]);
    expect((await fs.readdir(root)).map((entry) => entry.name)).toEqual(["pipe"]);
  });

  it("reports permission bits in stat and changes them with chmod, following links like the operating system", async () => {
    const { fs, root, symlink } = await sandbox();
    await fs.writeFile(`${root}/run.sh`, encode("#!/bin/sh"));
    await fs.chmod(`${root}/run.sh`, 0o755);
    expect((await fs.stat(`${root}/run.sh`)).mode).toBe(0o755);

    await fs.chmod(`${root}/run.sh`, 0o600);
    expect((await fs.lstat(`${root}/run.sh`)).mode).toBe(0o600);

    symlink(`${root}/run.sh`, `${root}/alias.sh`);
    await fs.chmod(`${root}/alias.sh`, 0o640);
    expect((await fs.stat(`${root}/run.sh`)).mode).toBe(0o640);
  });

  it("keeps the permission bits of a file moved by rename and fails chmod on a missing file", async () => {
    const { fs, root } = await sandbox();
    await fs.writeFile(`${root}/a.sh`, encode("a"));
    await fs.chmod(`${root}/a.sh`, 0o750);
    await fs.rename(`${root}/a.sh`, `${root}/b.sh`);
    expect((await fs.stat(`${root}/b.sh`)).mode).toBe(0o750);
    expect(await codeOf(fs.chmod(`${root}/missing.sh`, 0o644))).toBe("ENOENT");
  });

  it("creates a file with the requested permission bits and leaves an existing file's bits alone", async () => {
    const { fs, root } = await sandbox();
    await fs.writeFile(`${root}/private.txt`, encode("p"), { mode: 0o600 });
    expect((await fs.stat(`${root}/private.txt`)).mode).toBe(0o600);

    await fs.writeFile(`${root}/shared.txt`, encode("s"));
    await fs.chmod(`${root}/shared.txt`, 0o644);
    await fs.writeFile(`${root}/shared.txt`, encode("t"), { mode: 0o600 });
    expect((await fs.stat(`${root}/shared.txt`)).mode).toBe(0o644);

    await fs.writeFile(`${root}/exclusive.txt`, encode("e"), { exclusive: true, mode: 0o640 });
    expect((await fs.stat(`${root}/exclusive.txt`)).mode).toBe(0o640);
  });
});
