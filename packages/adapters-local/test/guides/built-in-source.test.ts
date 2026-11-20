import { describe, expect, it } from "vitest";
import { guideSetProblem } from "@caztor/core";
import { createBuiltInGuideSource, defaultGuidesDir, defaultLicensePath } from "../../src/guides/built-in-source.ts";
import { nodeFileSystem } from "../../src/node-infra.ts";
import { cleanupSandboxes, implementations } from "../support/fs-sandbox.ts";

cleanupSandboxes();
const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

describe.each(implementations)("built-in guide source: %s", (_name, create) => {
  async function setup(files: Record<string, string>, license: string | null = "Apache License text") {
    const box = create();
    const guidesDir = `${box.root}/guides`;
    await box.fs.mkdir(guidesDir, { recursive: true });
    for (const [name, text] of Object.entries(files)) await box.fs.writeFile(`${guidesDir}/${name}`, encode(text));
    const licensePath = `${box.root}/LICENSES/Apache-2.0.txt`;
    if (license !== null) {
      await box.fs.mkdir(`${box.root}/LICENSES`, { recursive: true });
      await box.fs.writeFile(licensePath, encode(license));
    }
    return { ...box, guidesDir, licensePath, source: createBuiltInGuideSource({ fs: box.fs, guidesDir, licensePath }) };
  }

  it("serves the guides, the index and the license copy under its guide name, sorted", async () => {
    const t = await setup({ "INDEX.md": "index", "02-b.md": "two", "01-a.md": "one" });

    const loaded = await t.source.load();

    expect(loaded.ok).toBe(true);
    const documents = loaded.ok ? loaded.value : [];
    expect(documents.map((d) => d.name)).toEqual(["01-a.md", "02-b.md", "INDEX.md", "LICENSE-papersmith-ai.txt"]);
    expect(documents.map((d) => decode(d.bytes))).toEqual(["one", "two", "index", "Apache License text"]);
    expect(guideSetProblem(documents)).toBeNull();
  });

  it("leaves out files that are not guides, such as the source record, tests and folders", async () => {
    const t = await setup({ "INDEX.md": "index", "01-a.md": "one", "SOURCE.json": "{}", "guides.test.ts": "x", "tsconfig.json": "{}", "notes.md": "n" });
    await t.fs.mkdir(`${t.guidesDir}/03-folder.md`);

    const loaded = await t.source.load();

    expect(loaded.ok && loaded.value.map((d) => d.name)).toEqual(["01-a.md", "INDEX.md", "LICENSE-papersmith-ai.txt"]);
  });

  it("does not follow a link that is named like a guide", async () => {
    const t = await setup({ "INDEX.md": "index", "01-a.md": "one" });
    await t.fs.writeFile(`${t.root}/secret.txt`, encode("secret"));
    t.symlink(`${t.root}/secret.txt`, `${t.guidesDir}/02-link.md`);

    const loaded = await t.source.load();

    expect(loaded.ok && loaded.value.map((d) => d.name)).toEqual(["01-a.md", "INDEX.md", "LICENSE-papersmith-ai.txt"]);
  });

  it("returns a readable error when the guides folder is missing", async () => {
    const t = await setup({});
    await t.fs.rm(t.guidesDir, { recursive: true });

    const loaded = await t.source.load();

    expect(loaded.ok).toBe(false);
    expect(!loaded.ok && loaded.error.message).toMatch(/^The built-in writing guides could not be read: /);
  });

  it("returns a readable error when the license copy is missing", async () => {
    const t = await setup({ "INDEX.md": "index" }, null);

    const loaded = await t.source.load();

    expect(loaded.ok).toBe(false);
    expect(!loaded.ok && loaded.error.message).toMatch(/license/i);
  });
});

describe("the guides shipped in the repository", () => {
  it("are served as ten guides, the index and the license copy", async () => {
    const source = createBuiltInGuideSource({ fs: nodeFileSystem, guidesDir: defaultGuidesDir(), licensePath: defaultLicensePath() });

    const loaded = await source.load();

    expect(loaded.ok).toBe(true);
    const documents = loaded.ok ? loaded.value : [];
    expect(documents).toHaveLength(12);
    expect(documents.map((d) => d.name).filter((name) => /^\d\d-/.test(name))).toHaveLength(10);
    expect(documents.map((d) => d.name)).toContain("LICENSE-papersmith-ai.txt");
    expect(guideSetProblem(documents)).toBeNull();
    const license = documents.find((d) => d.name === "LICENSE-papersmith-ai.txt");
    expect(decode(license?.bytes ?? new Uint8Array())).toContain("Apache License");
  });
});
