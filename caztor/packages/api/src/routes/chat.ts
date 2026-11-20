import { PROVIDER_IDS } from "@caztor/core";
import type { ProviderId, StartRefusal, TurnService } from "@caztor/core";
import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { errorResponse, isRecord, readJson } from "../http.ts";
import { formatSseEvent, HEARTBEAT_FRAME, HEARTBEAT_MS } from "../sse.ts";
import { PERSON_UNAVAILABLE, personOf, userOf, type RequestUser } from "../users.ts";

const isProvider = (value: unknown): value is ProviderId => typeof value === "string" && (PROVIDER_IDS as readonly string[]).includes(value);
const UNKNOWN_PROVIDER = "The provider must be claude, opencode, codex, antigravity or pi.";
const MODES = ["strict", "skip_conflicts", "force"] as const;

const REFUSAL_STATUS: Record<StartRefusal["code"], 400 | 409> = {
  busy: 409,
  invalid_prompt: 400,
  unknown_provider: 409,
  not_installed: 409,
  model_required: 409,
  api_key_missing: 409,
  mode_unsupported: 400,
  person_unavailable: 409,
};

const HOST_REQUEST: RequestUser = { id: "host", name: "Host", role: "host" };
const userIn = (c: Context): RequestUser => userOf(c) ?? HOST_REQUEST;
const same = (a: { id: string }, b: RequestUser) => a.id === b.id || (a.id === "host" && b.role === "host");

/** A non-negative whole number from a header or query value, else 0. */
function sequence(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
}

/**
 * `POST /api/chat/turns` (the response is the turn's event stream), the stream of the current or a given turn,
 * stop, undo, replace definition, history and new chat. A turn runs on the server: closing a stream never stops it.
 */
