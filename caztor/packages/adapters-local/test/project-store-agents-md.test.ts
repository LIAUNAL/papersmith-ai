import type { RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createProjectStore } from "../src/project-store.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const rel = (path: string) => path as RelPath;

cleanupSandboxes();

describe.each(implementations)("AGENTS.md created by Caztor in the file API: %s", (_name, create) => {
  async function setup(createdByCaztor: boolean) {
    const box = create();
    const project = `${box.root}/project`;
    await box.fs.mkdir(project, { recursive: true });
    await box.fs.writeFile(`${project}/AGENTS.md`, encode("managed"));
    await box.fs.writeFile(`${project}/other.md`, encode("other"));
    const store = createProjectStore({ fs: box.fs, root: project, agentsMdCreatedByCaztor: () => createdByCaztor });
    return { ...box, project, store };
  }

  it("rejects reading, saving, renaming and deleting it as hidden, like a reserved path", async () => {
    const { store, project, fs } = await setup(true);
    const hidden = (path: string) => ({ ok: false, error: { code: "hidden", path } });

    expect(await store.read(rel("AGENTS.md"))).toEqual(hidden("AGENTS.md"));
    expect(await store.write(rel("AGENTS.md"), encode("x"), "any")).toEqual(hidden("AGENTS.md"));
    expect(await store.rename(rel("AGENTS.md"), rel("moved.md"))).toEqual(hidden("AGENTS.md"));
    expect(await store.rename(rel("other.md"), rel("AGENTS.md"))).toEqual(hidden("AGENTS.md"));
    expect(await store.remove(rel("AGENTS.md"))).toEqual(hidden("AGENTS.md"));
    expect(new TextDecoder().decode(await fs.readFile(`${project}/AGENTS.md`))).toBe("managed");
  });

  it("treats a user-authored AGENTS.md as an ordinary file", async () => {
    const { store } = await setup(false);
    expect((await store.read(rel("AGENTS.md"))).ok).toBe(true);
    expect((await store.write(rel("AGENTS.md"), encode("mine"), "any")).ok).toBe(true);
  });

  it("only hides the top-level file, not one in a folder", async () => {
    const { store, fs, project } = await setup(true);
    await fs.mkdir(`${project}/docs`);
    await fs.writeFile(`${project}/docs/AGENTS.md`, encode("nested"));
    expect((await store.read(rel("docs/AGENTS.md"))).ok).toBe(true);
  });
});
