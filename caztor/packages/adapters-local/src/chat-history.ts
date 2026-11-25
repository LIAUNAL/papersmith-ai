import { MAX_NAMED_UNPROTECTED, type ChatHistoryPort, type ChatTurnRecord, type ProviderId, type TurnEvent } from "@caztor/core";
import { isSafeUserId, PROVIDER_IDS } from "@caztor/core";
import type { FileSystem } from "./infra.ts";
import { createKeyedLock } from "./keyed-lock.ts";
import { userChatFolder, userHomePaths } from "./user-home.ts";

/** The stored conversation of one provider keeps at most this many turns and this many bytes; the oldest turns go first. */
export const MAX_HISTORY_TURNS = 200;
export const MAX_HISTORY_BYTES = 1024 * 1024;
/** One stored turn keeps at most this many events and this many bytes; a longer one loses its least important events. */
export const MAX_TURN_EVENTS = 1000;
export const MAX_STORED_LINE_BYTES = 256 * 1024;
/** A turn lists at most this many changed files. */
const MAX_LISTED_FILES = 300;
/** One prompt or one answer is shortened beyond this many characters. */
const MAX_TEXT_CHARS = 50_000;
const SHORTENED = "\n[shortened by Caztor to keep the saved conversation small]";

const EVENT_TYPES: ReadonlySet<string> = new Set([
  "session", "text_delta", "text", "tool_start", "tool_update", "tool_end", "notice", "error", "done", "turn_started", "files_changed",
]);

export interface ChatHistoryOptions {
  fs: FileSystem;
  /** Absolute path of the project folder. */
  root: string;
  /** A collaborator's id: their turns go to their private folder (see `userChatFolder`). Missing for the host, whose turns stay in `.caztor/chat/`. */
  userId?: string;
  /** Where the collaborators' private folders live; needed with `userId`. */
  configHome?: string;
}

const lock = createKeyedLock();

/** The history location is a link or something else it must not use; the message is fit for the user. */
class ChatHistoryRefused extends Error {}
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function parseLine(line: string, provider: ProviderId): ChatTurnRecord | null {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  const { turnId, prompt, startedAt, events } = value;
  if (value["provider"] !== provider || typeof turnId !== "string" || typeof prompt !== "string" || typeof startedAt !== "number") return null;
  if (!Array.isArray(events)) return null;
  const known = events.filter((event): event is TurnEvent => isRecord(event) && typeof event["type"] === "string" && EVENT_TYPES.has(event["type"]));
  return { turnId, provider, prompt, startedAt, events: known };
}

const shorten = (text: string, limit = MAX_TEXT_CHARS) => (text.length > limit ? text.slice(0, limit) + SHORTENED : text);

const ESSENTIAL: ReadonlySet<string> = new Set(["turn_started", "error", "done", "files_changed"]);

function limited(record: ChatTurnRecord, textLimit: number): ChatTurnRecord {
  return {
    ...record,
    prompt: shorten(record.prompt, textLimit),
    events: record.events.map((event) => {
      if (event.type === "text" || event.type === "text_delta") return { ...event, text: shorten(event.text, textLimit) };
      if (event.type === "files_changed" && event.files.length > MAX_LISTED_FILES) return { ...event, files: event.files.slice(0, MAX_LISTED_FILES) };
      return event;
    }),
  };
}

/** At most `MAX_TURN_EVENTS` events: the essential ones stay, and the rest fill what is left, oldest first. */
function capEvents(events: TurnEvent[]): TurnEvent[] {
  if (events.length <= MAX_TURN_EVENTS) return events;
  const essential = events.filter((event) => ESSENTIAL.has(event.type)).length;
  let room = Math.max(0, MAX_TURN_EVENTS - essential);
  return events.filter((event) => {
    if (ESSENTIAL.has(event.type)) return true;
    if (event.type === "tool_update") return false;
    room -= 1;
    return room >= 0;
  });
}

/** A turn from before the event was bounded can name every unprotected file: keep the first few and the count. */
function boundedStart(event: TurnEvent): TurnEvent {
  if (event.type !== "turn_started" || event.unprotected.length <= MAX_NAMED_UNPROTECTED) return event;
  return { ...event, unprotected: event.unprotected.slice(0, MAX_NAMED_UNPROTECTED), unprotectedCount: event.unprotectedCount ?? event.unprotected.length };
}

/** The JSON line of one turn, shortened step by step until it fits `MAX_STORED_LINE_BYTES`. The reply's text is the last thing given up. */
function storedLine(record: ChatTurnRecord): string {
  let current = limited({ ...record, events: capEvents(record.events.map(boundedStart)) }, MAX_TEXT_CHARS);
  let line = JSON.stringify(current);
  for (const textLimit of [10_000, 2_000, 500]) {
    if (line.length <= MAX_STORED_LINE_BYTES) return line;
    current = limited(current, textLimit);
    line = JSON.stringify(current);
  }
  if (line.length <= MAX_STORED_LINE_BYTES) return line;
  current = { ...current, events: current.events.filter((event) => ESSENTIAL.has(event.type) || event.type === "text") };
  line = JSON.stringify(current);
  if (line.length > MAX_STORED_LINE_BYTES) {
    current = { ...current, events: current.events.filter((event) => ESSENTIAL.has(event.type)) };
    line = JSON.stringify(current);
  }
  return line.length <= MAX_STORED_LINE_BYTES ? line : JSON.stringify({ ...current, events: [], prompt: shorten(current.prompt, 500) });
}

