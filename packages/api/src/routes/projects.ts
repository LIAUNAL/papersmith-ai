import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { userOf } from "../users.ts";

const STATUS = { invalid_path: 400, invalid_name: 400, folder_refused: 403, not_found: 404, turn_running: 409, exists: 409, not_available: 503 } as const;

/** `GET /api/projects`, `POST /api/projects/open` and `POST /api/projects/create`: the projects the navigator shows, and moving this server to one of them. */
export function projectRoutes(app: Hono, deps: ApiDeps): void {
  app.get("/api/projects", async (c: Context) => {
    if (deps.projects === undefined) return errorResponse(c, 503, "not_available", "This server cannot switch projects.");
    return c.json({ projects: await deps.projects.list() });
  });

  app.post("/api/projects/open", async (c: Context) => {
    if (deps.projects === undefined) return errorResponse(c, 503, "not_available", "This server cannot switch projects.");
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const path = isRecord(body.value) ? body.value["path"] : undefined;
    if (typeof path !== "string") return errorResponse(c, 400, "invalid_path", 'The folder must be a full path, for example "~/papers/my-paper".');
    // Any folder on the host's machine is the host's choice; a collaborator can only move between the listed projects.
    if (userOf(c)?.role === "collaborator" && !(await deps.projects.list()).some((entry) => entry.path === path)) {
      return errorResponse(c, 403, "host_only", "Only the host can open a folder that is not in the project list.");
    }
    const opened = await deps.projects.open(path);
    if (!opened.ok) return errorResponse(c, STATUS[opened.error.code], opened.error.code, opened.error.message);
    return c.json({ projects: await deps.projects.list() });
  });

  app.post("/api/projects/create", async (c: Context) => {
    if (deps.projects === undefined) return errorResponse(c, 503, "not_available", "This server cannot create projects.");
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const name = isRecord(body.value) ? body.value["name"] : undefined;
    const created = await deps.projects.create(typeof name === "string" ? name : "");
    if (!created.ok) return errorResponse(c, STATUS[created.error.code], created.error.code, created.error.message);
    return c.json({ projects: await deps.projects.list() });
  });
}
