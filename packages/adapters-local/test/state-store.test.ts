import type { ContentHash, ProjectState, RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import type { FileSystem } from "../src/infra.ts";
import { createStateStore, defaultProjectState } from "../src/state-store.ts";
import { cleanupSandboxes, implementations } from "./support/fs-sandbox.ts";

const encode = (text: string) => new TextEncoder().encode(text);
const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
const hash = (hex: string) => `sha256:${hex}` as ContentHash;

cleanupSandboxes();

describe.each(implementations)("state store: %s", (_name, create) => {
  async function setup(wrap: (fs: FileSystem) => FileSystem = (fs) => fs) {
    const box = create();
    const project = `${box.root}/project`;
    await box.fs.mkdir(project, { recursive: true });
    const store = createStateStore({ fs: wrap(box.fs), root: project });
    const statePath = `${project}/.caztor/state.json`;
    const writeRaw = async (text: string) => {
      await box.fs.mkdir(`${project}/.caztor`, { recursive: true });
      await box.fs.writeFile(statePath, encode(text));
    };
    return { ...box, project, store, statePath, writeRaw };
  }

  it("returns the defaults when state.json does not exist", async () => {
    const { store } = await setup();
    expect(await store.load()).toEqual(defaultProjectState());
    expect(defaultProjectState()).toMatchObject({
      selectedProvider: null,
      mainFile: null,
      stopOnFirstError: false,
      autoCompile: true,
      sandboxedCompile: false,
      disclosureAcknowledged: false,
      projectCliConfigTrusted: {},
      models: {},
      sessions: {},
      provisioned: {},
    });
  });

  it("keeps the trusted project configuration fingerprints of known providers and drops anything else", async () => {
    const { store, writeRaw } = await setup();
    await writeRaw(JSON.stringify({ projectCliConfigTrusted: { opencode: hash("cc"), claude: 7, nobody: hash("dd"), codex: "plain" } }));
    expect((await store.load()).projectCliConfigTrusted).toEqual({ opencode: hash("cc") });
  });

  it("has no stored auth mode by default, so every provider is read as account", async () => {
    const { store } = await setup();
    expect(defaultProjectState().authModes).toEqual({});
    expect((await store.load()).authModes).toEqual({});
  });

  it("keeps the auth modes of known providers and drops unknown providers and unknown modes", async () => {
    const { store, writeRaw } = await setup();
    await writeRaw(JSON.stringify({ authModes: { claude: "api", opencode: "account", codex: "oauth", nobody: "api", antigravity: 3 } }));
    expect((await store.load()).authModes).toEqual({ claude: "api", opencode: "account" });
  });

  it("reads a state file written before auth modes existed as having none", async () => {
    const { store, writeRaw } = await setup();
    await writeRaw(JSON.stringify({ selectedProvider: "claude", models: { claude: "sonnet" } }));
    const state = await store.load();
    expect(state.selectedProvider).toBe("claude");
    expect(state.authModes).toEqual({});
  });

  it("round-trips a mode through update", async () => {
    const { store } = await setup();
    await store.update({ authModes: { opencode: "api" } });
    expect((await store.load()).authModes).toEqual({ opencode: "api" });
  });

  it("keeps the sign-in method of a stored session and reads a session without one as having none", async () => {
    const { store, writeRaw } = await setup();
    await writeRaw(
      JSON.stringify({
        sessions: {
          claude: { sessionId: "s1", agentHash: hash("aa"), isolation: "I1", authMode: "api" },
          codex: { sessionId: "s2", agentHash: hash("bb"), isolation: "I1" },
          opencode: { sessionId: "s3", agentHash: hash("cc"), isolation: "I1", authMode: "oauth" },
        },
      }),
    );
    const { sessions } = await store.load();
    expect(sessions.claude).toEqual({ sessionId: "s1", agentHash: hash("aa"), isolation: "I1", authMode: "api" });
    expect(sessions.codex).toEqual({ sessionId: "s2", agentHash: hash("bb"), isolation: "I1" });
    expect(sessions.opencode).toEqual({ sessionId: "s3", agentHash: hash("cc"), isolation: "I1" });
  });

  it.each([
    ["truncated JSON", '{"selectedProvider": "cla'],
    ["empty file", ""],
    ["a JSON array", "[1,2]"],
    ["JSON null", "null"],
    ["a JSON string", '"hello"'],
  ])("returns the defaults for %s", async (_label, content) => {
    const { store, writeRaw } = await setup();
    await writeRaw(content);
    expect(await store.load()).toEqual(defaultProjectState());
  });

  it("keeps valid fields and replaces only the fields with the wrong type", async () => {
    const { store, writeRaw } = await setup();
    await writeRaw(
      JSON.stringify({
        selectedProvider: "opencode",
        models: { claude: "sonnet", codex: 7, unknown: "x" },
        mainFile: "../escape.tex",
        autoCompile: "yes",
        stopOnFirstError: true,
        sessions: { claude: { sessionId: "s1", agentHash: hash("aa"), isolation: "I1" }, codex: { sessionId: 3 } },
        provisioned: { "AGENTS.md": { hash: hash("bb"), createdByCaztor: true }, "bad": { hash: "nope", createdByCaztor: true } },
        extra: "dropped",
      }),
    );
    const state = await store.load();
    expect(state).toEqual({
      ...defaultProjectState(),
      selectedProvider: "opencode",
      models: { claude: "sonnet" },
      stopOnFirstError: true,
      sessions: { claude: { sessionId: "s1", agentHash: hash("aa"), isolation: "I1" } },
      provisioned: { "AGENTS.md": { hash: hash("bb"), createdByCaztor: true } },
    });
    expect("extra" in state).toBe(false);
  });

  it("merges a patch into the stored state, persists it and returns the result", async () => {
    const { store, statePath, fs } = await setup();
    const first = await store.update({ selectedProvider: "claude", mainFile: "main.tex" as RelPath });
    const second = await store.update({ autoCompile: false, models: { claude: "opus" } });

    expect(second).toEqual({
      ...defaultProjectState(),
      selectedProvider: "claude",
      mainFile: "main.tex",
      autoCompile: false,
      models: { claude: "opus" },
    });
    expect(first.autoCompile).toBe(true);
    expect(await store.load()).toEqual(second);
    expect(JSON.parse(decode(await fs.readFile(statePath))) as ProjectState).toEqual(second);
  });

  it("starts from the defaults when the stored file is corrupt and then repairs it", async () => {
    const { store, writeRaw, statePath, fs } = await setup();
    await writeRaw("{not json");
    const state = await store.update({ disclosureAcknowledged: true });
    expect(state).toEqual({ ...defaultProjectState(), disclosureAcknowledged: true });
    expect(JSON.parse(decode(await fs.readFile(statePath)))).toEqual(state);
  });

  it("applies concurrent updates without losing either one", async () => {
    const { store } = await setup();
    await Promise.all([store.update({ autoCompile: false }), store.update({ stopOnFirstError: true }), store.update({ sandboxedCompile: true })]);
    expect(await store.load()).toMatchObject({ autoCompile: false, stopOnFirstError: true, sandboxedCompile: true });
  });

  it("writes atomically: a failed replace keeps the previous state and leaves no temporary file", async () => {
    const failingRename = (fs: FileSystem): FileSystem => ({
      readFile: (p) => fs.readFile(p),
      readRange: (p, s, l) => fs.readRange(p, s, l),
      writeFile: (p, d, o) => fs.writeFile(p, d, o),
      mkdir: (p, o) => fs.mkdir(p, o),
      readdir: (p) => fs.readdir(p),
      stat: (p) => fs.stat(p),
      lstat: (p) => fs.lstat(p),
      realpath: (p) => fs.realpath(p),
      rename: () => Promise.reject(Object.assign(new Error("disk full"), { code: "ENOSPC" })),
      rm: (p, o) => fs.rm(p, o),
      copyFile: (a, b) => fs.copyFile(a, b),
      chmod: (p, m) => fs.chmod(p, m),
      mkdtemp: (p) => fs.mkdtemp(p),
    });
    const { store, writeRaw, statePath, project, fs } = await setup(failingRename);
    await writeRaw(JSON.stringify({ autoCompile: false }));

    await expect(store.update({ stopOnFirstError: true })).rejects.toMatchObject({ code: "ENOSPC" });
    expect(JSON.parse(decode(await fs.readFile(statePath)))).toEqual({ autoCompile: false });
    expect((await fs.readdir(`${project}/.caztor`)).map((entry) => entry.name)).toEqual(["state.json"]);
  });

  it("refuses to write when .caztor is a link that leaves the project", async () => {
    const { store, project, root, fs, symlink } = await setup();
    await fs.mkdir(`${root}/outside`);
    symlink(`${root}/outside`, `${project}/.caztor`);

    const failure = await store.update({ autoCompile: false }).then(() => new Error("it did not fail"), (error: Error) => error);
    expect(failure.message).toBe("The .caztor folder is a link, so Caztor cannot keep the project's settings in it. Replace the link with a plain folder.");
    expect(failure.message).not.toContain(root);
    expect(await fs.readdir(`${root}/outside`)).toEqual([]);
    expect(await store.load()).toEqual(defaultProjectState());
  });

  it("returns the defaults when .caztor links back to itself, and update still refuses to write", async () => {
    const { store, project, symlink } = await setup();
    symlink(`${project}/.caztor`, `${project}/.caztor`);

    expect(await store.load()).toEqual(defaultProjectState());
    await expect(store.update({ autoCompile: false })).rejects.toThrow();
  });

  it("returns the defaults when the state directory cannot be inspected, and update does not write", async () => {
    const denied = (fs: FileSystem): FileSystem => ({
      readFile: (p) => fs.readFile(p),
      readRange: (p, s, l) => fs.readRange(p, s, l),
      writeFile: (p, d, o) => fs.writeFile(p, d, o),
      mkdir: (p, o) => fs.mkdir(p, o),
      readdir: (p) => fs.readdir(p),
      stat: (p) => fs.stat(p),
      lstat: (p) => fs.lstat(p),
      realpath: (p) => (p.endsWith("/.caztor") ? Promise.reject(Object.assign(new Error("denied"), { code: "EACCES" })) : fs.realpath(p)),
      rename: (a, b) => fs.rename(a, b),
      rm: (p, o) => fs.rm(p, o),
      copyFile: (a, b) => fs.copyFile(a, b),
      chmod: (p, m) => fs.chmod(p, m),
      mkdtemp: (p) => fs.mkdtemp(p),
    });
    const { store, project, fs } = await setup(denied);
    await fs.mkdir(`${project}/.caztor`);

    expect(await store.load()).toEqual(defaultProjectState());
    await expect(store.update({ autoCompile: false })).rejects.toMatchObject({ code: "EACCES" });
    expect(await fs.readdir(`${project}/.caztor`)).toEqual([]);
  });

  it("keeps provisioned entries with valid project paths and drops the others", async () => {
    const { store, writeRaw } = await setup();
    const entry = { hash: hash("aa"), createdByCaztor: true };
    await writeRaw(
      JSON.stringify({
        provisioned: {
          "AGENTS.md": entry,
          "docs/notes.md": entry,
          "../escape.md": entry,
          "/etc/passwd": entry,
          "a/../b.md": entry,
          ".caztor/state.json": entry,
          "": entry,
        },
      }),
    );
    const state = await store.load();
    expect(Object.keys(state.provisioned).sort()).toEqual(["AGENTS.md", "docs/notes.md"]);
    expect(state.provisioned["AGENTS.md" as RelPath]).toEqual(entry);
  });

  it("keeps the records of the three agent definition paths, which lie in reserved folders, and no other reserved path", async () => {
    const { store, writeRaw } = await setup();
    const entry = { hash: hash("aa"), createdByCaztor: true };
    await writeRaw(
      JSON.stringify({
        provisioned: {
          ".claude/agents/caztor.md": entry,
          ".opencode/agents/caztor.md": entry,
          "AGENTS.md": entry,
          ".claude/settings.json": entry,
          ".claude/agents/other.md": entry,
          ".git/config": entry,
          "node_modules/x.js": entry,
        },
      }),
    );
    const state = await store.load();
    expect(Object.keys(state.provisioned).sort()).toEqual([".claude/agents/caztor.md", ".opencode/agents/caztor.md", "AGENTS.md"]);
  });

  it("keeps the records of provisioned writing guides, which lie in the reserved state folder, and no other path in it", async () => {
    const { store, writeRaw } = await setup();
    const entry = { hash: hash("aa"), createdByCaztor: true };
    await writeRaw(
      JSON.stringify({
        provisioned: {
          ".caztor/guides/INDEX.md": entry,
          ".caztor/guides/08-abstract.md": entry,
          ".caztor/guides/LICENSE-papersmith-ai.txt": entry,
          ".caztor/guides/notes.md": entry,
          ".caztor/guides/../state.json": entry,
          ".caztor/guides/sub/INDEX.md": entry,
          ".caztor/snapshots/x": entry,
          ".caztor/state.json": entry,
        },
      }),
    );
    const state = await store.load();
    expect(Object.keys(state.provisioned).sort()).toEqual([
      ".caztor/guides/08-abstract.md",
      ".caztor/guides/INDEX.md",
      ".caztor/guides/LICENSE-papersmith-ai.txt",
    ]);
  });

  it("writes a record of a native definition and reads it back", async () => {
    const { store } = await setup();
    const record = { hash: hash("bb"), createdByCaztor: false };
    await store.update({ provisioned: { ".claude/agents/caztor.md": record } });
    expect((await store.load()).provisioned).toEqual({ ".claude/agents/caztor.md": record });
  });

  describe("each person's state", () => {
    const session = { sessionId: "s1", agentHash: hash("a".repeat(64)), isolation: "tier-1" };

    it("loads an old state file unchanged and writes no users key for a host-only project", async () => {
      const t = await setup();
      const old = { selectedProvider: "claude", models: { claude: "claude-opus" }, sessions: { claude: session }, autoCompile: false };
      await t.writeRaw(JSON.stringify(old));
      expect(await t.store.load()).toEqual({ ...defaultProjectState(), ...old });
      await t.store.update({ models: { claude: "claude-sonnet" } });
      const written = JSON.parse(decode(await t.fs.readFile(t.statePath))) as Record<string, unknown>;
      expect(Object.keys(written)).toEqual(Object.keys(defaultProjectState()));
      expect(written["sessions"]).toEqual({ claude: session });
    });

    it("keeps the valid entries of each collaborator and drops hostile ids and bad values", async () => {
      const t = await setup();
      await t.writeRaw(
        JSON.stringify({
          users: {
            "alice-1": { selectedProvider: "codex", models: { claude: "m", nope: "x" }, authModes: { claude: "api", codex: "weird" }, sessions: { claude: session, pi: { sessionId: 3 } } },
            "../escape": { selectedProvider: "claude", models: {}, authModes: {}, sessions: {} },
            host: { selectedProvider: "claude", models: {}, authModes: {}, sessions: {} },
            "bob-2": "not an object",
          },
        }),
      );
      expect((await t.store.load()).users).toEqual({ "alice-1": { selectedProvider: "codex", models: { claude: "m" }, authModes: { claude: "api" }, sessions: { claude: session } } });
    });

    it("applies an edit to the current state in one serialized step, so two people's writes both land", async () => {
      const t = await setup();
      const add = (id: string) => t.store.change!((current) => ({ users: { ...(current.users ?? {}), [id]: { selectedProvider: "claude", models: {}, authModes: {}, sessions: {} } } }));
      await Promise.all([add("alice-1"), add("bob-2")]);
      expect(Object.keys((await t.store.load()).users ?? {}).sort()).toEqual(["alice-1", "bob-2"]);
    });
  });
});
