import { Hono } from "hono";
import { UPLOAD_PATH } from "../src/app.ts";
import { securityMiddleware, type SecurityConfig } from "../src/security.ts";

export const TOKEN = "launch-token-0123456789abcdef";
export const HOST = "127.0.0.1:4173";
export const ORIGIN = "http://127.0.0.1:4173";

export const security: SecurityConfig = {
  token: TOKEN,
  allowedHosts: ["127.0.0.1:4173", "localhost:4173"],
  allowedOrigins: ["http://127.0.0.1:4173", "http://localhost:4173"],
};

/** The security gate alone, in front of probe routes whose handlers record that they ran. */
export function probeApp(config: SecurityConfig = security): { app: Hono; calls: string[] } {
  const app = new Hono();
  for (const middleware of securityMiddleware(config)) app.use("*", middleware);
  const calls: string[] = [];
  app.get("/api/ping", (c) => {
    calls.push("GET /api/ping");
    return c.json({ ok: true });
  });
  app.post("/api/echo", async (c) => {
    calls.push("POST /api/echo");
    return c.json({ bytes: (await c.req.arrayBuffer()).byteLength });
  });
  app.delete("/api/echo", (c) => {
    calls.push("DELETE /api/echo");
    return c.json({ ok: true });
  });
  app.post(UPLOAD_PATH, async (c) => {
    calls.push(`POST ${UPLOAD_PATH}`);
    return c.json({ bytes: (await c.req.arrayBuffer()).byteLength });
  });
  app.get("/api", (c) => {
    calls.push("GET /api");
    return c.json({ ok: true });
  });
  app.post("/api", (c) => {
    calls.push("POST /api");
    return c.json({ ok: true });
  });
  app.post("/elsewhere", (c) => {
    calls.push("POST /elsewhere");
    return c.json({ ok: true });
  });
  app.get("/boom", () => {
    throw new Error("handler failure");
  });
  app.get("/index.html", (c) => {
    calls.push("GET /index.html");
    return c.html("<!doctype html><title>Caztor</title>");
  });
  return { app, calls };
}

export function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { host: HOST, "x-caztor-token": TOKEN, ...extra };
}

export function writeHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return headers({ origin: ORIGIN, "content-type": "application/json", ...extra });
}
