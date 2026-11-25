import { parseRelPath } from "@caztor/core";
import type { RelPath } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord } from "../http.ts";

const ENGINE_MISSING =
  "The LaTeX engine (Tectonic) was not found. Install Tectonic and make sure it is on the PATH, then compile again.";

type MainChoice = { ok: true; main: RelPath } | { ok: false; status: 400 | 404 | 409; error: string; message: string };

/** The request body: nothing, `{}` or `{ "main": "path.tex" }`. */
async function readBody(c: Context): Promise<{ ok: true; main: unknown } | { ok: false }> {
  const text = await c.req.text();
  if (text.trim() === "") return { ok: true, main: undefined };
  try {
    const value: unknown = JSON.parse(text);
    return isRecord(value) ? { ok: true, main: value["main"] } : { ok: false };
  } catch {
    return { ok: false };
  }
}

/** The main file: the request's, else the project's setting, else `main.tex`, else the only top-level `.tex` file, else PaperSmith's `paper/main.tex`. */
async function chooseMain(deps: ApiDeps, requested: unknown, configured: RelPath | null): Promise<MainChoice> {
  const files = new Set((await deps.store.list()).filter((entry) => entry.kind === "file").map((entry) => entry.path as string));
  // In a PaperSmith workspace the paper is always at the same place.
  const workspace = (await deps.papersmith?.status()) ?? null;
  let wanted: unknown = requested ?? configured ?? (workspace?.exists === true ? workspace.main : null);
  if (wanted === undefined || wanted === null) {
    const topLevel = [...files].filter((path) => !path.includes("/") && path.endsWith(".tex"));
    if (files.has("main.tex")) wanted = "main.tex";
    else if (topLevel.length === 1) wanted = topLevel[0];
    else if (files.has("paper/main.tex")) wanted = "paper/main.tex";
    else {
      return { ok: false, status: 409, error: "no_main_file", message: "Choose a main file in the settings before compiling." };
    }
  }
  const parsed = typeof wanted === "string" ? parseRelPath(wanted) : null;
  if (parsed === null || !parsed.ok) {
    return { ok: false, status: 400, error: "invalid_main", message: 'The main file must be a path inside the project, for example "main.tex".' };
  }
  if (!files.has(parsed.value)) {
    return { ok: false, status: 404, error: "main_not_found", message: `The main file "${parsed.value}" does not exist in the project.` };
  }
  return { ok: true, main: parsed.value };
}

/**
 * `POST /api/compile`, `POST /api/compile/cancel`, `GET /api/compile/status|pdf|log`, and the compile events on the
 * SSE stream. The PDF route serves only the promoted preview: no part of the request names a file.
 */
export function compileRoutes(app: Hono, deps: ApiDeps): void {
  const compile = deps.compile;
  if (compile !== undefined) {
    compile.coordinator.subscribe((event) => {
      const { type, ...data } = event;
      deps.events.publish(`compile.${type}`, data);
    });
  }

  app.post("/api/compile", async (c: Context) => {
    if (compile === undefined) return errorResponse(c, 503, "engine_unavailable", ENGINE_MISSING);
    const body = await readBody(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const state = await deps.state.load();
    const choice = await chooseMain(deps, body.main, state.mainFile);
    if (!choice.ok) return errorResponse(c, choice.status, choice.error, choice.message);
    // The engine can read any file it is given a path to, and a collaborator can write the source, so once collaborators
    // can reach the server every compile, the host's too, runs in the sandbox, which sees only the project.
    const forced = deps.collaboratorMode === true;
    if (forced) {
      const sandbox = deps.sandbox === undefined ? { ok: false, reason: "This server has no sandbox." } : await deps.sandbox().catch(() => ({ ok: false, reason: "The sandbox could not be checked." }));
      if (!sandbox.ok) {
        return errorResponse(c, 409, "sandbox_required", `Collaborators can reach this server, so every compile runs in the sandbox, and the sandbox cannot be used: ${sandbox.reason ?? "the reason is unknown."}`);
      }
    }
    if (!(await compile.compiler.available()).ok) return errorResponse(c, 503, "engine_unavailable", ENGINE_MISSING);
    const accepted = compile.coordinator.request({ main: choice.main, stopOnFirstError: state.stopOnFirstError, sandboxed: forced || state.sandboxedCompile });
    return c.json(accepted, 202);
  });

  app.post("/api/compile/cancel", (c: Context) => {
    return c.json(compile === undefined ? { cancelled: false } : compile.coordinator.cancel());
  });

  app.get("/api/compile/status", async (c: Context) => {
    const status = compile?.coordinator.status() ?? { running: null, queued: null, last: null };
    // The preview revision is clock-based, so after a restart the UI cannot know a preview exists unless told.
    const pdfAvailable = ((await compile?.compiler.readArtifact("pdf")) ?? null) !== null;
    return c.json({ ...status, pdfAvailable });
  });

  app.get("/api/compile/pdf", async (c: Context) => {
    const pdf = (await compile?.compiler.readArtifact("pdf")) ?? null;
    if (pdf === null) return errorResponse(c, 404, "no_pdf", "No PDF has been produced yet. Compile the project first.");
    return c.body(pdf as Uint8Array<ArrayBuffer>, 200, { "content-type": "application/pdf", "cache-control": "no-store" });
  });

  app.get("/api/compile/log", async (c: Context) => {
    const log = (await compile?.compiler.readArtifact("log")) ?? null;
    if (log === null) return errorResponse(c, 404, "no_log", "There is no compile log yet.");
    return c.body(log as Uint8Array<ArrayBuffer>, 200, { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" });
  });
}
