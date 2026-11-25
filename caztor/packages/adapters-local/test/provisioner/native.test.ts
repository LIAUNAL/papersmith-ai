import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { CLAUDE_V1, CLAUDE_V2, decode, hashOf, implementations, OPENCODE_V1, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const TARGET = ".claude/agents/caztor.md";

describe.each(implementations)("provisioning a native definition: %s", (_name, create) => {
  it("creates the definition, records its hash and returns the definition that is present", async () => {
    const t = await setupProvisioner(create);

    const result = await t.provisioner.ensure("claude");

    expect(result).toEqual({
      ok: true,
      value: {
        outcomes: [{ target: TARGET, status: "created" }],
        agent: {
          hash: await hashOf(CLAUDE_V1),
          name: "caztor",
          description: "Test agent",
          prompt: "Claude prompt, first version.",
          tools: ["Read", "Edit"],
        },
      },
    });
    expect(await t.read(TARGET)).toBe(CLAUDE_V1);
    expect((await t.fs.stat(`${t.project}/${TARGET}`)).mode).toBe(0o644);
    expect((await t.state.load()).provisioned).toEqual({ [TARGET]: { hash: await hashOf(CLAUDE_V1), createdByCaztor: true } });
  });

  it("writes only the definition of the provider whose turn is starting", async () => {
    const t = await setupProvisioner(create);

    await t.provisioner.ensure("opencode");

    expect(await t.exists(".opencode/agents/caztor.md")).toBe(true);
    expect(await t.exists(".claude")).toBe(false);
    expect(await t.exists("AGENTS.md")).toBe(false);
    const result = await t.provisioner.ensure("opencode");
    expect(result.ok && result.value.agent).toMatchObject({ name: "caztor", description: "Test opencode agent", tools: ["edit"] });
  });

  it("changes nothing when it runs again", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("claude");
    const before = await t.fs.stat(`${t.project}/${TARGET}`);

    const again = await t.provisioner.ensure("claude");

    expect(again.ok && again.value.outcomes).toEqual([{ target: TARGET, status: "unchanged" }]);
    expect((await t.fs.stat(`${t.project}/${TARGET}`)).mtimeMs).toBe(before.mtimeMs);
    expect(await t.names(".claude/agents")).toEqual(["caztor.md"]);
  });

  it("updates a copy the user did not touch when the shipped definition changes", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("claude");
    await t.publish("claude", CLAUDE_V2);

    const result = await t.provisioner.ensure("claude");

    expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "updated" }]);
    expect(result.ok && result.value.agent.hash).toBe(await hashOf(CLAUDE_V2));
    expect(await t.read(TARGET)).toBe(CLAUDE_V2);
    expect((await t.state.load()).provisioned[TARGET]).toEqual({ hash: await hashOf(CLAUDE_V2), createdByCaztor: true });
  });

  it("keeps the permission bits of the file it updates", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("claude");
    await t.fs.chmod(`${t.project}/${TARGET}`, 0o640);
    await t.publish("claude", CLAUDE_V2);
    await t.provisioner.ensure("claude");
    expect((await t.fs.stat(`${t.project}/${TARGET}`)).mode).toBe(0o640);
  });

  describe("a file the user changed or wrote", () => {
    it("is left as it is and reported as skipped when the user edited the provisioned copy", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("claude");
      await t.put(TARGET, `${CLAUDE_V1}\nMy own rule.\n`);
      await t.publish("claude", CLAUDE_V2);

      const result = await t.provisioner.ensure("claude");

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "skipped_user_modified" }]);
      expect(await t.read(TARGET)).toBe(`${CLAUDE_V1}\nMy own rule.\n`);
      expect(result.ok && result.value.agent.hash).toBe(await hashOf(`${CLAUDE_V1}\nMy own rule.\n`));
      expect((await t.state.load()).provisioned[TARGET]?.hash).toBe(await hashOf(CLAUDE_V1));
    });

    it("is left as it is when it was written by the user and Caztor never recorded it", async () => {
      const t = await setupProvisioner(create);
      await t.put(TARGET, "---\nname: caztor\ndescription: Mine\n---\nMy agent.\n");

      const result = await t.provisioner.ensure("claude");

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "skipped_user_modified" }]);
      expect(await t.read(TARGET)).toContain("My agent.");
      expect((await t.state.load()).provisioned).toEqual({});
    });

    it("is overwritten only by an explicit replace", async () => {
      const t = await setupProvisioner(create);
      await t.put(TARGET, "---\nname: caztor\ndescription: Mine\n---\nMy agent.\n");
      await t.provisioner.ensure("claude");

      const result = await t.provisioner.ensure("claude", { replace: true });

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "updated" }]);
      expect(await t.read(TARGET)).toBe(CLAUDE_V1);
      expect((await t.state.load()).provisioned[TARGET]?.hash).toBe(await hashOf(CLAUDE_V1));

      await t.put(TARGET, `${CLAUDE_V1}edited\n`);
      expect((await t.provisioner.ensure("claude")).ok && true).toBe(true);
      expect(await t.read(TARGET)).toBe(`${CLAUDE_V1}edited\n`);
    });

    it("does not overwrite when replace is asked for but the file already is the shipped one", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("claude");
      const result = await t.provisioner.ensure("claude", { replace: true });
      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "unchanged" }]);
    });
  });

  describe("lost or stale records", () => {
    it("adopts a file that equals the shipped definition when the state was lost", async () => {
      const t = await setupProvisioner(create);
      await t.put(TARGET, CLAUDE_V1);

      const result = await t.provisioner.ensure("claude");

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "unchanged" }]);
      expect((await t.state.load()).provisioned[TARGET]).toEqual({ hash: await hashOf(CLAUDE_V1), createdByCaztor: true });
    });

    it("re-adopts a file the user changed back to the shipped definition", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("claude");
      await t.put(TARGET, "something else\n");
      await t.put(TARGET, CLAUDE_V1);
      await t.publish("claude", CLAUDE_V2);
      await t.put(TARGET, CLAUDE_V2);

      const result = await t.provisioner.ensure("claude");

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "unchanged" }]);
      expect((await t.state.load()).provisioned[TARGET]?.hash).toBe(await hashOf(CLAUDE_V2));
    });

    it("creates the file again when the user deleted it", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("claude");
      await t.fs.rm(`${t.project}/${TARGET}`);

      const result = await t.provisioner.ensure("claude");

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "created" }]);
      expect(await t.read(TARGET)).toBe(CLAUDE_V1);
    });
  });

  describe("containment", () => {
    it("refuses a .claude folder that is a link leading out of the project, and writes nothing outside", async () => {
      const t = await setupProvisioner(create);
      await t.fs.mkdir(`${t.root}/elsewhere`, { recursive: true });
      t.symlink(`${t.root}/elsewhere`, `${t.project}/.claude`);

      const result = await t.provisioner.ensure("claude");

      expect(result.ok).toBe(false);
      expect(!result.ok && result.error.message).toContain(".claude");
      expect(await t.fs.readdir(`${t.root}/elsewhere`)).toEqual([]);
      expect((await t.state.load()).provisioned).toEqual({});
    });

    it("refuses an agents folder that is a link, even when the link stays inside the project", async () => {
      const t = await setupProvisioner(create);
      await t.fs.mkdir(`${t.project}/.opencode`, { recursive: true });
      await t.fs.mkdir(`${t.project}/real-agents`, { recursive: true });
      t.symlink(`${t.project}/real-agents`, `${t.project}/.opencode/agents`);

      const result = await t.provisioner.ensure("opencode");

      expect(result.ok).toBe(false);
      expect(await t.names("real-agents")).toEqual([]);
    });

    it("refuses a .claude entry that is a file", async () => {
      const t = await setupProvisioner(create);
      await t.put(".claude", "not a folder");
      const result = await t.provisioner.ensure("claude");
      expect(result.ok).toBe(false);
      expect(await t.read(".claude")).toBe("not a folder");
    });

    it("treats a definition that is a link as the user's own and never writes through it", async () => {
      const t = await setupProvisioner(create);
      await t.fs.writeFile(`${t.root}/secret.md`, new TextEncoder().encode("outside secret"));
      await t.fs.mkdir(`${t.project}/.claude/agents`, { recursive: true });
      t.symlink(`${t.root}/secret.md`, `${t.project}/${TARGET}`);

      const result = await t.provisioner.ensure("claude", { replace: true });

      expect(result.ok && result.value.outcomes).toEqual([{ target: TARGET, status: "skipped_user_modified" }]);
      expect(decode(await t.fs.readFile(`${t.root}/secret.md`))).toBe("outside secret");
    });
  });

  describe("failures", () => {
    it("reports a missing shipped definition", async () => {
      const t = await setupProvisioner(create);
      await t.fs.rm(`${t.agentsDir}/claude.md`);
      const result = await t.provisioner.ensure("claude");
      expect(result.ok).toBe(false);
      expect(!result.ok && result.error.message).toContain("claude");
      expect(await t.exists(".claude")).toBe(false);
    });

    it("leaves no partial file when the write fails", async () => {
      const t = await setupProvisioner(create, {
        hooks: {
          writeFile: (path) => {
            if (path.includes(".claude")) throw Object.assign(new Error("ENOSPC: no space left on device"), { code: "ENOSPC" });
          },
        },
      });

      const result = await t.provisioner.ensure("claude");

      expect(result.ok).toBe(false);
      expect(!result.ok && result.error.message).toContain("ENOSPC");
      expect(await t.names(".claude/agents")).toEqual([]);
      expect((await t.state.load()).provisioned).toEqual({});
    });

    it("lets two calls at once end with one file and one record", async () => {
      const t = await setupProvisioner(create);
      const [first, second] = await Promise.all([t.provisioner.ensure("claude"), t.provisioner.ensure("claude")]);
      const statuses = [first, second].map((result) => (result.ok ? result.value.outcomes[0]?.status : "error")).sort();
      expect(statuses).toEqual(["created", "unchanged"]);
      expect(await t.names(".claude/agents")).toEqual(["caztor.md"]);
    });
  });

  it("falls back to the shipped fields, with the hash of the present file, when the user's copy cannot be parsed", async () => {
    const t = await setupProvisioner(create);
    await t.put(".opencode/agents/caztor.md", "no frontmatter at all\n");
    const result = await t.provisioner.ensure("opencode");
    expect(result.ok && result.value.outcomes[0]?.status).toBe("skipped_user_modified");
    expect(result.ok && result.value.agent).toMatchObject({ hash: await hashOf("no frontmatter at all\n"), name: "caztor", tools: ["edit"], description: "Test opencode agent" });
    expect(OPENCODE_V1).toContain("Opencode prompt.");
  });
});
