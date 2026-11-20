import type { Context } from "hono";

export type ErrorStatus = 400 | 401 | 403 | 404 | 409 | 413 | 415 | 429 | 500 | 503;

/** The one error shape every route returns: a stable code for clients and a readable message for people. */
export function errorResponse(
  c: Context,
  status: ErrorStatus,
  error: string,
  message: string,
  extra: Record<string, unknown> = {},
): Response {
  return c.json({ error, message, ...extra }, status);
}

/** The parsed JSON body, or null when it is not valid JSON. */
export async function readJson(c: Context): Promise<{ ok: true; value: unknown } | { ok: false }> {
  try {
    return { ok: true, value: await c.req.json() };
  } catch {
    return { ok: false };
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
