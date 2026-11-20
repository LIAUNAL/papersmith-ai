import type { ProviderId, TurnEvent } from "./ports.ts";

/** One turn of the visible conversation: what the user wrote and what happened, ready to be replayed into the chat. */
export interface ChatTurnRecord {
  turnId: string;
  provider: ProviderId;
  /** What the user wrote, without any note Caztor added for the agent. */
  prompt: string;
  /** Milliseconds since the epoch when the turn was accepted. */
  startedAt: number;
  events: TurnEvent[];
}

export interface ChatHistoryPort {
  /** The stored turns of one provider, oldest first. */
  load(provider: ProviderId): Promise<ChatTurnRecord[]>;
  append(record: ChatTurnRecord): Promise<void>;
  /** Forgets the conversation of one provider (a new chat). */
  clear(provider: ProviderId): Promise<void>;
}

/**
 * Joins the text deltas of each message into one whole `text` event, at the place of its first delta, so a stored turn
 * is small. A whole `text` that arrives later replaces what the deltas said: it is authoritative.
 */
export function compactEvents(events: readonly TurnEvent[]): TurnEvent[] {
  const out: TurnEvent[] = [];
  const textAt = new Map<string, number>();
  for (const event of events) {
    if (event.type !== "text_delta" && event.type !== "text") {
      out.push(event);
      continue;
    }
    const at = textAt.get(event.messageId);
    if (at === undefined) {
      textAt.set(event.messageId, out.length);
      out.push({ type: "text", messageId: event.messageId, text: event.text });
      continue;
    }
    const known = out[at] as Extract<TurnEvent, { type: "text" }>;
    out[at] = { ...known, text: event.type === "text" ? event.text : known.text + event.text };
  }
  return out;
}
