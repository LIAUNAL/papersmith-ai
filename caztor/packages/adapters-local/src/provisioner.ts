import { AGENT_BLOCK_BEGIN, AGENT_BLOCK_END, AGENT_TARGETS, GUIDES_DIR, guideSetProblem, hashBytes } from "@caztor/core";
import type { RelPath, Result } from "@caztor/core";
import type { AgentDefinition, ContentHash, GuideSourcePort, ProjectState, ProvisionerPort, ProvisionOutcome, ProviderId, StatePort } from "@caztor/core";
import { parseAgentFile } from "./agent-definition.ts";
import { blockBodyHash, findBlock } from "./agents-md.ts";
import { basename, codeOf, dirname, joinPath } from "./containment.ts";
import type { FileSystem } from "./infra.ts";
import { createKeyedLock } from "./keyed-lock.ts";
import type { ProjectStore } from "./project-store.ts";
import { TEMP_PREFIX } from "./project-store.ts";

export interface ProvisionerOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  state: StatePort;
  /** Used to write a visible `AGENTS.md`, so a save by the user cannot be lost to the provisioner. */
  store: ProjectStore;
  /** Absolute path of the folder with the shipped definitions; see `defaultAgentsDir`. */
  agentsDir: string;
  /** Where the writing guides come from. Without it no guide is provisioned. */
  guides?: GuideSourcePort;
}

export interface RemovalOutcome {
  target: string;
  status: "removed" | "unchanged" | "skipped_user_modified";
}

/** The port, plus taking a provider's definition back out of the project. */
export interface Provisioner extends ProvisionerPort {
  /** Removes what `ensure` added for the provider, leaving every other file as it is. A file the user changed stays. */
  remove(provider: ProviderId): Promise<Result<{ outcomes: RemovalOutcome[] }, { message: string }>>;
}

/** Permission bits of a file the provisioner creates. */
const NEW_FILE_MODE = 0o644;

/** Serializes provisioning of one project, also across several provisioner instances in this process. */
const provisionLock = createKeyedLock();

/** A refusal with a message fit for the user; it never carries a stack or a host path beyond the project's. */
class ProvisionError extends Error {}

const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/** What a guarded write is for, so a refusal names the right thing. */
interface WriteKind {
  folder: string;
  /** Completes "..., so <what> not written". */
  what: string;
}
const AGENT_KIND: WriteKind = { folder: "agent", what: "the agent definition was" };
const GUIDES_KIND: WriteKind = { folder: "guides", what: "the writing guides were" };

type Present = { kind: "absent" } | { kind: "other" } | { kind: "file"; bytes: Uint8Array; hash: ContentHash; mode: number };

/**
 * Writes the agent definition of the provider whose turn is starting. It deliberately targets folders the project
 * store refuses (`.claude/`, `.opencode/`, `.agents/`, and `.caztor/agents/` for Pi), so it has its own guarded writer: every folder on the way must be a
 * real folder inside the project (a link is refused, even one that stays inside), and a definition that is itself a
 * link is treated as the user's own and never written through.
 */
