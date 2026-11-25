import type { GuideDocument, GuideSourcePort } from "@caztor/core";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { chatHarness, cleanupChatProjects, type ChatHarness, type Frame } from "./chat-support.ts";

cleanupChatProjects();

const GUIDES = ".caztor/guides";
const encode = (text: string) => new TextEncoder().encode(text);
const NAMES = [
  ...Array.from({ length: 10 }, (_, i) => `${String(i + 1).padStart(2, "0")}-section${"abcdefghij"[i]}.md`),
  "INDEX.md",
  "LICENSE-papersmith-ai.txt",
];

function source(version: string): GuideSourcePort & { version: string; failure: string | null } {
  const port = {
    version,
    failure: null as string | null,
    async load() {
      if (port.failure !== null) return { ok: false as const, error: { message: port.failure } };
      const documents: GuideDocument[] = NAMES.map((name) => ({ name, bytes: encode(`${name} ${port.version}\n`) }));
      return { ok: true as const, value: documents };
    },
  };
  return port;
}

const frameOf = (frames: Frame[], type: string) => frames.find((frame) => frame.data["type"] === type);
const listed = async (h: ChatHarness) => ((await (await h.call("GET", "/api/files")).json()) as { entries: { path: string }[] }).entries.map((e) => e.path);

describe("writing guides through the running chat routes", () => {
  it("provisions the twelve built-in files before the turn, hidden and absent from the changed files", async () => {
    const h = chatHarness();
    writeFileSync(join(h.root, "main.tex"), "text");

    const { frames } = await h.sendMessage("hello");

    const folder = join(h.root, GUIDES);
    expect(readdirSync(folder).sort()).toHaveLength(12);
    expect(readdirSync(folder)).toContain("INDEX.md");
    expect(readdirSync(folder)).toContain("LICENSE-papersmith-ai.txt");
    expect(readdirSync(folder).filter((name) => /^\d\d-.*\.md$/.test(name))).toHaveLength(10);
    expect(frameOf(frames, "files_changed")?.data).toMatchObject({ files: [] });
    expect(frames.some((frame) => frame.data["type"] === "notice")).toBe(false);
    expect(await listed(h)).toEqual(["main.tex"]);
    expect((await h.call("GET", `/api/files/content?path=${GUIDES}/INDEX.md`)).status).toBeGreaterThanOrEqual(400);
    expect((await h.call("PUT", "/api/files/content", { body: { path: `${GUIDES}/INDEX.md`, content: "x", baseHash: null } })).status).toBeGreaterThanOrEqual(400);
    const state = JSON.parse(readFileSync(join(h.root, ".caztor", "state.json"), "utf8")) as { provisioned: Record<string, unknown> };
    expect(Object.keys(state.provisioned).filter((key) => key.startsWith(`${GUIDES}/`))).toHaveLength(12);
  });

  it("writes the guides before the agent starts, so the agent can read them", async () => {
    const h = chatHarness();
    let seen: string[] = [];
    h.runners.claude.script = async function* ({ root }) {
      seen = readdirSync(join(root, GUIDES));
      yield { type: "done", reason: "completed" };
    };

    await h.sendMessage("hello");

    expect(seen).toHaveLength(12);
  });

  it("keeps a rewrite of the guides by provisioning out of the changed files and out of undo", async () => {
    const guides = source("v1");
    const h = chatHarness({ guides });
    await h.sendMessage("first");
    guides.version = "v2";

    const { frames } = await h.sendMessage("second");

    expect(readFileSync(join(h.root, GUIDES, "INDEX.md"), "utf8")).toBe("INDEX.md v2\n");
    expect(frameOf(frames, "files_changed")?.data).toMatchObject({ files: [] });
    expect(frames.some((frame) => frame.data["type"] === "notice")).toBe(false);
  });

  it("provisions the documents of a substituted source", async () => {
    const h = chatHarness({ guides: source("custom") });

    await h.sendMessage("hello");

    expect(readFileSync(join(h.root, GUIDES, "INDEX.md"), "utf8")).toBe("INDEX.md custom\n");
    expect(readFileSync(join(h.root, GUIDES, NAMES[0] as string), "utf8")).toBe(`${NAMES[0]} custom\n`);
  });

  it("uses the built-in guides when the substituted source fails", async () => {
    const broken = source("x");
    broken.failure = "offline";
    const h = chatHarness({ guides: broken });

    const { frames } = await h.sendMessage("hello");

    expect(readFileSync(join(h.root, GUIDES, "INDEX.md"), "utf8")).toMatch(/^# Writing guides/);
    expect(frames.some((frame) => frame.data["type"] === "notice")).toBe(false);
  });

  it("starts the turn anyway and says so when no guide source can be read", async () => {
    const broken = source("x");
    broken.failure = "offline";
    const alsoBroken = source("y");
    alsoBroken.failure = "folder missing";
    const h = chatHarness({ guides: broken, builtInGuides: alsoBroken });

    const { response, frames } = await h.sendMessage("hello");

    expect(response.status).toBe(200);
    expect(frameOf(frames, "notice")?.data).toMatchObject({
      level: "warning",
      message: expect.stringContaining("The writing guides could not be prepared, so this turn runs without them: folder missing"),
    });
    expect(h.runners.claude.requests).toHaveLength(1);
    expect(frames.at(-2)?.data).toMatchObject({ type: "done", reason: "completed" });
    expect(existsSync(join(h.root, GUIDES))).toBe(false);
    expect(existsSync(join(h.root, ".claude", "agents", "caztor.md"))).toBe(true);
  });

  it("keeps a guide the user edited and tells them how to restore it", async () => {
    const h = chatHarness({ guides: source("v1") });
    await h.sendMessage("first");
    writeFileSync(join(h.root, GUIDES, "04-sectiond.md"), "mine\n");

    const { frames } = await h.sendMessage("second");

    expect(frameOf(frames, "notice")?.data).toMatchObject({
      message: "The writing guide `04-sectiond.md` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide.",
      action: "replace_definition",
    });
    expect(readFileSync(join(h.root, GUIDES, "04-sectiond.md"), "utf8")).toBe("mine\n");

    const replaced = await h.call("POST", "/api/chat/definition/replace", { body: { provider: "claude" } });
    expect(replaced.status).toBe(200);
    expect(readFileSync(join(h.root, GUIDES, "04-sectiond.md"), "utf8")).toBe("04-sectiond.md v1\n");
  });
});