/**
 * The conversation of each provider, one JSON line per turn, in `.caztor/chat/<provider>.jsonl` for the host and
 * `<configHome>/caztor/users/<userId>/chat/<project key>/<provider>.jsonl` for a collaborator, outside the shared project.
 */
export function createChatHistory(options: ChatHistoryOptions): ChatHistoryPort {
  const { fs, root, userId } = options;
  if (userId !== undefined && !isSafeUserId(userId)) throw new Error("The user id cannot name a folder.");
  if (userId !== undefined && options.configHome === undefined) throw new Error("A collaborator's conversation needs the configuration folder.");
  const own = userId === undefined ? null : { dir: userHomePaths(options.configHome!, userId).dir, folder: userChatFolder(options.configHome!, userId, root) };
  const folder = own === null ? `${root}/.caztor/chat` : own.folder;
  const fileOf = (provider: ProviderId) => `${folder}/${provider}.jsonl`;

  /**
   * Refuses a folder of the history that is a link or not a folder, and a history file that is a link, so the
   * history can neither be written nor read outside its own folder. A missing part is fine: it is created on write.
   */
  async function guard(provider: ProviderId): Promise<void> {
    // The names in messages are relative to the project, or name "your chat folder": a path on this computer is not for the user to read.
    const parts: Array<[string, string, boolean]> =
      own === null
        ? [
            [`${root}/.caztor`, ".caztor", true],
            [`${root}/.caztor/chat`, ".caztor/chat", true],
            [fileOf(provider), `.caztor/chat/${provider}.jsonl`, false],
          ]
        : [
            [own.dir, "Your private folder", true],
            [`${own.dir}/chat`, "Your chat folder", true],
            [folder, "Your chat folder", true],
            [fileOf(provider), "Your chat file", false],
          ];
    for (const [path, shown, isFolder] of parts) {
      let stats;
      try {
        stats = await fs.lstat(path);
      } catch (error) {
        if ((error as { code?: string } | null)?.code === "ENOENT") return;
        throw error;
      }
      if (stats.isSymbolicLink()) throw new ChatHistoryRefused(isFolder ? `${shown} is a link, not a plain folder` : `${shown} is a link`);
      if (isFolder ? !stats.isDirectory() : !stats.isFile()) throw new ChatHistoryRefused(`${shown} is not a plain ${isFolder ? "folder" : "file"}`);
    }
  }

  async function readTurns(provider: ProviderId): Promise<ChatTurnRecord[]> {
    let text: string;
    try {
      await guard(provider);
      text = new TextDecoder().decode(await fs.readFile(fileOf(provider)));
    } catch (error) {
      if (error instanceof ChatHistoryRefused || (error as { code?: string } | null)?.code === "ENOENT") return [];
      throw error;
    }
    const turns: Array<{ turn: ChatTurnRecord; size: number }> = [];
    for (const line of text.split("\n")) {
      // A line this long was not written by this version; reading it would only cost memory.
      if (line.trim() === "" || line.length > 2 * MAX_STORED_LINE_BYTES) continue;
      const turn = parseLine(line, provider);
      if (turn !== null) turns.push({ turn, size: line.length });
    }
    // The newest turns that fit the stored size limit: no answer is larger than the file may be.
    let size = 0;
    const kept: ChatTurnRecord[] = [];
    for (const entry of turns.reverse()) {
      size += entry.size + 1;
      if (size > MAX_HISTORY_BYTES) break;
      kept.unshift(entry.turn);
    }
    return kept;
  }

  async function write(provider: ProviderId, turns: ChatTurnRecord[]): Promise<void> {
    let lines = turns.map((turn) => storedLine(turn));
    let size = lines.reduce((sum, line) => sum + line.length + 1, 0);
    while (size > MAX_HISTORY_BYTES && lines.length > 1) {
      size -= lines[0]!.length + 1;
      lines = lines.slice(1);
    }
    // A collaborator's folders are closed to everyone else, as their private home is.
    await fs.mkdir(folder, own === null ? { recursive: true } : { recursive: true, mode: 0o700 });
    const temporary = `${fileOf(provider)}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temporary, new TextEncoder().encode(lines.map((line) => `${line}\n`).join("")), { mode: 0o600 });
      await fs.rename(temporary, fileOf(provider));
    } catch (error) {
      await fs.rm(temporary, { force: true }).catch(() => {});
      throw error;
    }
  }

  return {
    load: (provider) => lock([fileOf(provider)], () => readTurns(provider)),
    append: (record) =>
      lock([fileOf(record.provider)], async () => {
        if (!PROVIDER_IDS.includes(record.provider)) throw new Error(`Unknown provider: ${record.provider}`);
        await guard(record.provider);
        const turns = await readTurns(record.provider);
        turns.push(record);
        await write(record.provider, turns.slice(-MAX_HISTORY_TURNS));
      }),
    clear: (provider) =>
      lock([fileOf(provider)], async () => {
        try {
          await guard(provider);
        } catch (error) {
          if (error instanceof ChatHistoryRefused) return;
          throw error;
        }
        await fs.rm(fileOf(provider), { force: true });
      }),
  };
}
