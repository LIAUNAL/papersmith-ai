import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { ANTIGRAVITY_V1, ANTIGRAVITY_V2, hashOf, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const TARGET = ".agents/agents/caztor.md";

describe.each(implementations)("provisioning the Antigravity definition: %s", (_name, create) => {
  it("creates only .agents/agents/caztor.md (plus the guides), records it and returns the parsed definition", async () => {
    const t = await setupProvisioner(create);
    const result = await t.provisioner.ensure("antigravity");
    expect(result).toMatchObject({
      ok: true,
      value: {
        outcomes: expect.arrayContaining([{ target: TARGET, status: "created" }]),
        agent: { hash: await hashOf(ANTIGRAVITY_V1), name: "caztor", description: "Test antigravity agent", tools: ["view_file", "list_dir", "replace_file_content"], prompt: "Antigravity prompt." },
      },
    });
    expect(await t.read(TARGET)).toBe(ANTIGRAVITY_V1);
    expect(await t.exists(".claude")).toBe(false);
    expect(await t.exists(".opencode")).toBe(false);
    expect(await t.exists("AGENTS.md")).toBe(false);
    expect(await t.names(".agents")).toEqual(["agents"]);
    expect((await t.state.load()).provisioned[TARGET]).toEqual({ hash: await hashOf(ANTIGRAVITY_V1), createdByCaztor: true });
  });

  it("is idempotent and updates an untouched copy when the shipped definition changes", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("antigravity");
    const again = await t.provisioner.ensure("antigravity");
    expect(again.ok && again.value.outcomes).toContainEqual({ target: TARGET, status: "unchanged" });
    await t.publish("antigravity", ANTIGRAVITY_V2);
    const updated = await t.provisioner.ensure("antigravity");
    expect(updated.ok && updated.value.outcomes).toContainEqual({ target: TARGET, status: "updated" });
    expect(await t.read(TARGET)).toBe(ANTIGRAVITY_V2);
  });

  it("leaves a file the user edited unchanged and reports it as skipped, until replace is asked for", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("antigravity");
    await t.put(TARGET, "my own agent\n");
    const skipped = await t.provisioner.ensure("antigravity");
    expect(skipped.ok && skipped.value.outcomes).toContainEqual({ target: TARGET, status: "skipped_user_modified" });
    expect(await t.read(TARGET)).toBe("my own agent\n");
    const replaced = await t.provisioner.ensure("antigravity", { replace: true });
    expect(replaced.ok && replaced.value.outcomes).toContainEqual({ target: TARGET, status: "updated" });
    expect(await t.read(TARGET)).toBe(ANTIGRAVITY_V1);
  });

  it("removes the file it created, and the folders it leaves empty, but not one the user edited", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("antigravity");
    const removed = await t.provisioner.remove("antigravity");
    expect(removed.ok && removed.value.outcomes).toContainEqual({ target: TARGET, status: "removed" });
    expect(await t.exists(".agents")).toBe(false);

    await t.provisioner.ensure("antigravity");
    await t.put(TARGET, "mine\n");
    const kept = await t.provisioner.remove("antigravity");
    expect(kept.ok && kept.value.outcomes).toContainEqual({ target: TARGET, status: "skipped_user_modified" });
    expect(await t.read(TARGET)).toBe("mine\n");
  });

  it("does not write through a link at .agents", async () => {
    const t = await setupProvisioner(create);
    await t.fs.mkdir(`${t.root}/elsewhere`, { recursive: true });
    t.symlink(`${t.root}/elsewhere`, `${t.project}/.agents`);
    const result = await t.provisioner.ensure("antigravity");
    expect(result.ok).toBe(false);
    expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
  });
});
