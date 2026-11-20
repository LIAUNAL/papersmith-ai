import { describe, expect, it } from "vitest";
import { createApp } from "../src/app.ts";
import { securityMiddleware } from "../src/security.ts";
import { headers, HOST, ORIGIN, probeApp, security, TOKEN, writeHeaders } from "./support.ts";

describe("security middleware: gate scope", () => {
  it("applies the token gate to /api without a trailing slash", async () => {
    const { app, calls } = probeApp();
    const without = await app.request("/api", { headers: { host: HOST } });
    expect(without.status).toBe(401);
    expect(calls).toEqual([]);
    expect((await app.request("/api", { headers: headers() })).status).toBe(200);
    expect(calls).toEqual(["GET /api"]);
  });

  it("applies the content-type gate to a POST on /api", async () => {
    const { app, calls } = probeApp();
    const wrong = await app.request("/api", { method: "POST", headers: writeHeaders({ "content-type": "text/plain" }), body: "x" });
    expect(wrong.status).toBe(415);
    expect(calls).toEqual([]);
    const right = await app.request("/api", { method: "POST", headers: writeHeaders(), body: "{}" });
    expect(right.status).toBe(200);
  });

  it("does not treat a lookalike prefix as the API", async () => {
    const { app } = probeApp();
    expect((await app.request("/apiary", { headers: { host: HOST } })).status).toBe(404);
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])("refuses %s outside /api before any handler runs", async (method) => {
    const { app, calls } = probeApp();
    const response = await app.request("/elsewhere", { method, headers: writeHeaders(), body: "{}" });
    expect(response.status).toBe(405);
    expect(calls).toEqual([]);
  });

  it("still serves GET outside /api", async () => {
    const { app } = probeApp();
    expect((await app.request("/index.html", { headers: { host: HOST } })).status).toBe(200);
    const head = await app.request("/index.html", { method: "HEAD", headers: { host: HOST } });
    expect(head.status).not.toBe(405);
  });
});

describe("security middleware: configuration", () => {
  it.each([["an empty token", ""], ["a short token", "short-token"]])("refuses %s", (_label, token) => {
    expect(() => securityMiddleware({ ...security, token })).toThrow(/token/i);
    expect(() => createApp({} as never, { ...security, token })).toThrow(/token/i);
  });

  it("accepts a 16 character token", () => {
    expect(() => securityMiddleware({ ...security, token: "0123456789abcdef" })).not.toThrow();
  });
});

describe("security middleware: negative cases", () => {
  it.each([
    ["an uppercase host", "LOCALHOST:4173"],
    ["a host with a trailing dot", "127.0.0.1.:4173"],
    ["a localhost host with a trailing dot", "localhost.:4173"],
  ])("rejects %s", async (_label, host) => {
    const { app, calls } = probeApp();
    expect((await app.request("/api/ping", { headers: headers({ host }) })).status).toBe(403);
    expect(calls).toEqual([]);
  });

  it("rejects a token passed in the query string", async () => {
    const { app, calls } = probeApp();
    const response = await app.request(`/api/ping?token=${TOKEN}&x-caztor-token=${TOKEN}`, { headers: { host: HOST } });
    expect(response.status).toBe(401);
    expect(calls).toEqual([]);
  });

  it("sends the security headers on a 404 and on a 500", async () => {
    const { app } = probeApp();
    app.onError((_error, c) => c.text("failure", 500));
    for (const path of ["/missing", "/boom"]) {
      const response = await app.request(path, { headers: headers({ origin: ORIGIN }) });
      expect([404, 500]).toContain(response.status);
      expect(response.headers.get("content-security-policy")).toContain("default-src 'self'");
      expect(response.headers.get("x-content-type-options")).toBe("nosniff");
      expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    }
  });
});
