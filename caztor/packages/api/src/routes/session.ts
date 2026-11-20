import { parseRelPath } from "@caztor/core";
import type { ProjectState } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { userOf } from "../users.ts";

const BOOLEAN_SETTINGS = ["stopOnFirstError", "autoCompile", "sandboxedCompile", "disclosureAcknowledged"] as const;
type SettingsPatch = Partial<Pick<ProjectState, (typeof BOOLEAN_SETTINGS)[number] | "mainFile">>;

function settingsOf(state: ProjectState) {
  return {
    stopOnFirstError: state.stopOnFirstError,
    autoCompile: state.autoCompile,
    sandboxedCompile: state.sandboxedCompile,
    mainFile: state.mainFile,
    disclosureAcknowledged: state.disclosureAcknowledged,
  };
}

/** Validates a settings patch. Only the user-editable settings are accepted; anything else is refused. */
function parseSettingsPatch(body: unknown): { ok: true; patch: SettingsPatch } | { ok: false; message: string } {
  if (!isRecord(body)) return { ok: false, message: "The request body must be a JSON object." };
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(body)) {
    if ((BOOLEAN_SETTINGS as readonly string[]).includes(key)) {
      if (typeof value !== "boolean") return { ok: false, message: `The setting "${key}" must be true or false.` };
      patch[key] = value;
    } else if (key === "mainFile") {
      if (value !== null) {
        const parsed = typeof value === "string" ? parseRelPath(value) : null;
        if (parsed === null || !parsed.ok) return { ok: false, message: 'The setting "mainFile" must be a project file path or null.' };
        patch[key] = parsed.value;
      } else patch[key] = null;
    } else {
      return { ok: false, message: `"${key}" is not a setting that can be changed.` };
    }
  }
  return { ok: true, patch: patch as SettingsPatch };
}

interface Capability {
  available: boolean;
  version?: string;
  reason?: string;
}

async function probe(run: ApiDeps["engine"], notConfigured?: string): Promise<Capability> {
  if (run === undefined) return { available: false, ...(notConfigured === undefined ? {} : { reason: notConfigured }) };
  const result = await run();
  return {
    available: result.ok,
    ...(result.version === undefined ? {} : { version: result.version }),
    ...(result.ok || result.reason === undefined ? {} : { reason: result.reason }),
  };
}

/** `GET /api/session` and `PATCH /api/settings`. Registered behind the security gate by `createApp`. */
export function sessionRoutes(app: Hono, deps: ApiDeps): void {
  app.get("/api/session", async (c: Context) => {
    const state = await deps.state.load();
    const papersmith = (await deps.papersmith?.status()) ?? null;
    const user = userOf(c);
    return c.json({
      ...(papersmith === null ? {} : { papersmith }),
      ...(deps.embed === undefined ? {} : { embed: deps.embed }),
      // A single-user server answers as it always did; the user is named only once collaborators can sign in.
      ...(user === null || deps.collaboratorMode !== true ? {} : { user }),
      project: { name: deps.projectName, ...(deps.projectId === undefined ? {} : { id: deps.projectId }) },
      engine: await probe(deps.engine, "No LaTeX engine is configured."),
      sandbox: await probe(deps.sandbox),
      settings: settingsOf(state),
    });
  });

  app.patch("/api/settings", async (c: Context) => {
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const parsed = parseSettingsPatch(body.value);
    if (!parsed.ok) return errorResponse(c, 400, "invalid_settings", parsed.message);
    // Outside the sandbox the engine can read any file of the host's, so only the host decides.
    if (userOf(c)?.role === "collaborator" && "sandboxedCompile" in parsed.patch) {
      return errorResponse(c, 403, "host_only", "Only the host can change whether compiles run in the sandbox.");
    }
    return c.json({ settings: settingsOf(await deps.state.update(parsed.patch)) });
  });

  app.post("/api/papersmith/scaffold", async (c: Context) => {
    if ((await deps.papersmith?.status()) == null) return errorResponse(c, 404, "not_workspace", "This project is not a PaperSmith workspace.");
    const made = await deps.papersmith!.scaffold();
    if (!made.ok) return errorResponse(c, 409, "scaffold_refused", made.error.message);
    return c.json({ created: made.value });
  });
}
