import type { Context, Hono } from "hono";
import type { ApiDeps } from "../deps.ts";
import { HEARTBEAT_FRAME, HEARTBEAT_MS } from "../sse.ts";

/** `GET /api/events`: a Server-Sent Events stream read with `fetch`, so the token header travels with it. */
export function eventRoutes(app: Hono, deps: ApiDeps): void {
  app.get("/api/events", (c: Context) => {
    const encoder = new TextEncoder();
    let release = (): void => {};
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const send = (frame: string) => controller.enqueue(encoder.encode(frame));
        const unsubscribe = deps.events.subscribe(send);
        let cancelTimer = (): void => {};
        const beat = () => {
          send(HEARTBEAT_FRAME);
          cancelTimer = deps.clock.setTimeout(beat, HEARTBEAT_MS);
        };
        cancelTimer = deps.clock.setTimeout(beat, HEARTBEAT_MS);
        release = () => {
          unsubscribe();
          cancelTimer();
        };
      },
      cancel: () => release(),
    });
    return c.body(body, 200, { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-store" });
  });
}
