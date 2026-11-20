import type { Context, Hono } from "hono";
import { bodyLimit } from "hono/body-limit";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { INVITE_ID, KEY_REFUSED, keyPage, plainPage, remoteAddressOf, sessionCookie, userOf } from "../users.ts";

const STATUS = { invalid_name: 400, invalid_lifetime: 400, not_found: 404, host_refused: 409, not_exposed: 409, busy: 503, io: 500, unsafe: 500, corrupt: 500 } as const;
const PAGE_HEADERS = { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" };
/** The same page for a used, expired or unknown host link: nobody learns which. */
const REFUSED = plainPage("This link cannot be used", "Ask the host for a new invite link.");
const TOO_MANY = plainPage("Too many tries", "Wait a minute, then try again.");
/** A key and its form field fit in far less; anything bigger is not a sign-in. */
const MAX_SIGN_IN_BYTES = 4096;
const LIFETIME_MESSAGE = "Choose how long the key lasts: from 10 minutes to 365 days.";

const isJson = (c: Context) => (c.req.header("content-type") ?? "").split(";")[0]?.trim().toLowerCase() === "application/json";

/** The access key a sign-in posted, as a form field or a JSON property; "" when there is none. */
async function postedKey(c: Context): Promise<string> {
  try {
    if (isJson(c)) {
      const body = (await c.req.json()) as unknown;
      return isRecord(body) && typeof body["key"] === "string" ? body["key"] : "";
    }
    return new URLSearchParams(await c.req.text()).get("key") ?? "";
  } catch {
    return "";
  }
}

/**
 * Host-only collaborator management under `/api/users`, and the pages that turn into a cookie session: an invite link,
 * `/invite/<id>`, which only shows a form for the access key and takes it back by POST, and this launch's one-time host
 * link, `/host/<code>`. They are page navigations, so they sit outside the API.
 */
export function userRoutes(app: Hono, deps: ApiDeps): void {
  const hostOnly = (c: Context) => (userOf(c)?.role === "host" ? null : errorResponse(c, 403, "host_only", "Only the host can manage collaborators."));
  const unavailable = (c: Context) => errorResponse(c, 503, "not_available", "This server cannot keep collaborators: it has no configuration folder.");

  app.get("/api/users", async (c: Context) => {
    const refused = hostOnly(c);
    if (refused !== null) return refused;
    if (deps.users === undefined) return unavailable(c);
    const listed = await deps.users.list();
    if (!listed.ok) return errorResponse(c, STATUS[listed.error.code], listed.error.code, listed.error.message);
    return c.json({ users: listed.value.filter((user) => user.role === "collaborator") });
  });

  app.post("/api/users/invites", async (c: Context) => {
    const refused = hostOnly(c);
    if (refused !== null) return refused;
    if (deps.users === undefined) return unavailable(c);
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const name = isRecord(body.value) ? body.value["name"] : undefined;
    const minutes = isRecord(body.value) && "minutes" in body.value ? body.value["minutes"] : undefined;
    if (minutes !== undefined && typeof minutes !== "number") return errorResponse(c, 400, "invalid_lifetime", LIFETIME_MESSAGE);
    const invited = await deps.users.invite(typeof name === "string" ? name : "", minutes);
    if (!invited.ok) return errorResponse(c, STATUS[invited.error.code], invited.error.code, invited.error.message);
    return c.json(invited.value, 201);
  });

  app.delete("/api/users/invites/:id", async (c: Context) => {
    const refused = hostOnly(c);
    if (refused !== null) return refused;
    if (deps.users === undefined) return unavailable(c);
    const revoked = await deps.users.revokeInvite(c.req.param("id") ?? "");
    if (!revoked.ok) return errorResponse(c, STATUS[revoked.error.code], revoked.error.code, revoked.error.message);
    return c.json({ revoked: true });
  });

  app.delete("/api/users/:id", async (c: Context) => {
    const refused = hostOnly(c);
    if (refused !== null) return refused;
    if (deps.users === undefined) return unavailable(c);
    const revoked = await deps.users.revoke(c.req.param("id") ?? "");
    if (!revoked.ok) return errorResponse(c, STATUS[revoked.error.code], revoked.error.code, revoked.error.message);
    return c.json({ revoked: true });
  });

  const secureOf = (c: Context) => deps.users?.secureCookies === true || new URL(c.req.url).protocol === "https:";

  // The link alone signs no one in and changes nothing, so a preview bot that fetches it uses nothing up. The same
  // form answers every well-formed id, known or not.
  app.get("/invite/:id", (c: Context) => {
    const id = c.req.param("id") ?? "";
    return INVITE_ID.test(id) ? c.body(keyPage(id), 200, PAGE_HEADERS) : c.body(REFUSED, 403, PAGE_HEADERS);
  });

  app.post(
    "/invite/:id",
    bodyLimit({ maxSize: MAX_SIGN_IN_BYTES, onError: (c) => c.body(REFUSED, 413, PAGE_HEADERS) }),
    async (c: Context) => {
      const id = c.req.param("id") ?? "";
      const json = isJson(c);
      const users = deps.users;
      const key = await postedKey(c);
      const secret = users === undefined || !INVITE_ID.test(id) ? null : await users.signIn(id, key);
      if (secret === null) {
        // Only failures count and only failures are refused, so others' wrong keys never lock a valid key out.
        const address = remoteAddressOf(c);
        const limited = users?.redemptions.limited(address) === true;
        users?.redemptions.hit(address);
        if (json) return limited ? errorResponse(c, 429, "too_many_attempts", "Too many tries. Wait a minute, then try again.") : errorResponse(c, 403, "invalid_key", KEY_REFUSED);
        if (limited) return c.body(TOO_MANY, 429, PAGE_HEADERS);
        return c.body(INVITE_ID.test(id) ? keyPage(id, KEY_REFUSED) : REFUSED, 403, PAGE_HEADERS);
      }
      const cookie = sessionCookie(secret, secureOf(c));
      if (json) return c.json({ signedIn: true }, 200, { "cache-control": "no-store", "set-cookie": cookie });
      // The post came from this site's own page, so the redirect stays same-site and the Strict cookie goes with it.
      return c.body(null, 303, { location: "/", "cache-control": "no-store", "set-cookie": cookie });
    },
  );

  app.get("/host/:code", async (c: Context) => {
    const users = deps.users;
    if (users === undefined) return c.body(REFUSED, 403, PAGE_HEADERS);
    const address = remoteAddressOf(c);
    const secret = await users.redeemHost(c.req.param("code") ?? "");
    if (secret === null) {
      const limited = users.redemptions.limited(address);
      users.redemptions.hit(address);
      return limited ? c.body(plainPage("Too many tries", "Wait a minute, then open the link again."), 429, PAGE_HEADERS) : c.body(REFUSED, 403, PAGE_HEADERS);
    }
    // A page that moves on by itself rather than a 302: after a link opened from another site, a SameSite=Strict
    // cookie is only sent once the navigation starts from this site.
    const page = plainPage("Signed in", "Opening Caztor.", '<meta http-equiv="refresh" content="0;url=/">');
    return c.body(page, 200, { ...PAGE_HEADERS, "set-cookie": sessionCookie(secret, secureOf(c)) });
  });
}
