import { AGENT_BLOCK_BEGIN as BEGIN, AGENT_BLOCK_END as END } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { cleanupSandboxes } from "../support/fs-sandbox.ts";
import { treeOf } from "../snapshot/support.ts";
import { CLAUDE_V1, implementations, setupProvisioner } from "./support.ts";

cleanupSandboxes();

describe.each(implementations)("removing provisioned definitions: %s", (_name, create) => {
  it("deletes an unmodified native definition and the folders that only held it, and forgets the record", async () => {
    const t = await setupProvisioner(create);
    await t.put("main.tex", "keep me");
    await t.provisioner.ensure("claude");

    const result = await t.provisioner.remove("claude");

    expect(result).toEqual({ ok: true, value: { outcomes: [{ target: ".claude/agents/caztor.md", status: "removed" }] } });
    expect(await t.names()).toEqual([".caztor", "main.tex"]);
    expect((await t.state.load()).provisioned).toEqual({});
  });

  it("leaves other files in the same folders, and the folders, alone", async () => {
    const t = await setupProvisioner(create);
    await t.put(".claude/settings.json", "{}");
    await t.put(".claude/agents/mine.md", "my agent");
    await t.provisioner.ensure("claude");

    await t.provisioner.remove("claude");

    expect(await t.names(".claude")).toEqual(["agents", "settings.json"]);
    expect(await t.names(".claude/agents")).toEqual(["mine.md"]);
  });

  it("keeps a native definition the user changed and reports it", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("claude");
    await t.put(".claude/agents/caztor.md", `${CLAUDE_V1}my edit\n`);

    const result = await t.provisioner.remove("claude");

    expect(result.ok && result.value.outcomes).toEqual([{ target: ".claude/agents/caztor.md", status: "skipped_user_modified" }]);
    expect(await t.read(".claude/agents/caztor.md")).toBe(`${CLAUDE_V1}my edit\n`);
    expect((await t.state.load()).provisioned[".claude/agents/caztor.md"]).toBeDefined();
  });

  it("does nothing for a definition that was never provisioned", async () => {
    const t = await setupProvisioner(create);
    await t.put(".claude/agents/caztor.md", "the user's own agent");
    const result = await t.provisioner.remove("claude");
    expect(result.ok && result.value.outcomes).toEqual([{ target: ".claude/agents/caztor.md", status: "unchanged" }]);
    expect(await t.read(".claude/agents/caztor.md")).toBe("the user's own agent");
  });

  it("deletes an AGENTS.md that Caztor created and holds nothing else", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("codex");

    const result = await t.provisioner.remove("codex");

    expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "removed" }]);
    expect(await t.exists("AGENTS.md")).toBe(false);
    expect((await t.state.load()).provisioned).toEqual({});
  });

  it.each([
    ["ends with a line break", "# Mine\n\nRule one.\n"],
    ["has a blank line at the end", "# Mine\n\nRule one.\n\n"],
    ["uses Windows line breaks", "# Mine\r\n\r\nRule one.\r\n"],
  ])("takes only the block out of a user's AGENTS.md that %s, leaving it as it was", async (_label, original) => {
    const t = await setupProvisioner(create);
    await t.put("AGENTS.md", original);
    await t.provisioner.ensure("codex");

    const result = await t.provisioner.remove("codex");

    expect(result.ok && result.value.outcomes).toEqual([{ target: "AGENTS.md", status: "removed" }]);
    expect(await t.read("AGENTS.md")).toBe(original);
    expect((await t.state.load()).provisioned).toEqual({});
  });

  it("keeps the text on both sides of a block that sits in the middle of the file", async () => {
    const t = await setupProvisioner(create);
    await t.put("AGENTS.md", `# Above\n\n${BEGIN}\nold\n${END}\n\n# Below\n`);
    await t.provisioner.remove("codex");
    expect(await t.read("AGENTS.md")).toBe("# Above\n\n\n# Below\n");
  });

  it("keeps the file, without the block, once the user added their own text to a file Caztor created", async () => {
    const t = await setupProvisioner(create);
    await t.provisioner.ensure("codex");
    await t.put("AGENTS.md", `# Added later\n\n${await t.read("AGENTS.md")}`);

    await t.provisioner.remove("codex");

    // The blank line that separated a trailing block from the text above it goes with the block.
    expect(await t.read("AGENTS.md")).toBe("# Added later\n");
  });

  it("does nothing when AGENTS.md has no block, and refuses markers it cannot trust", async () => {
    const t = await setupProvisioner(create);
    await t.put("AGENTS.md", "# Plain\n");
    const none = await t.provisioner.remove("codex");
    expect(none.ok && none.value.outcomes).toEqual([{ target: "AGENTS.md", status: "unchanged" }]);
    expect(await t.read("AGENTS.md")).toBe("# Plain\n");

    await t.put("AGENTS.md", `${BEGIN}\nunfinished\n`);
    const broken = await t.provisioner.remove("codex");
    expect(broken.ok && broken.value.outcomes).toEqual([{ target: "AGENTS.md", status: "skipped_user_modified" }]);
    expect(await t.read("AGENTS.md")).toBe(`${BEGIN}\nunfinished\n`);
  });

  it("puts the project back exactly as it was after provisioning every provider and removing them", async () => {
    const t = await setupProvisioner(create);
    await t.put("main.tex", "\\documentclass{article}");
    await t.put("sections/intro.tex", "intro");
    await t.put("AGENTS.md", "# My project rules\n\nUse British spelling.\n");
    await t.put(".claude/settings.json", "{\"hooks\": {}}");
    const before = await treeOf(t);
    const foldersBefore = await t.names();

    for (const provider of ["claude", "opencode", "codex"] as const) await t.provisioner.ensure(provider);
    expect(await treeOf(t)).not.toEqual(before);
    for (const provider of ["claude", "opencode", "codex"] as const) await t.provisioner.remove(provider);

    expect(await treeOf(t)).toEqual(before);
    expect((await t.names()).filter((name) => name !== ".caztor")).toEqual(foldersBefore);
    expect(await t.names(".claude")).toEqual(["settings.json"]);
  });
});
