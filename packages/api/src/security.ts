import { bodyLimit } from "hono/body-limit";
import type { MiddlewareHandler } from "hono";
import { timingSafeEqual } from "./token.ts";
import { HOST_USER, remoteAddressOf, sessionCookieOf, type RateLimiter, type SessionLookup } from "./users.ts";

export const MAX_JSON_BYTES = 2 * 1024 * 1024;
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const TOKEN_HEADER = "x-caztor-token";

export interface SecurityConfig {
  /** The per-launch secret every API request must carry in `X-Caztor-Token`. */
  token: string;
  /** Exact `Host` header values, fixed at startup (for example `127.0.0.1:4173`). Never derived from a request. */
  allowedHosts: readonly string[];
  /** Exact `Origin` values, fixed at startup (for example `http://127.0.0.1:4173`). Never derived from a request. */
  allowedOrigins: readonly string[];
  /** The open project. A request naming another one was meant for the project open before, so it is refused. */
  projectId?: string;
  /** Route that receives raw uploads. Defaults to `/api/files/upload`. */
  uploadPath?: string;
  /**
   * Cookie sessions. A request without the launch token passes only with a session cookie this finds and, in
   * `X-Caztor-Token`, that session's own token. Without it, only the launch token is accepted.
   */
  sessions?: SessionLookup;
  /** Counts failed cookie checks per remote address. Only failures are throttled: a valid session always passes. */
  failedSessions?: RateLimiter;
  /** Exact origins allowed to show the pages in a frame. None by default: no page may frame Caztor. */
  frameAncestors?: readonly string[];
}

export const DEFAULT_UPLOAD_PATH = "/api/files/upload";

/** Scripts stay strict; only styles may be inline because CodeMirror and the pane library inject style elements. */
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "worker-src 'self' blob:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
].join("; ");

/** The policy with `frame-ancestors` naming the given origins instead of 'none'. */
export function contentSecurityPolicy(frameAncestors: readonly string[] = []): string {
  if (frameAncestors.length === 0) return CONTENT_SECURITY_POLICY;
  return CONTENT_SECURITY_POLICY.replace("frame-ancestors 'none'", `frame-ancestors ${frameAncestors.join(" ")}`);
}

const SAFE_METHODS = new Set(["GET", "HEAD"]);

/** Shortest accepted launch token; the real one is 32 random bytes. */
export const MIN_TOKEN_LENGTH = 16;

/** `/api` and everything below it, but not a lookalike such as `/apiary`. */
function isApiPath(path: string): boolean {
  return path === "/api" || path.startsWith("/api/");
}

const PROJECT_HEADER = "x-caztor-project";
/** An invite link: the only page that takes a POST. */
const INVITE_PATH = /^\/invite\/[^/]+$/;

function reject(status: 401 | 403 | 405 | 413 | 415 | 429, error: string): Response {
  return Response.json({ error }, { status });
}

function mediaType(header: string | undefined): string {
  return (header ?? "").split(";")[0]?.trim().toLowerCase() ?? "";
}

/**
 * Response headers on every response, then the request gate in order: Host, Origin, preflight, token, content type, body size.
 * Every allowlist comes from `config`; nothing is read from the request to widen it.
 */
export function securityMiddleware(config: SecurityConfig): MiddlewareHandler[] {
  if (config.token.length < MIN_TOKEN_LENGTH) {
    throw new Error(`The launch token must have at least ${MIN_TOKEN_LENGTH} characters`);
  }
  const uploadPath = config.uploadPath ?? DEFAULT_UPLOAD_PATH;
  const hosts = new Set(config.allowedHosts);
  const origins = new Set(config.allowedOrigins);
  const policy = contentSecurityPolicy(config.frameAncestors);

  const headers: MiddlewareHandler = async (c, next) => {
    await next();
    c.header("Content-Security-Policy", policy);
    c.header("X-Content-Type-Options", "nosniff");
    c.header("Referrer-Policy", "no-referrer");
  };

  const host: MiddlewareHandler = async (c, next) => {
    const value = c.req.header("host");
    if (value === undefined || !hosts.has(value)) return reject(403, "host_not_allowed");
    await next();
  };

  const origin: MiddlewareHandler = async (c, next) => {
    const value = c.req.header("origin");
    if (value !== undefined && !origins.has(value)) return reject(403, "origin_not_allowed");
    if (value === undefined && !SAFE_METHODS.has(c.req.method)) return reject(403, "origin_required");
    await next();
  };

  const preflight: MiddlewareHandler = async (c, next) => {
    if (c.req.method === "OPTIONS") return reject(403, "preflight_refused");
    await next();
  };

  const api = (handler: MiddlewareHandler): MiddlewareHandler => {
    return async (c, next) => (isApiPath(c.req.path) ? handler(c, next) : next());
  };

  /**
   * Outside the API only pages and assets exist, so nothing but reads may reach a handler. The one exception is the
   * access key an invite's sign-in page posts back to its own link; the Origin check above has already run for it.
   */
  const readOnlyOutsideApi: MiddlewareHandler = async (c, next) => {
    const signIn = c.req.method === "POST" && INVITE_PATH.test(c.req.path);
    if (!isApiPath(c.req.path) && !SAFE_METHODS.has(c.req.method) && !signIn) return reject(405, "method_not_allowed");
    await next();
  };

  /** The launch token makes the request the host's. Otherwise a session cookie and its own token make it that user's. */
  const token: MiddlewareHandler = async (c, next) => {
    const presented = c.req.header(TOKEN_HEADER) ?? "";
    if (timingSafeEqual(presented, config.token)) {
      c.set("user", HOST_USER);
      return next();
    }
    const secret = sessionCookieOf(c.req.header("cookie"));
    if (secret === null || config.sessions === undefined) return reject(401, "token_required");
    const address = remoteAddressOf(c);
    const session = await config.sessions(secret);
    if (session === null || !timingSafeEqual(presented, session.token)) {
      // Behind a proxy every request shares one address, so a valid session is never refused for others' failures.
      const limited = config.failedSessions?.limited(address) === true;
      config.failedSessions?.hit(address);
      return limited ? reject(429, "too_many_attempts") : reject(401, "token_required");
    }
    c.set("user", session.user);
    return next();
  };

  const project: MiddlewareHandler = async (c, next) => {
    const named = c.req.header(PROJECT_HEADER);
    if (named !== undefined && config.projectId !== undefined && named !== config.projectId) return Response.json({ error: "project_changed", message: "Caztor moved to another project, so this page is starting again." }, { status: 409 });
    await next();
  };

  const contentType: MiddlewareHandler = async (c, next) => {
    if (!SAFE_METHODS.has(c.req.method)) {
      const expected = c.req.path === uploadPath ? "application/octet-stream" : "application/json";
      if (mediaType(c.req.header("content-type")) !== expected) return reject(415, "unsupported_content_type");
    }
    await next();
  };

  const size: MiddlewareHandler = async (c, next) => {
    const maxSize = c.req.path === uploadPath ? MAX_UPLOAD_BYTES : MAX_JSON_BYTES;
    return bodyLimit({ maxSize, onError: () => reject(413, "body_too_large") })(c, next);
  };

  return [headers, host, origin, preflight, readOnlyOutsideApi, api(token), api(project), api(contentType), api(size)];
}
