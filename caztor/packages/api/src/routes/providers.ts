import { authModeOf, credentialSlot, loginHintOf, parseAuthMode, parseModel, PROVIDER_IDS, providerSlots, slotLabel } from "@caztor/core";
import type { CredentialStatus, ProjectConfigFinding, ProjectState, ProviderId, ProviderLogin, ProviderStatus } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { PERSON_UNAVAILABLE, personOf, userOf } from "../users.ts";

const isProvider = (value: unknown): value is ProviderId => typeof value === "string" && (PROVIDER_IDS as readonly string[]).includes(value);

const UNKNOWN_PROVIDER = "The provider must be claude, opencode, codex, antigravity or pi.";

function unavailable(provider: ProviderId, reason: string): ProviderStatus {
  return { provider, installed: false, unavailableReason: reason, requiresModel: false };
}

interface KeyBook {
  /** Every slot that has a key; empty when the store cannot be used. */
  stored: Map<string, CredentialStatus>;
  /** Why the keys cannot be shown, when they cannot. */
  problem?: string;
}

/** What the browser needs to know about how a provider signs in. It holds no key, only whether one is set and its last four characters. */
function authOf(provider: ProviderId, state: ProjectState, book: KeyBook, login: ProviderLogin) {
  const slot = credentialSlot(provider, state.models[provider] ?? null);
  const ready = slot.ok && book.stored.get(slot.value)?.set === true;
  return {
    mode: authModeOf(state.authModes, provider),
    modes: slot.ok || slot.error.code !== "mode_unsupported" ? ["account", "api"] : ["account"],
    keys: book.problem === undefined ? providerSlots(provider).map((name) => book.stored.get(name) ?? { slot: name, set: false }) : [],
    slot: slot.ok ? slot.value : null,
    ...(slot.ok ? {} : { slotProblem: slot.error.message }),
    apiReady: ready,
    ...(book.problem === undefined ? {} : { storeProblem: book.problem }),
    login,
    loginHint: loginHintOf(provider),
  };
}

/**
 * `GET /api/providers`, `POST /api/providers/recheck`, `PUT /api/providers/selected`, `PUT /api/providers/:id/model` and
 * `PUT /api/providers/:id/auth-mode`.
 * Detection runs once per provider and is cached until a re-check, because it starts the CLI.
 */
