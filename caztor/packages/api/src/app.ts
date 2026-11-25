import { Hono } from "hono";
import type { ApiDeps } from "./deps.ts";
import { chatRoutes } from "./routes/chat.ts";
import { compileRoutes } from "./routes/compile.ts";
import { credentialRoutes } from "./routes/credentials.ts";
import { eventRoutes } from "./routes/events.ts";
import { fileRoutes } from "./routes/files.ts";
import { loginRoutes } from "./routes/logins.ts";
import { projectRoutes } from "./routes/projects.ts";
import { providerRoutes } from "./routes/providers.ts";
import { sessionRoutes } from "./routes/session.ts";
import { userRoutes } from "./routes/users.ts";
import { collaboratorScope } from "./users.ts";
import { DEFAULT_UPLOAD_PATH, securityMiddleware, type SecurityConfig } from "./security.ts";

export { DEFAULT_UPLOAD_PATH as UPLOAD_PATH, MAX_JSON_BYTES, MAX_UPLOAD_BYTES } from "./security.ts";
export type { SecurityConfig } from "./security.ts";
export type { ApiDeps, FileStore, InviteSummary, Probe, ProjectOpenError, UserSummary, UsersError } from "./deps.ts";
export { createRateLimiter, HOST_USER, plainPage, SESSION_COOKIE, sessionCookieOf, userOf } from "./users.ts";
export type { RateLimiter, RequestUser, SessionLookup } from "./users.ts";
export { createEventHub, formatSseEvent, HEARTBEAT_MS } from "./sse.ts";
export type { EventHub, HeartbeatClock } from "./sse.ts";

/**
 * Builds the HTTP app. The security gate is registered first, so every route added afterwards,
 * API or static, is only reachable through it.
 */
export function createApp(deps: ApiDeps, security: SecurityConfig): Hono {
  const app = new Hono();
  for (const middleware of securityMiddleware(security)) app.use("*", middleware);
  app.use("/api/*", collaboratorScope);
  userRoutes(app, deps);
  sessionRoutes(app, deps);
  fileRoutes(app, deps, security.uploadPath ?? DEFAULT_UPLOAD_PATH);
  eventRoutes(app, deps);
  compileRoutes(app, deps);
  providerRoutes(app, deps);
  credentialRoutes(app, deps);
  loginRoutes(app, deps);
  chatRoutes(app, deps);
  projectRoutes(app, deps);
  return app;
}
