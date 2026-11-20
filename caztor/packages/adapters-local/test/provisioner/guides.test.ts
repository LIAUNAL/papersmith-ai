import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { fakeGuides, GUIDE_NAMES, GUIDES_TARGET_DIR, hashOf, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const target = (name: string) => `${GUIDES_TARGET_DIR}/${name}`;
const CLAUDE = ".claude/agents/caztor.md";

describe.each(implementations)("provisioning the writing guides: %s", (_name, create) => {
  it("writes the twelve files, tracks each by hash, and reports them after the definition", async () => {
    const guides = fakeGuides();
    const t = await setupProvisioner(create, { guides });

    const result = await t.provisioner.ensure("claude");

    expect(result.ok).toBe(true);
    const outcomes = result.ok ? result.value.outcomes : [];
    expect(outcomes[0]).toEqual({ target: CLAUDE, status: "created" });
    expect(outcomes.slice(1)).toEqual(GUIDE_NAMES.map((name) => ({ target: target(name), status: "created" })));
    expect(await t.names(GUIDES_TARGET_DIR)).toEqual([...GUIDE_NAMES].sort());
    for (const name of GUIDE_NAMES) {
      expect(await t.read(target(name))).toBe(`${name} v1\n`);
      expect((await t.fs.stat(`${t.project}/${target(name)}`)).mode & 0o777).toBe(0o644);
    }
    const tracked = (await t.state.load()).provisioned;
    expect(Object.keys(tracked).filter((key) => key.startsWith(`${GUIDES_TARGET_DIR}/`))).toHaveLength(12);
    expect(tracked[target("INDEX.md")]).toEqual({ hash: await hashOf("INDEX.md v1\n"), createdByCaztor: true });
    expect(tracked[target("LICENSE-papersmith-ai.txt")]).toEqual({ hash: await hashOf("LICENSE-papersmith-ai.txt v1\n"), createdByCaztor: true });
  });

  it("provisions the guides for every provider", async () => {
    for (const provider of ["claude", "opencode", "codex", "antigravity", "pi"] as const) {
      const t = await setupProvisioner(create, { guides: fakeGuides() });
      await t.provisioner.ensure(provider);
      expect(await t.names(GUIDES_TARGET_DIR), provider).toEqual([...GUIDE_NAMES].sort());
    }
  });

  it("shares one set between providers and rewrites nothing the second time", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    const before = await t.fs.stat(`${t.project}/${target("INDEX.md")}`);

    const second = await t.provisioner.ensure("opencode");

    const guideOutcomes = second.ok ? second.value.outcomes.filter((o) => o.target.startsWith(GUIDES_TARGET_DIR)) : [];
    expect(guideOutcomes).toHaveLength(12);
    expect(guideOutcomes.every((o) => o.status === "unchanged")).toBe(true);
    expect((await t.fs.stat(`${t.project}/${target("INDEX.md")}`)).mtimeMs).toBe(before.mtimeMs);
  });

  it("changes nothing when it runs again", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    const stateBefore = JSON.stringify((await t.state.load()).provisioned);
    const mtimes = await Promise.all(GUIDE_NAMES.map(async (name) => (await t.fs.stat(`${t.project}/${target(name)}`)).mtimeMs));

    const again = await t.provisioner.ensure("claude");

    expect(again.ok && again.value.outcomes.every((o) => o.status === "unchanged")).toBe(true);
    expect(JSON.stringify((await t.state.load()).provisioned)).toBe(stateBefore);
    expect(await Promise.all(GUIDE_NAMES.map(async (name) => (await t.fs.stat(`${t.project}/${target(name)}`)).mtimeMs))).toEqual(mtimes);
  });

  it("updates a guide the user did not touch when the source changes", async () => {
    const guides = fakeGuides();
    const t = await setupProvisioner(create, { guides });
    await t.provisioner.ensure("claude");
    guides.set("05-related-work.md", "new related work\n");

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("05-related-work.md")) : undefined;
    expect(outcome).toEqual({ target: target("05-related-work.md"), status: "updated" });
    expect(await t.read(target("05-related-work.md"))).toBe("new related work\n");
    expect((await t.state.load()).provisioned[target("05-related-work.md")]?.hash).toBe(await hashOf("new related work\n"));
  });

  it("keeps a guide the user edited and reports it as skipped", async () => {
    const guides = fakeGuides();
    const t = await setupProvisioner(create, { guides });
    await t.provisioner.ensure("claude");
    await t.put(target("04-limitations.md"), "my notes\n");
    guides.set("04-limitations.md", "newer limitations\n");

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("04-limitations.md")) : undefined;
    expect(outcome).toEqual({ target: target("04-limitations.md"), status: "skipped_user_modified" });
    expect(await t.read(target("04-limitations.md"))).toBe("my notes\n");
    expect((await t.state.load()).provisioned[target("04-limitations.md")]?.hash).toBe(await hashOf("04-limitations.md v1\n"));
  });

  it("keeps an edited license copy and an edited index", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.put(target("LICENSE-papersmith-ai.txt"), "edited license\n");
    await t.put(target("INDEX.md"), "edited index\n");

    const result = await t.provisioner.ensure("claude");

    const skipped = result.ok ? result.value.outcomes.filter((o) => o.status === "skipped_user_modified").map((o) => o.target) : [];
    expect(skipped.sort()).toEqual([target("INDEX.md"), target("LICENSE-papersmith-ai.txt")]);
    expect(await t.read(target("LICENSE-papersmith-ai.txt"))).toBe("edited license\n");
    expect(await t.read(target("INDEX.md"))).toBe("edited index\n");
  });

  it("restores a guide that was deleted", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.fs.rm(`${t.project}/${target("08-abstract.md")}`);

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("08-abstract.md")) : undefined;
    expect(outcome?.status).toBe("created");
    expect(await t.read(target("08-abstract.md"))).toBe("08-abstract.md v1\n");
  });

  it("does not overwrite a file the user created at a guide path that Caztor never wrote", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.put(target("01-materials-and-methods.md"), "written by the user\n");

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("01-materials-and-methods.md")) : undefined;
    expect(outcome?.status).toBe("skipped_user_modified");
    expect(await t.read(target("01-materials-and-methods.md"))).toBe("written by the user\n");
    expect((await t.state.load()).provisioned[target("01-materials-and-methods.md")]).toBeUndefined();
    expect(await t.exists(target("02-experimental-setup.md"))).toBe(true);
  });

  it("adopts an identical file the user placed there, without rewriting it", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.put(target("INDEX.md"), "INDEX.md v1\n");

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("INDEX.md")) : undefined;
    expect(outcome?.status).toBe("unchanged");
    expect((await t.state.load()).provisioned[target("INDEX.md")]?.hash).toBe(await hashOf("INDEX.md v1\n"));
  });

  it("overwrites an edited guide only when the user asks to replace", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.put(target("04-limitations.md"), "my notes\n");

    const result = await t.provisioner.ensure("claude", { replace: true });

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("04-limitations.md")) : undefined;
    expect(outcome?.status).toBe("updated");
    expect(await t.read(target("04-limitations.md"))).toBe("04-limitations.md v1\n");
  });

  it("never writes through a link that sits at a guide path, and reports it as skipped", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.fs.mkdir(`${t.project}/.caztor/guides`, { recursive: true });
    await t.fs.writeFile(`${t.root}/outside.txt`, new TextEncoder().encode("outside"));
    t.symlink(`${t.root}/outside.txt`, `${t.project}/${target("10-back-matter.md")}`);

    const result = await t.provisioner.ensure("claude");

    const outcome = result.ok ? result.value.outcomes.find((o) => o.target === target("10-back-matter.md")) : undefined;
    expect(outcome?.status).toBe("skipped_user_modified");
    expect(new TextDecoder().decode(await t.fs.readFile(`${t.root}/outside.txt`))).toBe("outside");
  });

  it("refuses a guides folder that is a link, writes nothing through it and still prepares the definition", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.fs.mkdir(`${t.project}/.caztor`, { recursive: true });
    await t.fs.mkdir(`${t.root}/elsewhere`);
    t.symlink(`${t.root}/elsewhere`, `${t.project}/.caztor/guides`);

    const result = await t.provisioner.ensure("claude");

    expect(result.ok).toBe(true);
    const outcomes = result.ok ? result.value.outcomes : [];
    expect(outcomes[0]).toEqual({ target: CLAUDE, status: "created" });
    expect(outcomes.at(-1)).toMatchObject({ target: GUIDES_TARGET_DIR, status: "unavailable" });
    expect(outcomes.at(-1)?.detail).toMatch(/guides is a link/);
    expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
  });

  it("reports the guides as unavailable, without failing the turn, when the source fails", async () => {
    const guides = fakeGuides();
    guides.failure = "folder missing";
    const t = await setupProvisioner(create, { guides });

    const result = await t.provisioner.ensure("claude");

    expect(result.ok).toBe(true);
    expect(result.ok && result.value.outcomes).toEqual([
      { target: CLAUDE, status: "created" },
      { target: GUIDES_TARGET_DIR, status: "unavailable", detail: "folder missing" },
    ]);
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
  });

  it("refuses a whole set that contains an invalid name and writes nothing", async () => {
    const guides = fakeGuides();
    guides.set("../escape.md", "bad\n");
    const t = await setupProvisioner(create, { guides });

    const result = await t.provisioner.ensure("claude");

    expect(result.ok && result.value.outcomes.at(-1)).toEqual({
      target: GUIDES_TARGET_DIR,
      status: "unavailable",
      detail: '"../escape.md" is not a valid guide name',
    });
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
    expect(await t.exists("escape.md")).toBe(false);
  });

  it("requires INDEX.md before it writes anything", async () => {
    const guides = fakeGuides();
    guides.drop("INDEX.md");
    const t = await setupProvisioner(create, { guides });

    const result = await t.provisioner.ensure("claude");

    expect(result.ok && result.value.outcomes.at(-1)).toEqual({ target: GUIDES_TARGET_DIR, status: "unavailable", detail: "INDEX.md is missing" });
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
  });

  it("removes a tracked guide that the source no longer ships, but keeps one the user edited", async () => {
    const guides = fakeGuides();
    const t = await setupProvisioner(create, { guides });
    await t.provisioner.ensure("claude");
    await t.put(target("09-title-and-keywords.md"), "my edit\n");
    guides.drop("09-title-and-keywords.md");
    guides.drop("10-back-matter.md");

    const result = await t.provisioner.ensure("claude");

    const outcomes = result.ok ? result.value.outcomes : [];
    expect(outcomes.some((o) => o.target === target("10-back-matter.md"))).toBe(false);
    expect(await t.exists(target("10-back-matter.md"))).toBe(false);
    expect(await t.read(target("09-title-and-keywords.md"))).toBe("my edit\n");
    const tracked = (await t.state.load()).provisioned;
    expect(tracked[target("10-back-matter.md")]).toBeUndefined();
    expect(tracked[target("09-title-and-keywords.md")]).toBeUndefined();
  });

  it("does not look at the guides when no source was configured", async () => {
    const t = await setupProvisioner(create);

    const result = await t.provisioner.ensure("claude");

    expect(result.ok && result.value.outcomes).toEqual([{ target: CLAUDE, status: "created" }]);
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
  });
});