export function createProvisioner(options: ProvisionerOptions): Provisioner {
  const { fs, state } = options;
  const lockKey = `provision:${options.root}`;

  async function shipped(provider: ProviderId): Promise<{ bytes: Uint8Array; text: string; hash: ContentHash }> {
    try {
      const bytes = await fs.readFile(joinPath(options.agentsDir, `${provider}.md`));
      return { bytes, text: new TextDecoder().decode(bytes), hash: await hashBytes(bytes) };
    } catch (error) {
      throw new ProvisionError(`The shipped agent definition for ${provider} could not be read: ${errorText(error)}`);
    }
  }

  /**
   * Makes sure each folder above `target` exists as a real folder and returns the folder's absolute path. With
   * `create: false` a missing folder gives null instead of being made.
   */
  async function guardedFolder(target: string, kind: WriteKind = AGENT_KIND, create = true): Promise<string | null> {
    let current = await fs.realpath(options.root);
    for (const segment of target.split("/").slice(0, -1)) {
      current = joinPath(current, segment);
      try {
        const stats = await fs.lstat(current);
        if (stats.isSymbolicLink()) throw new ProvisionError(`${segment} is a link, so ${kind.what} not written`);
        if (!stats.isDirectory()) throw new ProvisionError(`${segment} is not a folder, so ${kind.what} not written`);
      } catch (error) {
        if (error instanceof ProvisionError) throw error;
        if (codeOf(error) !== "ENOENT") throw error;
        if (!create) return null;
        await fs.mkdir(current);
      }
    }
    if ((await fs.realpath(current)) !== current) throw new ProvisionError(`The ${kind.folder} folder resolves outside the project, so nothing was written`);
    return current;
  }

  async function inspect(full: string): Promise<Present> {
    try {
      const stats = await fs.lstat(full);
      if (stats.isSymbolicLink() || !stats.isFile()) return { kind: "other" };
      const bytes = await fs.readFile(full);
      return { kind: "file", bytes, hash: await hashBytes(bytes), mode: stats.mode };
    } catch (error) {
      if (codeOf(error) === "ENOENT") return { kind: "absent" };
      throw error;
    }
  }

  /** Atomic replace through a temporary name; `mode` is the permission bits of the result. */
  async function writeFileGuarded(full: string, bytes: Uint8Array, mode: number, mustBeAbsent = false, kind: WriteKind = AGENT_KIND): Promise<void> {
    const folder = dirname(full);
    const temp = joinPath(folder, `${TEMP_PREFIX}${crypto.randomUUID()}`);
    try {
      await fs.writeFile(temp, bytes, { exclusive: true, mode: 0o600 });
      if ((await fs.realpath(folder)) !== folder) throw new ProvisionError(`The ${kind.folder} folder changed while writing, so nothing was written`);
      await fs.chmod(temp, mode);
      if (mustBeAbsent && (await inspect(full)).kind !== "absent") throw new ProvisionError(`${basename(full)} appeared while it was being created, so nothing was written`);
      await fs.rename(temp, full);
    } catch (error) {
      await fs.rm(temp, { force: true }).catch(() => {});
      throw error;
    }
  }

  async function record(target: string, entry: { hash: ContentHash; createdByCaztor: boolean }): Promise<void> {
    const current = await state.load();
    const provisioned: ProjectState["provisioned"] = { ...current.provisioned, [target]: entry };
    await state.update({ provisioned });
  }

  function describe(provider: ProviderId, present: Uint8Array, hash: ContentHash, fallback: AgentDefinition): AgentDefinition {
    return parseAgentFile(provider, new TextDecoder().decode(present), hash) ?? { ...fallback, hash };
  }

  /**
   * Brings one file in line with the shipped bytes under the rules every provisioned file follows: absent means
   * create, equal means unchanged, a known older version means update, anything else is the user's and is left
   * alone unless `replace` is set. A link or a folder at the path is never written through.
   */
  async function syncFile(
    target: string,
    canonical: { bytes: Uint8Array; hash: ContentHash },
    replace: boolean,
    kind: WriteKind,
  ): Promise<{ status: ProvisionOutcome["status"]; present: Present }> {
    const folder = (await guardedFolder(target, kind)) as string;
    const full = joinPath(folder, basename(target));
    const present = await inspect(full);
    const known = (await state.load()).provisioned[target];

    if (present.kind === "other") return { status: "skipped_user_modified", present };
    if (present.kind === "absent") {
      await writeFileGuarded(full, canonical.bytes, NEW_FILE_MODE, true, kind);
      await record(target, { hash: canonical.hash, createdByCaztor: true });
      return { status: "created", present };
    }
    if (present.hash === canonical.hash) {
      if (known?.hash !== present.hash) await record(target, { hash: present.hash, createdByCaztor: known?.createdByCaztor ?? true });
      return { status: "unchanged", present };
    }
    if (known?.hash === present.hash || replace) {
      await writeFileGuarded(full, canonical.bytes, present.mode, false, kind);
      await record(target, { hash: canonical.hash, createdByCaztor: known?.createdByCaztor ?? false });
      return { status: "updated", present };
    }
    return { status: "skipped_user_modified", present };
  }

  async function ensureNative(provider: Exclude<ProviderId, "codex">, replace: boolean) {
    const target = AGENT_TARGETS[provider];
    const canonical = await shipped(provider);
    const fallback = parseAgentFile(provider, canonical.text, canonical.hash);
    if (fallback === null) throw new ProvisionError(`The shipped agent definition for ${provider} is not valid`);

    const { status, present } = await syncFile(target, canonical, replace, AGENT_KIND);
    // The definition that is actually in the project: the user's own when it was kept, ours otherwise.
    const kept = present.kind === "file" && (status === "unchanged" || status === "skipped_user_modified");
    const agent = kept ? describe(provider, present.bytes, present.hash, fallback) : fallback;
    return { outcomes: [{ target, status }], agent };
  }

  const encodeText = (text: string) => new TextEncoder().encode(text);


  /**
   * Rewrites AGENTS.md. A file only Caztor wrote is hidden from the file API, so the guarded writer is used; a file the
   * user can see is written through the store with the hash that was read, so a save made meanwhile is not lost.
   */
  async function writeAgentsMd(full: string, next: string, present: Extract<Present, { kind: "file" }>, hidden: boolean): Promise<void> {
    if (hidden) return writeFileGuarded(full, encodeText(next), present.mode);
    const written = await options.store.write(AGENT_TARGETS.codex as RelPath, encodeText(next), present.hash);
    if (!written.ok) {
      throw new ProvisionError(
        written.error.code === "conflict"
          ? "AGENTS.md changed while it was being updated, so nothing was written. Try again."
          : `AGENTS.md could not be written (${written.error.code}).`,
      );
    }
  }

  async function ensureAgentsMd(replace: boolean) {
    const target = AGENT_TARGETS.codex;
    const canonical = await shipped("codex");
    const body = `${canonical.text.trimEnd()}\n`;
    const bodyHash = await hashBytes(encodeText(body));
    const fallback = parseAgentFile("codex", body, bodyHash);
    if (fallback === null) throw new ProvisionError("The shipped agent definition for codex is not valid");
    const region = `${AGENT_BLOCK_BEGIN}\n${body}${AGENT_BLOCK_END}`;

    const full = joinPath((await guardedFolder(target)) as string, target);
    const present = await inspect(full);
    const known = (await state.load()).provisioned[target];
    const done = (status: ProvisionOutcome["status"], agent: AgentDefinition) => ({ outcomes: [{ target, status }], agent });

    if (present.kind === "other") return done("skipped_user_modified", fallback);
    if (present.kind === "absent") {
      await writeFileGuarded(full, encodeText(`${region}\n`), NEW_FILE_MODE, true);
      await record(target, { hash: bodyHash, createdByCaztor: true });
      return done("created", fallback);
    }

    const text = new TextDecoder().decode(present.bytes);
    const found = findBlock(text);
    if (found.kind === "broken") return done("skipped_user_modified", fallback);

    let next: string;
    let outsideIsEmpty: boolean;
    let status: ProvisionOutcome["status"];
    if (found.kind === "none") {
      // A file without a final line break gets a block without one too, so removing it gives the file back byte for byte.
      next = text === "" ? `${region}\n` : text.endsWith("\n") ? `${text}\n${region}\n` : `${text}\n\n${region}`;
      outsideIsEmpty = text.trim() === "";
      status = "created";
    } else {
      const current = text.slice(found.start, found.end);
      // Text between a pair of markers is replaced only when it is the block Caztor wrote, or the user asked for it.
      if (current !== region && !replace && (await blockBodyHash(current)) !== known?.hash) return done("skipped_user_modified", fallback);
      const outside = text.slice(0, found.start) + text.slice(found.end);
      outsideIsEmpty = outside.trim() === "";
      next = current === region ? text : text.slice(0, found.start) + region + text.slice(found.end);
      status = current === region ? "unchanged" : "updated";
    }

    // A file only Caztor wrote stays hidden; the first line the user adds makes it theirs, and visible.
    const createdByCaztor = known?.createdByCaztor === true && outsideIsEmpty;
    if (known?.createdByCaztor === true && !createdByCaztor) await record(target, { hash: known.hash, createdByCaztor: false });
    if (next !== text) await writeAgentsMd(full, next, present, known?.createdByCaztor === true && createdByCaztor);
    if (known?.hash !== bodyHash || known.createdByCaztor !== createdByCaztor) await record(target, { hash: bodyHash, createdByCaztor });
    return done(status, fallback);
  }

  async function forget(target: string): Promise<void> {
    const current = await state.load();
    const { [target]: _removed, ...rest } = current.provisioned;
    await state.update({ provisioned: rest });
  }

  async function removeNative(provider: Exclude<ProviderId, "codex">): Promise<RemovalOutcome> {
    const target = AGENT_TARGETS[provider];
    const known = (await state.load()).provisioned[target];
    const full = joinPath(await fs.realpath(options.root), target);
    const present = await inspect(full);
    if (present.kind === "absent") {
      if (known !== undefined) await forget(target);
      return { target, status: "unchanged" };
    }
    if (known === undefined || present.kind === "other") return { target, status: "unchanged" };
    if (present.hash !== known.hash) return { target, status: "skipped_user_modified" };
    await fs.rm(full);
    // Only now-empty folders go; anything else in them is not ours. Pi's folder sits in `.caztor/`, which always stays.
    for (const folder of provider === "pi" ? [dirname(full)] : [dirname(full), dirname(dirname(full))]) {
      const stats = await fs.lstat(folder);
      if (stats.isSymbolicLink() || !stats.isDirectory() || (await fs.readdir(folder)).length > 0) break;
      await fs.rm(folder, { recursive: true });
    }
    await forget(target);
    return { target, status: "removed" };
  }

  async function removeAgentsMd(): Promise<RemovalOutcome> {
    const target = AGENT_TARGETS.codex;
    const known = (await state.load()).provisioned[target];
    const full = joinPath(await fs.realpath(options.root), target);
    const present = await inspect(full);
    if (present.kind === "absent") {
      if (known !== undefined) await forget(target);
      return { target, status: "unchanged" };
    }
    if (present.kind === "other") return { target, status: "unchanged" };
    const text = new TextDecoder().decode(present.bytes);
    const found = findBlock(text);
    if (found.kind === "broken") return { target, status: "skipped_user_modified" };
    if (found.kind === "none") {
      if (known !== undefined) await forget(target);
      return { target, status: "unchanged" };
    }
    const before = text.slice(0, found.start);
    const after = text.slice(found.end);
    // What separated the block from the text above it goes with the block: a block that ended the file without a line
    // break was added after a blank line, one that ended it with a line break after one more line break than the text had.
    let rest: string;
    if (after === "") rest = before.endsWith("\n\n") ? before.slice(0, -2) : before;
    else if (after === "\n") rest = before.endsWith("\n") ? before.slice(0, -1) : before;
    else rest = before + (after.startsWith("\n") ? after.slice(1) : after);
    const onlyOurs = known?.createdByCaztor === true && (before + after).trim() === "";
    if (onlyOurs) {
      await fs.rm(full);
    } else {
      // From here on the file is the user's, so it is no longer hidden, and the write goes through the store.
      if (known?.createdByCaztor === true) await record(target, { hash: known.hash, createdByCaztor: false });
      await writeAgentsMd(full, rest, present, false);
    }
    await forget(target);
    return { target, status: "removed" };
  }

  const guidePrefix = `${GUIDES_DIR}/`;
  const unavailable = (detail: string): ProvisionOutcome => ({ target: GUIDES_DIR, status: "unavailable", detail });

  /** Tracked guides that the source no longer ships go away when the user has not changed them. */
  async function removeStale(current: ReadonlySet<string>): Promise<void> {
    const tracked = (await state.load()).provisioned;
    for (const target of Object.keys(tracked)) {
      if (!target.startsWith(guidePrefix) || current.has(target)) continue;
      await removeTracked(target);
    }
  }

  /** Deletes one tracked guide whose content still matches its record, and forgets the record either way. */
  async function removeTracked(target: string): Promise<RemovalOutcome> {
    const known = (await state.load()).provisioned[target];
    const folder = await guardedFolder(target, GUIDES_KIND, false);
    const present = folder === null ? ({ kind: "absent" } as const) : await inspect(joinPath(folder, basename(target)));
    let status: RemovalOutcome["status"] = "unchanged";
    if (present.kind === "file") {
      if (known !== undefined && present.hash === known.hash) {
        await fs.rm(joinPath(folder as string, basename(target)));
        status = "removed";
      } else status = "skipped_user_modified";
    }
    await forget(target);
    return { target, status };
  }

  /**
   * Writes the guide set after the definition. A problem with the guides is reported as `unavailable` and never
   * fails the turn: the guides are advice, and a turn without them is still a turn.
   */
  async function ensureGuides(replace: boolean): Promise<ProvisionOutcome[]> {
    const source = options.guides;
    if (source === undefined) return [];
    const outcomes: ProvisionOutcome[] = [];
    try {
      const loaded = await source.load();
      if (!loaded.ok) return [unavailable(loaded.error.message)];
      const problem = guideSetProblem(loaded.value);
      if (problem !== null) return [unavailable(problem)];
      const documents = [...loaded.value].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
      for (const document of documents) {
        const target = `${guidePrefix}${document.name}`;
        const { status } = await syncFile(target, { bytes: document.bytes, hash: await hashBytes(document.bytes) }, replace, GUIDES_KIND);
        outcomes.push({ target, status });
      }
      await removeStale(new Set(documents.map((document) => `${guidePrefix}${document.name}`)));
    } catch (error) {
      outcomes.push(unavailable(errorText(error)));
    }
    return outcomes;
  }

  /** Once no provider's definition stays tracked, the shared guides go too (those the user changed stay). */
  async function removeGuides(): Promise<RemovalOutcome[]> {
    const tracked = (await state.load()).provisioned;
    if (Object.values(AGENT_TARGETS).some((target) => tracked[target] !== undefined)) return [];
    const outcomes: RemovalOutcome[] = [];
    for (const target of Object.keys(tracked).filter((key) => key.startsWith(guidePrefix))) outcomes.push(await removeTracked(target));
    const folder = await guardedFolder(`${GUIDES_DIR}/x`, GUIDES_KIND, false);
    if (folder !== null && (await fs.readdir(folder)).length === 0) await fs.rm(folder, { recursive: true });
    return outcomes;
  }

  return {
    ensure(provider, opts) {
      return provisionLock([lockKey], async () => {
        try {
          const replace = opts?.replace ?? false;
          const value = provider === "codex" ? await ensureAgentsMd(replace) : await ensureNative(provider, replace);
          return { ok: true as const, value: { ...value, outcomes: [...value.outcomes, ...(await ensureGuides(replace))] } };
        } catch (error) {
          return { ok: false as const, error: { message: errorText(error) } };
        }
      });
    },
    remove(provider) {
      return provisionLock([lockKey], async () => {
        try {
          const outcome = provider === "codex" ? await removeAgentsMd() : await removeNative(provider);
          return { ok: true as const, value: { outcomes: [outcome, ...(await removeGuides())] } };
        } catch (error) {
          return { ok: false as const, error: { message: errorText(error) } };
        }
      });
    },
  };
}
