/** Milliseconds between comment lines that keep an idle stream open through proxies and timeouts. */
export const HEARTBEAT_MS = 15_000;

/** The one timer the stream needs. The local `Clock` satisfies it; tests inject a fake. */
export interface HeartbeatClock {
  setTimeout(fn: () => void, ms: number): () => void;
}

/** A broadcast point for server events. Event names are `file_changed`, `compile.*` and the chat `TurnEvent` types. */
export interface EventHub {
  /** Sends an event to every connected client and returns its sequence id. */
  publish(event: string, data: unknown): number;
  /** Receives each event as a ready-to-send frame. Returns the unsubscribe function. */
  subscribe(listener: (frame: string) => void): () => void;
  subscriberCount(): number;
}

const EVENT_NAME = /^[A-Za-z0-9_.-]+$/;

/** One Server-Sent Events frame. `data` is single-line JSON, so an event can never span two frames. */
export function formatSseEvent(frame: { id: number; event: string; data: unknown }): string {
  if (!EVENT_NAME.test(frame.event)) throw new Error(`Invalid event name: ${JSON.stringify(frame.event)}`);
  return `id: ${frame.id}\nevent: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`;
}

export function createEventHub(): EventHub {
  const listeners = new Set<(frame: string) => void>();
  let sequence = 0;
  return {
    publish(event, data) {
      sequence += 1;
      const frame = formatSseEvent({ id: sequence, event, data });
      for (const listener of listeners) listener(frame);
      return sequence;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    subscriberCount: () => listeners.size,
  };
}

export const HEARTBEAT_FRAME = ": heartbeat\n\n";
