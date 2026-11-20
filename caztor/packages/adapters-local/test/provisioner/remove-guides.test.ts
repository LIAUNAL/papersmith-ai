import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { fakeGuides, GUIDE_NAMES, GUIDES_TARGET_DIR, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const target = (name: string) => `${GUIDES_TARGET_DIR}/${name}`;
const guideEntries = (provisioned: Record<string, unknown>) => Object.keys(provisioned).filter((key) => key.startsWith(`${GUIDES_TARGET_DIR}/`));

describe.each(implementations)("removing the writing guides: %s", (_name, create) => {
  it("deletes all twelve unmodified files with the last definition, then the empty folder, and leaves other files", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.put("main.tex", "keep me");
    await t.provisioner.ensure("claude");

    const result = await t.provisioner.remove("claude");

    const outcomes = result.ok ? result.value.outcomes : [];
    expect(outcomes[0]).toEqual({ target: ".claude/agents/caztor.md", status: "removed" });
    expect(outcomes.slice(1).map((o) => o.status)).toEqual(Array(12).fill("removed"));
    expect(outcomes.slice(1).map((o) => o.target).sort()).toEqual(GUIDE_NAMES.map(target).sort());
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
    expect(await t.names()).toEqual([".caztor", "main.tex"]);
    expect((await t.state.load()).provisioned).toEqual({});
  });

  it("keeps the guides while another provider's definition is still provisioned", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.provisioner.ensure("opencode");

    const first = await t.provisioner.remove("claude");
    expect(first.ok && first.value.outcomes).toEqual([{ target: ".claude/agents/caztor.md", status: "removed" }]);
    expect(await t.names(GUIDES_TARGET_DIR)).toEqual([...GUIDE_NAMES].sort());

    const second = await t.provisioner.remove("opencode");
    expect(second.ok && second.value.outcomes).toHaveLength(13);
    expect(await t.exists(GUIDES_TARGET_DIR)).toBe(false);
  });

  it("keeps a guide the user edited, and the license copy when it was edited, and the folder that holds them", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.put(target("03-results-and-discussion.md"), "my results notes\n");
    await t.put(target("LICENSE-papersmith-ai.txt"), "my license edit\n");

    const result = await t.provisioner.remove("claude");

    const outcomes = result.ok ? result.value.outcomes : [];
    expect(outcomes.filter((o) => o.status === "skipped_user_modified").map((o) => o.target).sort()).toEqual([
      target("03-results-and-discussion.md"),
      target("LICENSE-papersmith-ai.txt"),
    ]);
    expect(await t.names(GUIDES_TARGET_DIR)).toEqual(["03-results-and-discussion.md", "LICENSE-papersmith-ai.txt"]);
    expect(await t.read(target("03-results-and-discussion.md"))).toBe("my results notes\n");
    expect(guideEntries((await t.state.load()).provisioned)).toEqual([]);
  });

  it("leaves a file the user put at a guide path that Caztor never wrote", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.put(target("INDEX.md"), "the user's index\n");
    await t.provisioner.ensure("claude");

    await t.provisioner.remove("claude");

    expect(await t.names(GUIDES_TARGET_DIR)).toEqual(["INDEX.md"]);
    expect(await t.read(target("INDEX.md"))).toBe("the user's index\n");
  });

  it("does nothing to the guides when none were provisioned", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("claude");

    const result = await t.provisioner.remove("claude");

    expect(result.ok && result.value.outcomes).toEqual([{ target: ".claude/agents/caztor.md", status: "removed" }]);
  });

  it("does not delete through a link that replaced the guides folder", async () => {
    const t = await setupProvisioner(create, { guides: fakeGuides() });
    await t.provisioner.ensure("claude");
    await t.fs.mkdir(`${t.root}/elsewhere`);
    await t.fs.writeFile(`${t.root}/elsewhere/INDEX.md`, new TextEncoder().encode("INDEX.md v1\n"));
    await t.fs.rm(`${t.project}/${GUIDES_TARGET_DIR}`, { recursive: true });
    t.symlink(`${t.root}/elsewhere`, `${t.project}/${GUIDES_TARGET_DIR}`);

    const result = await t.provisioner.remove("claude");

    expect(result.ok).toBe(false);
    expect(await t.fs.readdir(`${t.root}/elsewhere`)).toHaveLength(1);
  });
});
