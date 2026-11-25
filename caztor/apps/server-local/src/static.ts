import type { FileSystem } from "@caztor/adapters-local";
import type { Context, Hono } from "hono";
import { injectToken, NO_SESSION_PAGE } from "./html.ts";

export interface StaticOptions {
  /** Absolute path of the built web app (`apps/web/dist`). */
  webRoot: string;
  fs: FileSystem;
  /**
   * The token substituted into `index.html`, or a function that decides it per request: the launch token for the
   * host, a session's own token for a collaborator, null for anyone else, who gets a page without app or token.
   */
  token: string | ((c: Context) => Promise<string | null>);
  /** The page served when `token` gives null. Defaults to the collaborator sign-in page. */
  noSessionPage?: string;
}

const CONTENT_TYPES: Readonly<Record<string, string>> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
};

const INDEX = "index.html";

/** The decoded path segments, or null when the path could leave the web root or is malformed. */
function safeSegments(pathname: string): string[] | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (decoded.includes("\\") || decoded.includes("\0")) return null;
  const segments = decoded.split("/").filter((segment) => segment !== "");
  if (segments.some((segment) => segment === "." || segment === "..")) return null;
  return segments;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

/**
 * Serves the built web app from `webRoot`. Registered after the API routes and after the security
 * gate, so static files are also behind the Host check. `/api/*` is never answered with a page.
 */
export function registerStatic(app: Hono, options: StaticOptions): void {
  const { webRoot, fs, token } = options;
  const noSessionPage = options.noSessionPage ?? NO_SESSION_PAGE;

  app.get("*", async (c: Context) => {
    if (c.req.path === "/api" || c.req.path.startsWith("/api/")) return c.json({ error: "not_found" }, 404);
    const segments = safeSegments(c.req.path);
    if (segments === null) return c.notFound();
    const name = segments.length === 0 ? INDEX : segments.join("/");
    let bytes: Uint8Array;
    try {
      bytes = await fs.readFile(`${webRoot}/${name}`);
    } catch {
      return c.notFound();
    }
    const type = CONTENT_TYPES[extensionOf(name)] ?? "application/octet-stream";
    if (name === INDEX) {
      const pageToken = typeof token === "string" ? token : await token(c);
      if (pageToken === null) return c.body(noSessionPage, 401, { "content-type": type, "cache-control": "no-store" });
      const page = injectToken(new TextDecoder().decode(bytes), pageToken);
      return c.body(page, 200, { "content-type": type, "cache-control": "no-store" });
    }
    return c.body(bytes as Uint8Array<ArrayBuffer>, 200, { "content-type": type });
  });
}