export function providerRoutes(app: Hono, deps: ApiDeps): void {
  const runners = deps.agents?.runners ?? {};
  const cache = new Map<ProviderId, ProviderStatus>();

  async function detect(provider: ProviderId): Promise<ProviderStatus> {
    const runner = runners[provider];
    if (runner === undefined) {
      return unavailable(provider, deps.agents === undefined ? "Agents are not set up in this server." : `Support for ${provider} is not available yet.`);
    }
    try {
      return await runner.detect();
    } catch (error) {
      return unavailable(provider, `${provider} could not be checked: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function statuses(refresh: boolean): Promise<ProviderStatus[]> {
    for (const provider of PROVIDER_IDS) {
      if (refresh || !cache.has(provider)) cache.set(provider, await detect(provider));
    }
    return PROVIDER_IDS.map((provider) => cache.get(provider)!);
  }

  /** The project files that make this provider's CLI run programs, or null. Read fresh every time: it is cheap and must be current. */
  async function projectConfigOf(provider: ProviderId): Promise<ProjectConfigFinding | null> {
    try {
      return (await runners[provider]?.projectConfig?.()) ?? null;
    } catch {
      return null;
    }
  }

  const trusted = async (provider: ProviderId, fingerprint: string, stored: string | undefined) =>
    deps.trust === undefined ? stored === fingerprint : deps.trust.holds(provider, fingerprint, stored);

  async function keyBook(credentials: ApiDeps["credentials"]): Promise<KeyBook> {
    if (credentials === undefined) return { stored: new Map(), problem: "This server cannot store API keys." };
    try {
      const listed = await credentials.list();
      if (!listed.ok) return { stored: new Map(), problem: listed.error.message };
      return { stored: new Map(listed.value.map((status) => [status.slot, status])) };
    } catch {
      return { stored: new Map(), problem: "The stored API keys could not be checked." };
    }
  }

  /** The model, auth mode, keys and login shown are the caller's own. */
  async function listing(c: Context, refresh = false): Promise<Response> {
    const person = personOf(c, deps);
    if (person === null) return errorResponse(c, 409, "person_unavailable", PERSON_UNAVAILABLE);
    const user = userOf(c);
    const found = await statuses(refresh);
    const state = await person.state.load();
    const book = await keyBook(person.credentials);
    const configs = new Map(await Promise.all(found.map(async (status) => [status.provider, await projectConfigOf(status.provider)] as const)));
    // Trust is the host's, kept in the shared project state; a collaborator sees whether the host confirmed it.
    const { projectCliConfigTrusted } = await deps.state.load();
    const confirmed = new Map(
      await Promise.all(
        [...configs].map(async ([provider, config]) => [provider, config !== null && (await trusted(provider, config.fingerprint, projectCliConfigTrusted[provider]))] as const),
      ),
    );
    return c.json({
      selected: state.selectedProvider,
      providers: found.map((status) => ({
        id: status.provider,
        installed: status.installed,
        ...(status.unavailableReason === undefined ? {} : { unavailableReason: status.unavailableReason }),
        ...(status.version === undefined ? {} : { version: status.version }),
        ...(status.versionWarning === undefined ? {} : { versionWarning: status.versionWarning }),
        ...(status.models === undefined ? {} : { models: status.models }),
        ...(status.defaultModel === undefined ? {} : { defaultModel: status.defaultModel }),
        requiresModel: status.requiresModel,
        ...(status.supportsModel === false ? { supportsModel: false } : {}),
        ...(status.note === undefined ? {} : { note: status.note }),
        ...(configs.get(status.provider) == null
          ? {}
          : {
              projectConfig: {
                files: configs.get(status.provider)!.files,
                fingerprint: configs.get(status.provider)!.fingerprint,
                confirmed: confirmed.get(status.provider) === true,
              },
            }),
        model: state.models[status.provider] ?? null,
        auth: authOf(status.provider, state, book, deps.agents?.turns.loginOf(status.provider, ...(user === null ? [] : [user])) ?? "unknown"),
      })),
    });
  }

  app.get("/api/providers", (c: Context) => listing(c));

  app.post("/api/providers/recheck", (c: Context) => listing(c, true));

  app.put("/api/providers/selected", async (c: Context) => {
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const provider = isRecord(body.value) ? body.value["provider"] : undefined;
    if (!isProvider(provider)) return errorResponse(c, 400, "invalid_provider", UNKNOWN_PROVIDER);
    const person = personOf(c, deps);
    if (person === null) return errorResponse(c, 409, "person_unavailable", PERSON_UNAVAILABLE);
    await person.state.update({ selectedProvider: provider });
    return listing(c);
  });

  app.post("/api/providers/:id/project-config/trust", async (c: Context) => {
    // The host's own turns run outside any sandbox with what is trusted here, so only the host may trust.
    if (userOf(c)?.role === "collaborator") return errorResponse(c, 403, "host_only", "Only the host can trust the project's CLI configuration.");
    const id = c.req.param("id");
    if (!isProvider(id)) return errorResponse(c, 404, "unknown_provider", UNKNOWN_PROVIDER);
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const fingerprint = isRecord(body.value) ? body.value["fingerprint"] : undefined;
    if (typeof fingerprint !== "string" || fingerprint === "") return errorResponse(c, 400, "invalid_fingerprint", 'The request must have a "fingerprint" field.');
    const current = await projectConfigOf(id);
    if (current === null) return errorResponse(c, 409, "no_project_config", "This project has no CLI configuration that needs to be trusted.");
    // The user confirms what was shown. If the files changed since, nothing is stored and the dialog must be shown again.
    if (current.fingerprint !== fingerprint) {
      return errorResponse(c, 409, "project_config_changed", "The project's CLI configuration changed since it was shown. Review it again.");
    }
    const { projectCliConfigTrusted } = await deps.state.load();
    const record = deps.trust === undefined ? current.fingerprint : await deps.trust.seal(id, current.fingerprint);
    await deps.state.update({ projectCliConfigTrusted: { ...projectCliConfigTrusted, [id]: record } });
    return listing(c);
  });

  app.put("/api/providers/:id/model", async (c: Context) => {
    const id = c.req.param("id");
    if (!isProvider(id)) return errorResponse(c, 404, "unknown_provider", UNKNOWN_PROVIDER);
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    if (!isRecord(body.value) || !("model" in body.value)) return errorResponse(c, 400, "invalid_model", 'The request must have a "model" field.');
    const parsed = parseModel(body.value["model"]);
    if (!parsed.ok) return errorResponse(c, 400, "invalid_model", parsed.message);
    const person = personOf(c, deps);
    if (person === null) return errorResponse(c, 409, "person_unavailable", PERSON_UNAVAILABLE);
    const { models } = await person.state.load();
    const { [id]: _previous, ...others } = models;
    await person.state.update({ models: parsed.value === null ? others : { ...others, [id]: parsed.value } });
    return listing(c);
  });

  app.put("/api/providers/:id/auth-mode", async (c: Context) => {
    const id = c.req.param("id");
    if (!isProvider(id)) return errorResponse(c, 404, "unknown_provider", UNKNOWN_PROVIDER);
    const body = await readJson(c);
    if (!body.ok) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const mode = parseAuthMode(isRecord(body.value) ? body.value["mode"] : undefined);
    if (mode === null) return errorResponse(c, 400, "invalid_mode", 'The mode must be "account" or "api".');
    const person = personOf(c, deps);
    if (person === null) return errorResponse(c, 409, "person_unavailable", PERSON_UNAVAILABLE);
    const state = await person.state.load();
    if (mode === "api") {
      const slot = credentialSlot(id, state.models[id] ?? null);
      if (!slot.ok) {
        // Without a vendor the key cannot be told apart yet, so the switch waits for a model; a vendor with no key route never works.
        return errorResponse(c, slot.error.code === "vendor_required" ? 409 : 400, slot.error.code === "vendor_required" ? "api_key_missing" : "mode_unsupported", slot.error.message);
      }
      const label = slotLabel(slot.value);
      const missing = () => errorResponse(c, 409, "api_key_missing", `No API key is stored for ${label}. Add one first, then switch.`);
      if (person.credentials === undefined) return missing();
      const found = await person.credentials.status(slot.value);
      if (!found.ok) return errorResponse(c, 409, "api_key_missing", found.error.message);
      if (!found.value.set) return missing();
    }
    await person.state.update({ authModes: { ...state.authModes, [id]: mode } });
    return listing(c);
  });
}
