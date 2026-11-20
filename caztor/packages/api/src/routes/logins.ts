import { LOGIN_KEYS, MAX_LOGIN_INPUT, PROVIDER_IDS, type LoginKey, type ProviderId } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson, type ErrorStatus } from "../http.ts";
import { HOST_USER, userOf } from "../users.ts";

const isProvider = (value: unknown): value is ProviderId => typeof value === "string" && (PROVIDER_IDS as readonly string[]).includes(value);
const UNKNOWN_PROVIDER = "The provider must be claude, opencode, codex, antigravity or pi.";

const START_STATUS: Readonly<Record<string, ErrorStatus>> = { unknown_method: 400, not_installed: 409, isolation_failed: 409, unavailable: 503 };
const INPUT_STATUS: Readonly<Record<string, ErrorStatus>> = { not_found: 404, ended: 409, invalid_input: 400 };

/**
 * `POST /api/logins/:provider` starts a sign-in to the provider's CLI, `GET` follows it (poll), `POST .../input` sends a
 * line or a key, `DELETE` cancels it. Everyone acts only on their own sign-in: a collaborator's runs in their sandbox
 * with their private home, the host's as a terminal of the host would. One sign-in at a time per person.
 */
export function loginRoutes(app: Hono, deps: ApiDeps): void {
  const prepare = (c: Context) => {
    const provider = c.req.param("provider");
    if (!isProvider(provider)) return { response: errorResponse(c, 404, "unknown_provider", UNKNOWN_PROVIDER) } as const;
    if (deps.logins === undefined) return { response: errorResponse(c, 503, "logins_unavailable", "Signing in from the browser is not set up in this server.") } as const;
    return { provider, logins: deps.logins, user: userOf(c) ?? HOST_USER } as const;
  };

  app.post("/api/logins/:provider", async (c: Context) => {
    const ready = prepare(c);
    if ("response" in ready) return ready.response;
    const body = c.req.header("content-length") === "0" ? { ok: true as const, value: {} } : await readJson(c);
    const method = body.ok && isRecord(body.value) ? body.value["method"] : undefined;
    if (method !== undefined && typeof method !== "string") return errorResponse(c, 400, "invalid_method", 'The "method" must be a string.');
    const started = await ready.logins.start(ready.user, ready.provider, method);
    if (!started.ok) return errorResponse(c, START_STATUS[started.error.code] ?? 409, started.error.code, started.error.message);
    return c.json({ login: started.value, methods: ready.logins.methods(ready.provider) }, 201);
  });

  app.get("/api/logins/:provider", (c: Context) => {
    const ready = prepare(c);
    if ("response" in ready) return ready.response;
    return c.json({ login: ready.logins.view(ready.user, ready.provider), methods: ready.logins.methods(ready.provider) });
  });

  app.post("/api/logins/:provider/input", async (c: Context) => {
    const ready = prepare(c);
    if ("response" in ready) return ready.response;
    const body = await readJson(c);
    if (!body.ok || !isRecord(body.value)) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const { line, key } = body.value;
    let input: { line: string } | { key: LoginKey };
    if (typeof line === "string" && key === undefined) {
      if (line.length > MAX_LOGIN_INPUT) return errorResponse(c, 400, "invalid_input", `A line can be at most ${MAX_LOGIN_INPUT} characters.`);
      input = { line };
    } else if (typeof key === "string" && line === undefined && (LOGIN_KEYS as readonly string[]).includes(key)) input = { key: key as LoginKey };
    else return errorResponse(c, 400, "invalid_input", `Send {"line": "..."} or {"key": "${LOGIN_KEYS.join('" | "')}"}.`);
    const sent = ready.logins.send(ready.user, ready.provider, input);
    if (!sent.ok) return errorResponse(c, INPUT_STATUS[sent.error.code] ?? 400, sent.error.code, sent.error.message);
    return c.json({ login: sent.value });
  });

  app.delete("/api/logins/:provider", (c: Context) => {
    const ready = prepare(c);
    if ("response" in ready) return ready.response;
    if (!ready.logins.cancel(ready.user, ready.provider)) return errorResponse(c, 404, "not_found", "There is no sign-in of yours to this provider.");
    return c.json({ login: ready.logins.view(ready.user, ready.provider) });
  });
}
