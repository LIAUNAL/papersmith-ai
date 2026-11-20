import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { hashOf, implementations, PI_V1, PI_V2, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const TARGET = ".caztor/agents/pi.md";

describe.each(implementations)("provisioning the Pi system prompt: %s", (_name, create) => {
  it("creates only .caztor/agents/pi.md (plus the guides), never .pi/, records it and returns the parsed definition", async () => {
    const t = await setupProvisioner(create);
    const result = await t.provisioner.ensure("pi");
    expect(result).toMatchObject({
      ok: true,
      value: {
        outcomes: expect.arrayContaining([{ target: TARGET, status: "created" }]),
        agent: { hash: await hashOf(PI_V1), name: "caztor", tools: [], prompt: "# Test Pi agent\n\nPi system prompt, first version." },
      },
    });
    expect(await t.read(TARGET)).toBe(PI_V1);
    for (const other of [".pi", ".claude", ".opencode", ".agents", "AGENTS.md"]) expect(await t.exists(other), other).toBe(false);
    expect(await t.names(".caztor/agents")).toEqual(["pi.md"]);
    expect((await t.state.load()).provisioned[TARGET]).toEqual({ hash: await hashOf(PI_V1), createdByCaztor: true });
  });

  it("is idempotent and updates an untouched copy when the shipped prompt changes", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("pi");
    const again = await t.provisioner.ensure("pi");
    expect(again.ok && again.value.outcomes).toContainEqual({ target: TARGET, status: "unchanged" });
    await t.publish("pi", PI_V2);
    const updated = await t.provisioner.ensure("pi");
    expect(updated.ok && updated.value.outcomes).toContainEqual({ target: TARGET, status: "updated" });
    expect(await t.read(TARGET)).toBe(PI_V2);
  });

  it("removes the file it created and its emptied folder, and keeps the rest of .caztor", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("pi");
    await t.put(".caztor/keep.txt", "x\n");
    const removed = await t.provisioner.remove("pi");
    expect(removed.ok && removed.value.outcomes).toContainEqual({ target: TARGET, status: "removed" });
    expect(await t.exists(".caztor/agents")).toBe(false);
    expect(await t.read(".caztor/keep.txt")).toBe("x\n");
  });

  it("does not write through a link at .caztor/agents", async () => {
    const t = await setupProvisioner(create);
    await t.fs.mkdir(`${t.root}/elsewhere`, { recursive: true });
    await t.fs.mkdir(`${t.project}/.caztor`, { recursive: true });
    t.symlink(`${t.root}/elsewhere`, `${t.project}/.caztor/agents`);
    const result = await t.provisioner.ensure("pi");
    expect(result.ok).toBe(false);
    expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
  });
});
