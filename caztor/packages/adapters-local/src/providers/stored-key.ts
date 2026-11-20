import type { AgentEvent, CredentialReaderPort, CredentialSlot } from "@caztor/core";
import { failed } from "./drive.ts";

/**
 * The key of one slot, read just before a process starts, or the events that end the turn. The store's message is
 * shown as it is: it never contains a key. `label` names the key for the user ("Claude", "the openai key of opencode").
 */
export async function readStoredKey(reader: CredentialReaderPort | undefined, slot: CredentialSlot, label: string): Promise<{ key: string } | { stop: AgentEvent[] }> {
  if (reader === undefined) return { stop: failed("auth", `${label} is set to use an API key, but Caztor has no place to read it from.`) };
  const read = await reader.read(slot);
  if (!read.ok) return { stop: failed("auth", read.error.message) };
  if (read.value === null) return { stop: failed("auth", `No API key is stored for ${label}. Add one in the chat settings, or switch to account sign-in.`) };
  return { key: read.value };
}
