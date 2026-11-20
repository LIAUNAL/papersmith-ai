import { AGENT_BLOCK_BEGIN as BEGIN, AGENT_BLOCK_END as END } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createAgentsMdVisibility } from "../../src/agents-md.ts";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { CODEX_V1, CODEX_V2, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

const block = (body: string) => `${BEGIN}\n${body.trimEnd()}\n${END}\n`;

describe.each(implementations)("the AGENTS.md block is only ever Caztor's own text: %s", (_name, create) => {
  describe("text between a pair of markers that Caztor did not write", () => {
    it("is kept when no record says the block is Caztor's", async () => {
      const t = await setupProvisioner(create);
      const mine = `# Mine\n\n${BEGIN}\nmy own rules, in my own markers\n${END}\n`;
      await t.put("AGENTS.md", mine);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
      expect(await t.read("AGENTS.md")).toBe(mine);
    });

    it("is kept when the user edited the block after Caztor wrote it, and the shipped text changed meanwhile", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      const edited = (await t.read("AGENTS.md")).replace("first version", "first version, plus my own line");
      await t.put("AGENTS.md", edited);
      await t.publish("codex", CODEX_V2);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
      expect(await t.read("AGENTS.md")).toBe(edited);
    });

    it("is replaced when the user asks to replace the definition", async () => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", `${BEGIN}\nmy own rules\n${END}\n`);

      const result = await t.provisioner.ensure("codex", { replace: true });

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "updated" }]);
      expect(await t.read("AGENTS.md")).toBe(block(CODEX_V1));
    });

    it("still updates the block Caztor wrote when the shipped text changes", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      await t.publish("codex", CODEX_V2);

      const result = await t.provisioner.ensure("codex");

      expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "updated" }]);
      expect(await t.read("AGENTS.md")).toBe(block(CODEX_V2));
    });
  });

  describe("removal is byte-exact", () => {
    it.each([
      ["no final newline", "no final newline"],
      ["one final newline", "one final newline\n"],
      ["a blank line at the end", "blank line at the end\n\n"],
      ["Windows line breaks", "windows\r\n"],
      ["text that is only a newline", "\n"],
    ])("gives back a file with %s exactly as it was", async (_label, original) => {
      const t = await setupProvisioner(create);
      await t.put("AGENTS.md", original);
      await t.provisioner.ensure("codex");
      expect(await t.read("AGENTS.md")).toContain(BEGIN);

      await t.provisioner.remove("codex");

      expect(await t.read("AGENTS.md")).toBe(original);
    });
  });

  describe("what the file API shows", () => {
    const listed = async (t: Awaited<ReturnType<typeof setupProvisioner>>) => (await t.store.list()).map((entry) => entry.path);
    const visibility = (t: Awaited<ReturnType<typeof setupProvisioner>>) => createAgentsMdVisibility({ fs: t.fs, root: t.project, state: t.state });

    it("hides a file that still holds exactly Caztor's block", async () => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      expect(await visibility(t)()).toBe(true);
    });

    it.each([
      ["rewritten completely", () => "# Written elsewhere\n"],
      ["given a line above", (current: string) => `# Added\n\n${current}`],
      ["given a line below", (current: string) => `${current}\nAdded below\n`],
      ["edited inside the block", (current: string) => current.replace("first version", "first version, edited")],
      ["emptied", () => ""],
    ])("shows the file at once when the user %s outside the app", async (_label, change) => {
      const t = await setupProvisioner(create);
      await t.provisioner.ensure("codex");
      await t.put("AGENTS.md", change(await t.read("AGENTS.md")));

      expect(await visibility(t)()).toBe(false);
    });

    it("shows a file that is missing, and one Caztor did not create", async () => {
      const t = await setupProvisioner(create);
      expect(await visibility(t)()).toBe(false);
      await t.put("AGENTS.md", "# Mine\n");
      await t.provisioner.ensure("codex");
      expect(await visibility(t)()).toBe(false);
      expect(await listed(t)).toEqual(["AGENTS.md"]);
    });
  });
});
