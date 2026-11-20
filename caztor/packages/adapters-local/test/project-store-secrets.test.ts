import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { RelPath } from "@caztor/core";
import { afterEach, describe, expect, it } from "vitest";
import { nodeFileSystem } from "../src/node-infra.ts";
import { createProjectStore } from "../src/project-store.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});
const STORE = "skills/kaggle-accounts/store";
function setup() {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-secrets-")));
  dirs.push(root);
  mkdirSync(join(root, STORE), { recursive: true });
  writeFileSync(join(root, STORE, "a.json"), "secret");
  writeFileSync(join(root, "skills", "SKILL.md"), "guide");
  return { root, store: createProjectStore({ fs: nodeFileSystem, root }) };
}
const rel = (path: string) => path as RelPath;
const hidden = { ok: false, error: { code: "hidden" } };

describe("a folder that holds secrets", () => {
  it("is not listed and cannot be read", async () => {
    const { store } = setup();
    const listed = (await store.list()).map((entry) => entry.path as string);
    expect(listed).toContain("skills/SKILL.md");
    expect(listed.some((path) => path.includes("store"))).toBe(false);
    expect(await store.read(rel(`${STORE}/a.json`))).toMatchObject(hidden);
  });

  it("cannot be reached through a link to a parent or to itself", async () => {
    const { root, store } = setup();
    symlinkSync(join(root, "skills"), join(root, "s"));
    symlinkSync(join(root, STORE), join(root, "direct"));
    expect(await store.read(rel("s/kaggle-accounts/store/a.json"))).toMatchObject(hidden);
    expect(await store.read(rel("direct/a.json"))).toMatchObject(hidden);
  });

  it("cannot be moved or deleted along with a folder above it", async () => {
    const { root, store } = setup();
    expect(await store.rename(rel("skills"), rel("moved"))).toMatchObject(hidden);
    expect(await store.rename(rel("skills/kaggle-accounts"), rel("moved"))).toMatchObject(hidden);
    expect(await store.remove(rel("skills/kaggle-accounts"), { recursive: true })).toMatchObject(hidden);
    expect(await store.remove(rel("skills"), { recursive: true })).toMatchObject(hidden);
    expect(readFileSync(join(root, STORE, "a.json"), "utf8")).toBe("secret");
  });

  it("does not stop moving or deleting a folder above it once it does not exist", async () => {
    const { root, store } = setup();
    rmSync(join(root, "skills", "kaggle-accounts"), { recursive: true });
    expect((await store.rename(rel("skills"), rel("moved"))).ok).toBe(true);
    expect((await store.remove(rel("moved"), { recursive: true })).ok).toBe(true);
  });
});
