import { parseApiKey, parseCredentialSlot } from "@caztor/core";
import type { CredentialError, CredentialStatus } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { personOf } from "../users.ts";

const UNKNOWN_SLOT = "That is not a key slot Caztor knows. Use claude, codex, opencode:<provider> or pi:<provider>.";

/** The slot named in the path, or null when it is not a known one (also for an undecodable path). */
function slotParam(c: Context): string | null {
  try {
    return parseCredentialSlot(decodeURIComponent(c.req.param("slot") ?? ""));
  } catch {
    return null;
  }
}

/** The browser learns whether a key is set and at most its last four characters, and never gets a response that could be cached. */
const echo = (c: Context, status: CredentialStatus): Response =>
  c.json({ slot: status.slot, set: status.set, ...(status.last4 === undefined ? {} : { last4: status.last4 }) }, 200, { "cache-control": "no-store" });

/** The store's refusal as a response. Its messages are fixed text and never contain a key. */
function refusal(c: Context, error: CredentialError): Response {
  if (error.code === "io") return errorResponse(c, 500, "credential_store_failed", error.message);
  return errorResponse(c, 409, "credential_store_unusable", error.message);
}

/**
 * `PUT /api/credentials/:slot` (the key travels in the JSON body only) and `DELETE /api/credentials/:slot`. Both answer
 * with the slot, whether it is set and at most the last four characters. There is no route that reads a key. Both act
 * on the caller's own store: the host's, or the collaborator's.
 */
export function credentialRoutes(app: Hono, deps: ApiDeps): void {
  const unavailable = (c: Context) => errorResponse(c, 503, "credentials_unavailable", "This server cannot store API keys.");

  app.put("/api/credentials/:slot", async (c: Context) => {
    const credentials = personOf(c, deps)?.credentials;
    if (credentials === undefined) return unavailable(c);
    const slot = slotParam(c);
    if (slot === null) return errorResponse(c, 404, "unknown_slot", UNKNOWN_SLOT);
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const key = parseApiKey(isRecord(body.value) ? body.value["key"] : undefined);
    if (!key.ok) return errorResponse(c, 400, "invalid_key", key.error.message);
    const saved = await credentials.set(slot, key.value);
    return saved.ok ? echo(c, saved.value) : refusal(c, saved.error);
  });

  app.delete("/api/credentials/:slot", async (c: Context) => {
    const credentials = personOf(c, deps)?.credentials;
    if (credentials === undefined) return unavailable(c);
    const slot = slotParam(c);
    if (slot === null) return errorResponse(c, 404, "unknown_slot", UNKNOWN_SLOT);
    const cleared = await credentials.clear(slot);
    return cleared.ok ? echo(c, cleared.value) : refusal(c, cleared.error);
  });
}