export function chatRoutes(app: Hono, deps: ApiDeps): void {
  const agents = deps.agents;
  const unavailable = (c: Context) => errorResponse(c, 503, "chat_unavailable", "The chat is not set up in this server.");

  /** The turn's events as Server-Sent Events: what was missed after `after`, then the rest, ending with the turn. */
  function stream(c: Context, turns: TurnService, turnId: string, after: number): Response {
    const encoder = new TextEncoder();
    let release = (): void => {};
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        let cancelTimer = (): void => {};
        let closed = false;
        const close = () => {
          if (closed) return;
          closed = true;
          cancelTimer();
          controller.close();
        };
        const beat = () => {
          if (closed) return;
          controller.enqueue(encoder.encode(HEARTBEAT_FRAME));
          cancelTimer = deps.clock.setTimeout(beat, HEARTBEAT_MS);
        };
        cancelTimer = deps.clock.setTimeout(beat, HEARTBEAT_MS);
        const unsubscribe = turns.subscribe(
          turnId,
          {
            onEvent: (event, seq) => {
              if (!closed) controller.enqueue(encoder.encode(formatSseEvent({ id: seq, event: event.type, data: event })));
            },
            onEnd: close,
          },
          after,
        );
        release = () => {
          closed = true;
          cancelTimer();
          unsubscribe?.();
        };
        if (unsubscribe === null) close();
      },
      cancel: () => release(),
    });
    return c.body(body, 200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-store",
      "x-caztor-turn-id": turnId,
    });
  }

  /** The provider named by the request, else the one the person selected. */
  async function providerOf(c: Context, requested: unknown): Promise<{ ok: true; provider: ProviderId } | { ok: false; code: "invalid_provider" | "no_provider" }> {
    if (requested !== undefined && requested !== null) return isProvider(requested) ? { ok: true, provider: requested } : { ok: false, code: "invalid_provider" };
    const selected = (await (personOf(c, deps)?.state ?? deps.state).load()).selectedProvider;
    return selected === null ? { ok: false, code: "no_provider" } : { ok: true, provider: selected };
  }

  /**
   * Refuses following or stopping a turn someone else ran: while it runs with a 409 naming them, once it ended with
   * `gone` as if there were no such turn, so nothing of it (prompt, answer, session) reaches anyone else. Null when the
   * turn is the caller's or is not the latest.
   */
  function someoneElses(c: Context, turnId: string, gone: () => Response): Response | null {
    const current = agents?.turns.current();
    if (current == null || current.turnId !== turnId || same(current.owner, userIn(c))) return null;
    if (!current.running) return gone();
    return errorResponse(c, 409, "not_your_turn", `${current.owner.name} has a turn running. Wait for it to finish.`);
  }

  const providerProblem = (c: Context, code: "invalid_provider" | "no_provider") =>
    errorResponse(c, 400, code, code === "invalid_provider" ? UNKNOWN_PROVIDER : "Choose a provider first.");

  app.post("/api/chat/turns", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const body = await readJson(c);
    if (!body.ok || !isRecord(body.value)) return errorResponse(c, 400, "invalid_json", "The request body is not valid JSON.");
    const { prompt } = body.value;
    if (typeof prompt !== "string") return errorResponse(c, 400, "invalid_prompt", "The message must be text.");
    const chosen = await providerOf(c, body.value["provider"]);
    if (!chosen.ok) return providerProblem(c, chosen.code);
    const user = userOf(c);
    const started = await agents.turns.start({ provider: chosen.provider, prompt, ...(user === null ? {} : { user }) });
    if (!started.ok) return errorResponse(c, REFUSAL_STATUS[started.error.code], started.error.code, started.error.message);
    return stream(c, agents.turns, started.value.turnId, 0);
  });

  app.get("/api/chat/turns/current", (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const current = agents.turns.current();
    if (current === null) return errorResponse(c, 404, "no_turn", "There is no turn to follow yet.");
    const refused = someoneElses(c, current.turnId, () => errorResponse(c, 404, "no_turn", "There is no turn to follow yet."));
    if (refused !== null) return refused;
    return stream(c, agents.turns, current.turnId, sequence(c.req.header("last-event-id") ?? c.req.query("after")));
  });

  app.get("/api/chat/turns/:id/events", (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const id = c.req.param("id")!;
    if (agents.turns.current()?.turnId !== id) return errorResponse(c, 404, "unknown_turn", "Only the latest turn can be followed.");
    const refused = someoneElses(c, id, () => errorResponse(c, 404, "unknown_turn", "Only the latest turn can be followed."));
    if (refused !== null) return refused;
    return stream(c, agents.turns, id, sequence(c.req.header("last-event-id") ?? c.req.query("after")));
  });

  app.post("/api/chat/turns/:id/stop", (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const refused = someoneElses(c, c.req.param("id")!, () => errorResponse(c, 404, "no_running_turn", "That turn is not running."));
    if (refused !== null) return refused;
    if (!agents.turns.stop(c.req.param("id")!, userIn(c))) return errorResponse(c, 404, "no_running_turn", "That turn is not running.");
    return c.json({ stopped: true });
  });

  app.post("/api/chat/turns/:id/undo", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const body = await readJson(c);
    const mode = body.ok && isRecord(body.value) ? body.value["mode"] : undefined;
    if (typeof mode !== "string" || !(MODES as readonly string[]).includes(mode)) {
      return errorResponse(c, 400, "invalid_mode", "The mode must be strict, skip_conflicts or force.");
    }
    const result = await agents.turns.undo(c.req.param("id")!, mode as (typeof MODES)[number], userIn(c));
    switch (result.status) {
      case "restored":
        return c.json(result);
      case "conflict": {
        const names = result.conflicts.map((conflict) => conflict.path).join(", ");
        return errorResponse(c, 409, "undo_conflict", `These files changed after the turn, so nothing was undone: ${names}. Cancel, undo the rest and keep your edits, or overwrite your edits.`, {
          conflicts: result.conflicts,
        });
      }
      case "unavailable":
        return errorResponse(c, 409, "undo_unavailable", "This turn can no longer be undone.", { reason: result.reason });
      case "busy":
        return errorResponse(c, 409, "busy", "A turn is running. Undo when it has finished.");
      case "not_yours":
        return errorResponse(c, 409, "not_your_turn", result.message);
      case "failed":
        return errorResponse(c, 409, "undo_failed", result.message);
    }
  });

  app.post("/api/chat/definition/replace", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const body = await readJson(c);
    const provider = body.ok && isRecord(body.value) ? body.value["provider"] : undefined;
    if (!isProvider(provider)) return errorResponse(c, 400, "invalid_provider", UNKNOWN_PROVIDER);
    const result = await agents.turns.replaceDefinition(provider);
    if (!result.ok) return errorResponse(c, result.error.code === "busy" ? 409 : 500, result.error.code, result.error.message);
    return c.json(result.value);
  });

  /** `GET /api/chat/agents`: the project's own agents, by name and description, for the chat's slash menu. */
  app.get("/api/chat/agents", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const listed = (await agents.projectAgents?.list().catch(() => [])) ?? [];
    return c.json({ agents: listed.map(({ name, description }) => ({ name, description })) });
  });

  app.get("/api/chat/history", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const person = personOf(c, deps);
    if (person === null) return errorResponse(c, 409, "person_unavailable", PERSON_UNAVAILABLE);
    const chosen = await providerOf(c, c.req.query("provider"));
    if (!chosen.ok) return providerProblem(c, chosen.code);
    const user = userIn(c);
    const current = agents.turns.current();
    const undoable = await agents.undoable();
    const turns = (await person.history?.load(chosen.provider)) ?? [];
    // Each person is offered the undo only of a turn they may undo: their own, or for the host one of unknown origin.
    const undoableTurnId = undoable.ok && undoable.value !== null && (await agents.turns.mayUndo(undoable.value, user)) ? undoable.value : null;
    const mine = current === null || same(current.owner, user);
    return c.json({
      provider: chosen.provider,
      turns,
      undoableTurnId,
      undoProblem: undoable.ok ? null : undoable.error.message,
      running: current?.running === true,
      currentTurnId: current?.running === true && mine ? current.turnId : null,
      ...(current?.running === true && !mine ? { runningBy: current.owner.name } : {}),
    });
  });

  app.post("/api/chat/sessions/reset", async (c: Context) => {
    if (agents === undefined) return unavailable(c);
    const body = await readJson(c);
    const provider = body.ok && isRecord(body.value) ? body.value["provider"] : undefined;
    if (!isProvider(provider)) return errorResponse(c, 400, "invalid_provider", UNKNOWN_PROVIDER);
    if (!(await agents.turns.resetSession(provider, userIn(c)))) return errorResponse(c, 409, "busy", "A turn is running. Start a new chat when it has finished.");
    return c.json({ reset: true });
  });
}
