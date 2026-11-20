import { AGENT_BLOCK_BEGIN as BEGIN, AGENT_BLOCK_END as END } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { CODEX_V1, CODEX_V2, encode, hashOf, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const block = (body: string) => `${BEGIN}\n${body.trimEnd()}\n${END}\n`;

describe.each(implementations)("provisioning the AGENTS.md block: %s", (_name, create) => {
  it("creates AGENTS.md holding only the block, records that Caztor created it, and returns the instructions", async () => {
    const t = await setupProvisioner(create);

    const result = await t.provisioner.ensure("codex");

    expect(result).toEqual({
      ok: true,
      value: {
        outcomes: [{ target: "AGENTS.md", status: "created" }],
        agent: {
          hash: await hashOf(CODEX_V1),
          name: "caztor",
          description: "Caztor academic writing instructions",
          prompt: CODEX_V1.trim(),
          tools: [],
        },
      },
    });
    expect(await t.read("AGENTS.md")).toBe(block(CODEX_V1));
    expect((await t.state.load()).provisioned["AGENTS.md"]).toEqual({ hash: await hashOf(CODEX_V1), createdByCaztor: true });
    expect(await t.exists(".claude")).toBe(false);
  });

  it("hides the AGENTS.md it created from the file tree and shows one the user wrote", async () => {
    const created = await setupProvisioner(create);
    await created.put("main.tex", "x");
    await created.provisioner.ensure("codex");
    expect((await created.store.list()).map((entry) => entry.path)).toEqual(["main.tex"]);

    const authored = await setupProvisioner(create);
    await authored.put("AGENTS.md", "# Mine\n");
    await authored.provisioner.ensure("codex");
    expect((await authored.store.list()).map((entry) => entry.path)).toEqual(["AGENTS.md"]);
  });

  describe("an AGENTS.md the user wrote", () => {
    it("receives the block after their content, which is kept byte for byte", async () => {
      const t = await setupProvisioner(create);
      const mine = "# My rules\r\n\r\nBe  kind.\t\n\n\nTrailing blank lines above.\n";
      await t.put("AGENTS.md", mine);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "created" }]);
      const text = await t.read("AGENTS.md");
      expect(text.startsWith(mine)).toBe(true);
      expect(text).toBe(`${mine}\n${block(CODEX_V1)}`);
      expect((await t.state.load()).provisioned["AGENTS.md"]).toEqual({ hash: await hashOf(CODEX_V1), createdByCaztor: false });
    });

    it("gets a line break first when its last line has none", async () => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", "no final newline");
      await t.provisioner.ensure("codex");
      expect(await t.read("AGENTS.md")).toBe(`no final newline\n\n${block(CODEX_V1).trimEnd()}`);
    });

    it("replaces only the block when the shipped text changes, keeping what is above and below it", async () => {
      const t = await setupProvisioner(create);
      const above = "# Above\n\nRule one.\n\n";
      const below = "\n## Below\n\nRule two.\r\nno final newline";
      await t.put("AGENTS.md", `${above}${block("Older instructions\nwith two lines")}${below}`);
      await t.state.update({ provisioned: { "AGENTS.md": { hash: await hashOf("Older instructions\nwith two lines\n"), createdByCaztor: false } } });
      await t.publish("codex", CODEX_V2);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "updated" }]);
      expect(await t.read("AGENTS.md")).toBe(`${above}${block(CODEX_V2)}${below}`);
      expect((await t.state.load()).provisioned["AGENTS.md"]?.hash).toBe(await hashOf(CODEX_V2));
    });

    it("keeps what the user wrote inside the block and reports it, and puts the shipped text back when asked to replace it", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      await t.put("AGENTS.md", `# Mine\n\n${block("I edited the managed text")}`);

      const kept = await t.provisioner.ensure("codex");

      expect(kept.ok && kept.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
      expect(await t.read("AGENTS.md")).toBe(`# Mine\n\n${block("I edited the managed text")}`);
      const replaced = await t.provisioner.ensure("codex", { replace: true });
      expect(replaced.ok && replaced.value.outcomes).toEqual([{ target: "AGENTS.md", status: "updated" }]);
      expect(await t.read("AGENTS.md")).toBe(`# Mine\n\n${block(CODEX_V1)}`);
    });

    it("changes nothing when it runs again", async () => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", "# Mine\n");
      await t.provisioner.ensure("codex");
      const first = await t.read("AGENTS.md");
      const stats = await t.fs.stat(`${t.project}/AGENTS.md`);

      const again = await t.provisioner.ensure("codex");

      expect(again.ok && again.value.outcomes).toEqual([{ target: "AGENTS.md", status: "unchanged" }]);
      expect(await t.read("AGENTS.md")).toBe(first);
      expect((await t.fs.stat(`${t.project}/AGENTS.md`)).mtimeMs).toBe(stats.mtimeMs);
      expect(first.split(BEGIN)).toHaveLength(2);
    });

    it("keeps the permission bits of the file it rewrites", async () => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", "# Mine\n");
      await t.fs.chmod(`${t.project}/AGENTS.md`, 0o600);
      await t.provisioner.ensure("codex");
      expect((await t.fs.stat(`${t.project}/AGENTS.md`)).mode).toBe(0o600);
    });
  });

  describe("markers that cannot be trusted", () => {
    it.each([
      ["a begin marker with no end", `# Mine\n${BEGIN}\nhalf a block\n`],
      ["an end marker before the begin marker", `${END}\n${BEGIN}\n`],
      ["two blocks", `${block("one")}${block("two")}`],
      ["an end marker with no begin", `# Mine\n${END}\n`],
    ])("leaves a file with %s untouched and reports it", async (_label, content) => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", content);

      const result = await t.provisioner.ensure("codex", { replace: true });

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
      expect(await t.read("AGENTS.md")).toBe(content);
    });
  });

  describe("who owns the file", () => {
    it("stops hiding a file that Caztor created once the user adds their own content to it", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      expect((await t.state.load()).provisioned["AGENTS.md"]?.createdByCaztor).toBe(true);
      await t.put("AGENTS.md", `# My own notes\n\n${await t.read("AGENTS.md")}`);

      await t.provisioner.ensure("codex");

      expect((await t.state.load()).provisioned["AGENTS.md"]?.createdByCaztor).toBe(false);
      expect((await t.store.list()).map((entry) => entry.path)).toEqual(["AGENTS.md"]);
    });

    it("updates a file it created, which the file API hides", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      await t.publish("codex", CODEX_V2);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "updated" }]);
      expect(await t.read("AGENTS.md")).toBe(block(CODEX_V2));
    });

    it("recreates the file it created when the user deleted it", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      await t.fs.rm(`${t.project}/AGENTS.md`);
      const result = await t.provisioner.ensure("codex");
      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "created" }]);
      expect(await t.read("AGENTS.md")).toBe(block(CODEX_V1));
    });

    it("does not follow an AGENTS.md that is a link leading out of the project", async () => {
      const t = await setupProvisioner(create);
      await t.fs.writeFile(`${t.root}/secret.md`, encode("outside secret"));
      t.symlink(`${t.root}/secret.md`, `${t.project}/AGENTS.md`);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
      expect(new TextDecoder().decode(await t.fs.readFile(`${t.root}/secret.md`))).toBe("outside secret");
    });
  });

  it("does not overwrite a save the user makes while the block is being added", async () => {
    let reads = 0;
    let injected = false;
    const t = await setupProvisioner(create, {
      hooks: {
        readFile: async (path) => {
          if (!path.endsWith("/AGENTS.md")) return;
          reads += 1;
          // The first read is the provisioner's own; the second is the store checking the hash it was given.
          if (reads === 2 && !injected) {
            injected = true;
            await t.fs.writeFile(path, encode("# The user saved this meanwhile\n"));
          }
        },
      },
    });
    await t.put("AGENTS.md", "# Original\n");

    const result = await t.provisioner.ensure("codex");

    expect(result.ok).toBe(false);
    expect(!result.ok && result.error.message).toMatch(/changed/i);
    expect(await t.read("AGENTS.md")).toBe("# The user saved this meanwhile\n");

    const retry = await t.provisioner.ensure("codex");
    expect(retry.ok && retry.value.outcomes[0]?.status).toBe("created");
    expect(await t.read("AGENTS.md")).toBe(`# The user saved this meanwhile\n\n${block(CODEX_V1)}`);
  });
});
