import { describe, expect, it } from "vitest";
import { createProjectCatalog } from "../src/project-catalog.ts";
import { MemoryFileSystem } from "./fakes/memory-fs.ts";

const HOME = "/home/someone";
const setup = (files: Record<string, string>, papersDir: string | null = `${HOME}/papers`) => {
  const fs = new MemoryFileSystem(files);
  return { fs, catalog: createProjectCatalog({ fs, papersDir, configHome: `${HOME}/.config` }) };
};

describe("the project catalog", () => {
  it("finds workspaces by either marker, leaves other folders out, and reads the title", async () => {
    const { catalog } = setup({
      [`${HOME}/papers/new/papersmith.yaml`]: 'name: new\ntitle: "Spin states"\n',
      [`${HOME}/papers/new/paper/main.tex`]: "x",
      [`${HOME}/papers/old/.papersmith/config.json`]: "{}",
      [`${HOME}/papers/notes/readme.md`]: "x",
      [`${HOME}/papers/loose.yaml`]: "x",
    });
    expect(await catalog.list()).toEqual([
      { path: `${HOME}/papers/new`, name: "new", kind: "papersmith", title: "Spin states" },
      { path: `${HOME}/papers/old`, name: "old", kind: "papersmith", missingMain: true },
    ]);
  });

  it("gives no title for an empty or null one", async () => {
    const { catalog } = setup({
      [`${HOME}/papers/a/papersmith.yaml`]: "title:\n",
      [`${HOME}/papers/b/papersmith.yaml`]: "title: null\n",
    });
    expect((await catalog.list()).map((entry) => entry.title)).toEqual([undefined, undefined]);
  });

  it("lists nothing when the papers folder is missing or unset", async () => {
    expect(await setup({ "/x/y": "z" }).catalog.list()).toEqual([]);
    expect(await setup({ "/x/y": "z" }, null).catalog.list()).toEqual([]);
  });

  it("remembers an opened folder across catalogs, once, and describes it as a plain folder", async () => {
    const { fs, catalog } = setup({ "/work/thesis/main.tex": "x", [`${HOME}/papers/a/papersmith.yaml`]: "" });
    await catalog.remember("/work/thesis");
    await catalog.remember("/work/thesis");
    await catalog.remember(`${HOME}/papers/a`);
    const again = createProjectCatalog({ fs, papersDir: `${HOME}/papers`, configHome: `${HOME}/.config` });
    expect((await again.list()).map((entry) => [entry.name, entry.kind])).toEqual([["a", "papersmith"], ["thesis", "folder"]]);
  });

  it("drops a remembered folder that is gone, and survives a damaged list", async () => {
    const { fs, catalog } = setup({ "/work/thesis/main.tex": "x" });
    await catalog.remember("/work/thesis");
    await fs.rm("/work/thesis", { recursive: true });
    expect(await catalog.list()).toEqual([]);
    await fs.writeFile(`${HOME}/.config/caztor/projects.json`, new TextEncoder().encode("{broken"));
    expect(await catalog.list()).toEqual([]);
    await catalog.remember("/work");
    expect((await catalog.list()).map((entry) => entry.path)).toEqual(["/work"]);
  });

  it("does not fail when the list cannot be saved or there is no config folder", async () => {
    const fs = new MemoryFileSystem({ "/work/a/main.tex": "x" });
    const catalog = createProjectCatalog({ fs, papersDir: null, configHome: null });
    await catalog.remember("/work/a");
    expect(await catalog.list()).toEqual([]);
    expect(await catalog.describe("/work/a")).toEqual({ path: "/work/a", name: "a", kind: "folder" });
    expect(await catalog.describe("/work/none")).toBeNull();
  });
});

describe("the folder the catalog creates", () => {
  it("is closed to other users, like the stores that share it", async () => {
    const { fs, catalog } = setup({ "/work/thesis/main.tex": "x" });
    await catalog.remember("/work/thesis");
    expect((await fs.stat(`${HOME}/.config/caztor`)).mode & 0o777).toBe(0o700);
    expect((await fs.stat(`${HOME}/.config/caztor/projects.json`)).mode & 0o777).toBe(0o600);
  });
});
