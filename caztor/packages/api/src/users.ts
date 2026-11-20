import type { PersonalPorts } from "@caztor/core";
import type { Context, MiddlewareHandler } from "hono";
import type { ApiDeps } from "./deps.ts";

/** Who made a request: the host (launch token or host session) or a collaborator (cookie session plus its own token). */
export interface RequestUser {
  id: string;
  name: string;
  role: "host" | "collaborator";
}

declare module "hono" {
  interface ContextVariableMap {
    /** Set by the token check on every API request that passed it. Later code reads it with `userOf`. */
    user: RequestUser;
  }
}

/** The fixed identity of whoever presents the launch token. */
export const HOST_USER: RequestUser = { id: "host", name: "Host", role: "host" };

export const SESSION_COOKIE = "caztor_session";

/** The user of an API request, or null outside the API, where no token check runs. */
export function userOf(c: Context): RequestUser | null {
  return c.get("user") ?? null;
}

/**
 * The state, chat history and keys of whoever made the request. The host, and a request outside the API, get the
 * server's own, exactly as a single-user server uses them; a collaborator gets their own, or null where none are set up.
 */
export function personOf(c: Context, deps: ApiDeps): PersonalPorts | null {
  const user = userOf(c);
  if (user === null || user.role === "host") {
    return {
      state: deps.state,
      ...(deps.agents === undefined ? {} : { history: deps.agents.history }),
      ...(deps.credentials === undefined ? {} : { credentials: deps.credentials }),
    };
  }
  return deps.people?.(user) ?? null;
}

/** Answers a collaborator's request where per-person state is not set up. */
export const PERSON_UNAVAILABLE = "Your own chat settings are not set up in this server.";

/** The raw session secret from a `Cookie` header, or null. Only the first `caztor_session` counts. */
export function sessionCookieOf(header: string | undefined): string | null {
  if (header === undefined) return null;
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === SESSION_COOKIE) {
      const value = rest.join("=");
      return /^[A-Za-z0-9_-]{1,128}$/.test(value) ? value : null;
    }
  }
  return null;
}

/** A session cookie that only this site's own pages send, never readable by scripts. */
export function sessionCookie(secret: string, secure: boolean): string {
  return `${SESSION_COOKIE}=${secret}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000${secure ? "; Secure" : ""}`;
}

/** The address a request came from, as the Node adapter reports it; one shared key where it reports none. */
export function remoteAddressOf(c: Context): string {
  const env = c.env as { incoming?: { socket?: { remoteAddress?: string } } } | undefined;
  return env?.incoming?.socket?.remoteAddress ?? "unknown";
}

/** A light in-memory limit per key: at most `limit` hits in a fixed window. */
export interface RateLimiter {
  /** True while the key has used up its window. */
  limited(key: string): boolean;
  hit(key: string): void;
}

export function createRateLimiter(options: { limit: number; windowMs: number; now?: () => number }): RateLimiter {
  const now = options.now ?? Date.now;
  const windows = new Map<string, { start: number; count: number }>();
  const current = (key: string) => {
    const entry = windows.get(key);
    if (entry === undefined || now() - entry.start >= options.windowMs) return null;
    return entry;
  };
  return {
    limited: (key) => (current(key)?.count ?? 0) >= options.limit,
    hit(key) {
      const entry = current(key);
      if (entry === null) {
        // Old windows go when a new one starts, so the map cannot grow without bound.
        for (const [other, value] of windows) if (now() - value.start >= options.windowMs) windows.delete(other);
        windows.set(key, { start: now(), count: 1 });
      } else entry.count += 1;
    },
  };
}

/** Looks up a cookie session: its user and the per-session token its page carries, or null. */
export type SessionLookup = (secret: string) => Promise<{ user: RequestUser; token: string } | null>;

function under(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`);
}

/**
 * What a collaborator may not reach: the user routes belong to the host. The chat, providers, keys and sign-ins are
 * their own (per-person state, turns and sign-ins in their sandbox with their private home).
 */
export const collaboratorScope: MiddlewareHandler = async (c, next) => {
  if (userOf(c)?.role !== "collaborator") return next();
  if (under(c.req.path, "/api/users")) return c.json({ error: "host_only", message: "Only the host can manage collaborators." }, 403);
  return next();
};

const PAGE_ESCAPES: Readonly<Record<string, string>> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

const escapePage = (value: string) => value.replace(/[&<>"]/g, (character) => PAGE_ESCAPES[character] ?? character);

/** A small page without scripts or styles, for the moments the app itself cannot be shown. */
export function plainPage(title: string, text: string, head = ""): string {
  const escape = escapePage;
  return `<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${head}<title>${escape(title)}</title></head>\n<body><h1>${escape(title)}</h1><p>${escape(text)}</p></body>\n</html>\n`;
}

/** The id of an invite link: base64url, as the users store makes it. */
export const INVITE_ID = /^[A-Za-z0-9_-]{16,64}$/;

/** What a wrong, expired, locked or unknown key gets: the same words for all of them. */
export const KEY_REFUSED = "That key does not work. Check it, or ask the host for a new invite.";

/**
 * The page an invite link opens: a plain form that posts the access key back to the same link. No script, so the
 * strict CSP holds. Its own referrer policy keeps the post's `Origin` header (the server's `no-referrer` would make it
 * `null`, which the Origin check refuses).
 */
export function keyPage(inviteId: string, problem?: string): string {
  const alert = problem === undefined ? "" : `<p role="alert">${escapePage(problem)}</p>`;
  return [
    "<!doctype html>",
    '<html lang="en">',
    '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="same-origin"><title>Sign in to Caztor</title></head>',
    "<body>",
    "<h1>Sign in to Caztor</h1>",
    "<p>Type the access key the host gave you with this link. It works on this browser and others until it expires.</p>",
    alert,
    `<form method="post" action="/invite/${escapePage(inviteId)}">`,
    '<label for="key">Access key</label> ',
    '<input id="key" name="key" type="text" required maxlength="64" autocomplete="off" autocapitalize="characters" spellcheck="false" autofocus placeholder="ABCDE-FGH23-JKMNP-QRST4"> ',
    '<button type="submit">Sign in</button>',
    "</form>",
    "</body>",
    "</html>",
    "",
  ].join("\n");
}
