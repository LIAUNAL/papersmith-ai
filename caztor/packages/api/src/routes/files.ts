import { parseRelPath, markersKept, PAPER_MARKER_PREFIX } from "@caztor/core";
import type { ContentHash, RelPath } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { DEFAULT_UPLOAD_PATH as UPLOAD_PATH } from "../security.ts";
import { storeErrorResponse } from "../store-errors.ts";

const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/;

type Parsed<T> = { ok: true; value: T } | { ok: false; response: Response };

/** The `path` query parameter as a validated project path, or the error response to return. */
function pathParam(c: Context): Parsed<RelPath> {
  const raw = c.req.query("path");
  if (raw === undefined) return { ok: false, response: errorResponse(c, 400, "invalid_path", 'The "path" parameter is required.') };
  const parsed = parseRelPath(raw);
  return parsed.ok ? parsed : { ok: false, response: storeErrorResponse(c, parsed.error) };
}

/** A JSON object body, or the 400 response to return. */
async function jsonObject(c: Context): Promise<Parsed<Record<string, unknown>>> {
  const body = await readJson(c);
  if (!body.ok) return { ok: false, response: errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.") };
  if (!isRecord(body.value)) {
    return { ok: false, response: errorResponse(c, 400, "invalid_body", "The request body must be a JSON object.") };
  }
  return { ok: true, value: body.value };
}

/** Project file routes: tree, text read, hash-checked write, creation, rename, delete and upload. All sit behind the security gate. */
export function fileRoutes(app: Hono, deps: ApiDeps, uploadPath: string = UPLOAD_PATH): void {
  const { store } = deps;

  app.get("/api/files", async (c: Context) => c.json({ entries: await store.list() }));

  app.get("/api/files/content", async (c: Context) => {
    const path = pathParam(c);
    if (!path.ok) return path.response;
    const read = await store.readText(path.value);
    if (!read.ok) return storeErrorResponse(c, read.error);
    return c.json({ path: path.value, content: new TextDecoder().decode(read.value.bytes), hash: read.value.hash });
  });

  app.put("/api/files/content", async (c: Context) => {
    const path = pathParam(c);
    if (!path.ok) return path.response;
    const body = await jsonObject(c);
    if (!body.ok) return body.response;
    const { content, baseHash } = body.value;
    if (typeof content !== "string") return errorResponse(c, 400, "invalid_body", 'The "content" field must be a string.');
    if (baseHash !== null && (typeof baseHash !== "string" || !HASH_PATTERN.test(baseHash))) {
      return errorResponse(c, 400, "invalid_body", 'The "baseHash" field must be the hash the edit was based on, or null for a new file.');
    }
    // PaperSmith finds each block of the paper by its marker lines, so a save may change the text between them only.
    if (path.value.toLowerCase().endsWith(".tex")) {
      const before = await store.readText(path.value);
      if (before.ok && !markersKept(new TextDecoder().decode(before.value.bytes), content)) {
        return errorResponse(c, 409, "markers_changed", `This save would change or remove a PaperSmith block marker (a line starting with "${PAPER_MARKER_PREFIX}") in ${path.value}. PaperSmith finds each block by them, so keep them as they are.`);
      }
    }
    const written = await store.write(path.value, new TextEncoder().encode(content), baseHash as ContentHash | null);
    if (!written.ok) return storeErrorResponse(c, written.error);
    return c.json({ path: path.value, hash: written.value.hash });
  });

  app.post("/api/files", async (c: Context) => {
    const body = await jsonObject(c);
    if (!body.ok) return body.response;
    const { path: rawPath, kind } = body.value;
    if (typeof rawPath !== "string") return errorResponse(c, 400, "invalid_body", 'The "path" field must be a string.');
    if (kind !== "file" && kind !== "dir") return errorResponse(c, 400, "invalid_body", 'The "kind" field must be "file" or "dir".');
    const path = parseRelPath(rawPath);
    if (!path.ok) return storeErrorResponse(c, path.error);
    const created = kind === "dir" ? await store.mkdir(path.value) : await store.write(path.value, new Uint8Array(0), null);
    if (!created.ok) return storeErrorResponse(c, created.error);
    return c.json({ path: path.value, kind }, 201);
  });

  app.post("/api/files/rename", async (c: Context) => {
    const body = await jsonObject(c);
    if (!body.ok) return body.response;
    const { from: rawFrom, to: rawTo } = body.value;
    if (typeof rawFrom !== "string" || typeof rawTo !== "string") {
      return errorResponse(c, 400, "invalid_body", 'The "from" and "to" fields must be strings.');
    }
    const from = parseRelPath(rawFrom);
    if (!from.ok) return storeErrorResponse(c, from.error);
    const to = parseRelPath(rawTo);
    if (!to.ok) return storeErrorResponse(c, to.error);
    const renamed = await store.rename(from.value, to.value);
    if (!renamed.ok) return storeErrorResponse(c, renamed.error);
    return c.json({ from: from.value, to: to.value });
  });

  app.delete("/api/files", async (c: Context) => {
    const path = pathParam(c);
    if (!path.ok) return path.response;
    const recursive = c.req.query("recursive") === "true";
    const removed = await store.remove(path.value, { recursive });
    if (!removed.ok) {
      // The store has no dedicated code for a folder that still has content; tell the user what to confirm.
      if (!recursive && removed.error.code === "invalid_path" && (await isFolder(path.value))) {
        return errorResponse(c, 409, "not_empty", `"${path.value}" is a folder with content. Confirm to delete it with everything inside.`, {
          path: path.value,
        });
      }
      return storeErrorResponse(c, removed.error);
    }
    return c.json({ path: path.value });
  });

  app.post(uploadPath, async (c: Context) => {
    const path = pathParam(c);
    if (!path.ok) return path.response;
    const stored = await store.write(path.value, new Uint8Array(await c.req.arrayBuffer()), null);
    if (!stored.ok) return storeErrorResponse(c, stored.error);
    return c.json({ path: path.value, hash: stored.value.hash }, 201);
  });

  async function isFolder(path: RelPath): Promise<boolean> {
    return (await store.list()).some((entry) => entry.path === path && entry.kind === "dir");
  }
}
