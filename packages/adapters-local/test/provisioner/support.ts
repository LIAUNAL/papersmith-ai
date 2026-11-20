import { hashBytes, type ContentHash, type GuideDocument, type GuideSourcePort, type ProviderId } from "@caztor/core";
import { createAgentsMdVisibility } from "../../src/agents-md.ts";
import { createProvisioner } from "../../src/provisioner.ts";
import { createProjectStore } from "../../src/project-store.ts";
import { createStateStore } from "../../src/state-store.ts";
import { hooked, type Hooks } from "../snapshot/support.ts";
import type { Sandbox } from "../support/fs-sandbox.ts";

export { implementations } from "../support/fs-sandbox.ts";
export const encode = (text: string) => new TextEncoder().encode(text);
export const decode = (bytes: Uint8Array) => new TextDecoder().decode(bytes);
export const hashOf = (text: string): Promise<ContentHash> => hashBytes(encode(text));

export const CLAUDE_V1 = "---\nname: caztor\ndescription: Test agent\ntools: Read, Edit\n---\n\nClaude prompt, first version.\n";
export const CLAUDE_V2 = "---\nname: caztor\ndescription: Test agent\ntools: Read, Edit\n---\n\nClaude prompt, second version.\n";
export const OPENCODE_V1 =
  "---\ndescription: Test opencode agent\nmode: primary\npermission:\n  edit: allow\n  bash: deny\n---\n\nOpencode prompt.\n";
export const ANTIGRAVITY_V1 =
  "---\nname: caztor\ndescription: Test antigravity agent\ntools: [view_file, list_dir, replace_file_content]\ncommandExecutionPolicy: off\nmodel: inherit\n---\n\nAntigravity prompt.\n";
export const ANTIGRAVITY_V2 = ANTIGRAVITY_V1.replace("Antigravity prompt.", "Antigravity prompt, second.");
export const PI_V1 = "# Test Pi agent\n\nPi system prompt, first version.\n";
export const PI_V2 = "# Test Pi agent\n\nPi system prompt, second version.\n";
export const CODEX_V1 = "# Test agent\n\nCodex instructions, first version.\n";
export const CODEX_V2 = "# Test agent\n\nCodex instructions, second version.\n";

export async function setupProvisioner(create: () => Sandbox, options: { hooks?: Hooks; guides?: GuideSourcePort } = {}) {
  const box = create();
  const project = `${box.root}/project`;
  const agentsDir = `${box.root}/shipped-agents`;
  await box.fs.mkdir(project, { recursive: true });
  await box.fs.mkdir(agentsDir, { recursive: true });
  const fs = options.hooks === undefined ? box.fs : hooked(box.fs, options.hooks);
  const canonical: Record<ProviderId, string> = { claude: CLAUDE_V1, opencode: OPENCODE_V1, codex: CODEX_V1, antigravity: ANTIGRAVITY_V1, pi: PI_V1 };
  const publish = async (provider: ProviderId, text: string) => {
    canonical[provider] = text;
    await box.fs.writeFile(`${agentsDir}/${provider}.md`, encode(text));
  };
  for (const provider of ["claude", "opencode", "codex", "antigravity", "pi"] as const) await publish(provider, canonical[provider]);

  const state = createStateStore({ fs, root: project });
  const store = createProjectStore({ fs, root: project, agentsMdCreatedByCaztor: createAgentsMdVisibility({ fs, root: project, state }) });
  const provisioner = createProvisioner({
    fs,
    root: project,
    state,
    store,
    agentsDir,
    ...(options.guides === undefined ? {} : { guides: options.guides }),
  });

  const read = async (path: string) => decode(await box.fs.readFile(`${project}/${path}`));
  const exists = (path: string) =>
    box.fs.lstat(`${project}/${path}`).then(
      () => true,
      () => false,
    );
  const put = async (path: string, text: string) => {
    const full = `${project}/${path}`;
    await box.fs.mkdir(full.slice(0, full.lastIndexOf("/")), { recursive: true });
    await box.fs.writeFile(full, encode(text));
  };
  const names = async (dir = "") => (await box.fs.readdir(`${project}/${dir}`.replace(/\/$/, ""))).map((entry) => entry.name).sort();
  return { ...box, project, agentsDir, state, store, provisioner, publish, read, exists, put, names };
}

export const GUIDE_NAMES = [
  "01-materials-and-methods.md",
  "02-experimental-setup.md",
  "03-results-and-discussion.md",
  "04-limitations.md",
  "05-related-work.md",
  "06-introduction.md",
  "07-conclusions.md",
  "08-abstract.md",
  "09-title-and-keywords.md",
  "10-back-matter.md",
  "INDEX.md",
  "LICENSE-papersmith-ai.txt",
] as const;

export const GUIDES_TARGET_DIR = ".caztor/guides";

export interface FakeGuides extends GuideSourcePort {
  documents: GuideDocument[];
  failure: string | null;
  loads: number;
  set(name: string, text: string): void;
  drop(name: string): void;
}

/** A guide source that serves the twelve names with text derived from the name, and can be changed or made to fail. */
export function fakeGuides(version = "v1"): FakeGuides {
  const port: FakeGuides = {
    documents: GUIDE_NAMES.map((name) => ({ name, bytes: encode(`${name} ${version}\n`) })),
    failure: null,
    loads: 0,
    set(name, text) {
      port.documents = [...port.documents.filter((d) => d.name !== name), { name, bytes: encode(text) }];
    },
    drop(name) {
      port.documents = port.documents.filter((d) => d.name !== name);
    },
    async load() {
      port.loads += 1;
      if (port.failure !== null) return { ok: false, error: { message: port.failure } };
      return { ok: true, value: port.documents };
    },
  };
  return port;
}
