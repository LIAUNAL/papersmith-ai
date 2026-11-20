import { hashBytes, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createProjectStore, MAX_TEXT_BYTES } from "../src/project-store.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
const rel = (path: string) => path as RelPath;

cleanupSandboxes();

describe.each(implementations)("project store reads and containment: %s", (_name, create) => {
  async function setup(options: { agentsMdCreatedByCaztor?: boolean } = {}) {
    const box = create();
    const project = `${box.root}/project`;
    const outside = `${box.root}/outside`;
    await box.fs.mkdir(project, { recursive: true });
    await box.fs.mkdir(outside, { recursive: true });
    await box.fs.writeFile(`${outside}/secret.txt`, encode("secret"));
    const store = createProjectStore({ fs: box.fs, root: project, ...options });
    return { ...box, project, outside, store };
  }

  describe("path containment", () => {
    it.each([
      ["../x", "outside_root"],
      ["sub/../../x", "outside_root"],
      ["/etc/passwd", "outside_root"],
      ["a\u0000b", "invalid_path"],
      ["", "invalid_path"],
    ])("rejects %j before touching the disk", async (path, code) => {
      const { store } = await setup();
      const result = await store.read(rel(path));
      expect(result).toEqual({ ok: false, error: { code, path } });
    });

    it("does not read a file outside the root reached by a traversal path", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/inside.txt`, encode("inside"));
      expect((await store.read(rel("../outside/secret.txt"))).ok).toBe(false);
      expect((await store.read(rel("inside.txt"))).ok).toBe(true);
    });

    it("refuses a symbolic link that points outside the project, for the file and for a parent directory", async () => {
      const { store, project, outside, symlink } = await setup();
      symlink(`${outside}/secret.txt`, `${project}/leak.txt`);
      symlink(outside, `${project}/escape`);

      expect(await store.read(rel("leak.txt"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
      expect(await store.read(rel("escape/secret.txt"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
    });

    it("refuses a dangling link because its target cannot be proven to stay inside", async () => {
      const { store, project, symlink } = await setup();
      symlink(`${project}/not-there.txt`, `${project}/dangling.txt`);
      expect(await store.read(rel("dangling.txt"))).toMatchObject({ ok: false, error: { code: "outside_root" } });
    });

    it("follows a link that stays inside the project", async () => {
      const { store, project, fs, symlink } = await setup();
      await fs.mkdir(`${project}/chapters`);
      await fs.writeFile(`${project}/chapters/one.tex`, encode("one"));
      symlink(`${project}/chapters`, `${project}/c`);

      const result = await store.read(rel("c/one.tex"));
      expect(result.ok && decode(result.value.bytes)).toBe("one");
    });

    it("refuses a link that leads into a reserved folder", async () => {
      const { store, project, fs, symlink } = await setup();
      await fs.mkdir(`${project}/.git`);
      await fs.writeFile(`${project}/.git/config`, encode("[core]"));
      symlink(`${project}/.git`, `${project}/docs`);
      expect(await store.read(rel("docs/config"))).toMatchObject({ ok: false, error: { code: "hidden" } });
    });

    it("refuses directories and other non-regular files", async () => {
      const { store, project, fs, special } = await setup();
      await fs.mkdir(`${project}/folder`);
      await special(`${project}/pipe`);
      expect(await store.read(rel("folder"))).toMatchObject({ ok: false, error: { code: "invalid_path" } });
      expect(await store.read(rel("pipe"))).toMatchObject({ ok: false, error: { code: "invalid_path" } });
    });

    it("reports a missing file as not_found, also below a missing folder", async () => {
      const { store } = await setup();
      expect(await store.read(rel("missing.tex"))).toMatchObject({ ok: false, error: { code: "not_found" } });
      expect(await store.read(rel("no/such/file.tex"))).toMatchObject({ ok: false, error: { code: "not_found" } });
    });
  });

  describe("reserved paths", () => {
    it.each([".caztor/state.json", ".claude/settings.json", ".opencode/a.json", ".agents/agents/caztor.md", ".git/config", "node_modules/x/index.js"])(
      "rejects reading %s as hidden",
      async (path) => {
        const { store, project, fs } = await setup();
        const dir = path.slice(0, path.lastIndexOf("/"));
        await fs.mkdir(`${project}/${dir}`, { recursive: true });
        await fs.writeFile(`${project}/${path}`, encode("x"));
        expect(await store.read(rel(path))).toEqual({ ok: false, error: { code: "hidden", path } });
      },
    );

    it("lists user files and folders while hiding every reserved folder", async () => {
      const { store, project, fs } = await setup();
      for (const dir of [".caztor", ".claude", ".opencode", ".agents", ".git", "node_modules", "chapters"]) {
        await fs.mkdir(`${project}/${dir}`);
        await fs.writeFile(`${project}/${dir}/inner.txt`, encode("x"));
      }
      await fs.writeFile(`${project}/main.tex`, encode("hello"));

      expect(await store.list()).toEqual([
        { path: "chapters", kind: "dir", size: 0 },
        { path: "chapters/inner.txt", kind: "file", size: 1 },
        { path: "main.tex", kind: "file", size: 5 },
      ]);
    });

    it("does not walk into environment, dependency and cache folders at any depth, which can still be read by path", async () => {
      const { store, project, fs } = await setup();
      const skipped = [".micromamba", "code/.venv", "code/.conda", "code/src/__pycache__", "code/node_modules", "code/.git", "code/.tox", "code/.mypy_cache", "code/.pytest_cache", "code/.ruff_cache"];
      for (const dir of skipped) {
        await fs.mkdir(`${project}/${dir}`, { recursive: true });
        await fs.writeFile(`${project}/${dir}/inner.txt`, encode("x"));
      }
      await fs.writeFile(`${project}/code/src/model.py`, encode("m"));
      await fs.mkdir(`${project}/code/venv`);
      await fs.writeFile(`${project}/code/venv/kept.txt`, encode("k"));

      expect((await store.list()).map((entry) => entry.path)).toEqual(["code", "code/src", "code/src/model.py", "code/venv", "code/venv/kept.txt"]);
      const read = await store.read(rel("code/.venv/inner.txt"));
      expect(read.ok && decode(read.value.bytes)).toBe("x");
    });

    it("shows a user-authored AGENTS.md and hides one created by Caztor", async () => {
      const authored = await setup({ agentsMdCreatedByCaztor: false });
      await authored.fs.writeFile(`${authored.project}/AGENTS.md`, encode("mine"));
      expect((await authored.store.list()).map((entry) => entry.path)).toEqual(["AGENTS.md"]);

      const created = await setup({ agentsMdCreatedByCaztor: true });
      await created.fs.writeFile(`${created.project}/AGENTS.md`, encode("ours"));
      await created.fs.writeFile(`${created.project}/main.tex`, encode("m"));
      expect((await created.store.list()).map((entry) => entry.path)).toEqual(["main.tex"]);
    });

    it("lists binary files, skips links and special files, and does not descend into links", async () => {
      const { store, project, outside, fs, symlink, special } = await setup();
      await fs.writeFile(`${project}/figure.png`, new Uint8Array([0, 255, 1]));
      symlink(outside, `${project}/escape`);
      await special(`${project}/pipe`);

      expect(await store.list()).toEqual([{ path: "figure.png", kind: "file", size: 3 }]);
    });
  });

  describe("read and readText", () => {
    it("returns the bytes with their sha256 hash", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/a.tex`, encode("hello"));
      const result = await store.read(rel("a.tex"));
      expect(result).toEqual({ ok: true, value: { bytes: encode("hello"), hash: await hashBytes(encode("hello")) } });
    });

    it("opens UTF-8 text but refuses binary data and files over 2 MB", async () => {
      const { store, project, fs } = await setup();
      await fs.writeFile(`${project}/text.tex`, encode("café €"));
      await fs.writeFile(`${project}/bad.bin`, new Uint8Array([0xff, 0xfe, 0x41]));
      await fs.writeFile(`${project}/nul.bin`, new Uint8Array([0x41, 0x00, 0x42]));
      await fs.writeFile(`${project}/big.tex`, new Uint8Array(MAX_TEXT_BYTES + 1).fill(0x61));
      await fs.writeFile(`${project}/limit.tex`, new Uint8Array(MAX_TEXT_BYTES).fill(0x61));

      const text = await store.readText(rel("text.tex"));
      expect(text.ok && decode(text.value.bytes)).toBe("café €");
      expect(await store.readText(rel("bad.bin"))).toMatchObject({ ok: false, error: { code: "not_text" } });
      expect(await store.readText(rel("nul.bin"))).toMatchObject({ ok: false, error: { code: "not_text" } });
      expect(await store.readText(rel("big.tex"))).toMatchObject({ ok: false, error: { code: "too_large" } });
      expect((await store.readText(rel("limit.tex"))).ok).toBe(true);
    });
  });
});
