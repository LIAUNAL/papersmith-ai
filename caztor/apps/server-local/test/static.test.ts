import { fileURLToPath } from "node:url";
import { createApp } from "@caztor/api";
import { nodeFileSystem } from "@caztor/adapters-local";
import { describe, expect, it } from "vitest";
import { registerStatic } from "../src/static.ts";

/** A port whose every method fails loudly: static serving must never reach a store or state. */
function unusedPort<T extends object>(name: string): T {
  return new Proxy({}, { get: () => () => Promise.reject(new Error(`${name} is not used by static serving`)) }) as T;
}

const webRoot = fileURLToPath(new URL("./fixtures/web", import.meta.url));
const TOKEN = "launch-token-0123456789abcdef";
const HOST = "127.0.0.1:4317";

function build(root: string = webRoot) {
  const app = createApp(
    {
      projectName: "fixture",
      store: unusedPort("store"),
      state: unusedPort("state"),
      events: unusedPort("events"),
      clock: unusedPort("clock"),
    },
    { token: TOKEN, allowedHosts: [HOST], allowedOrigins: [`http://${HOST}`] },
  );
  registerStatic(app, { webRoot: root, fs: nodeFileSystem, token: TOKEN });
  return app;
}

const get = (app: ReturnType<typeof build>, path: string, host: string = HOST) =>
  app.request(path, { headers: { host } });

describe("static web app", () => {
  it("serves index.html at / with the launch token in the meta tag and no placeholder left", async () => {
    const response = await get(build(), "/");
    const html = await response.text();
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/html");
    expect(html).toContain(`<meta name="caztor-token" content="${TOKEN}" />`);
    expect(html).not.toContain("__CAZTOR_TOKEN__");
    expect(html).not.toMatch(/<script>/);
  });

  it("marks the page no-store so a cached copy never carries a stale token", async () => {
    expect((await get(build(), "/")).headers.get("cache-control")).toBe("no-store");
    expect((await get(build(), "/assets/app.js")).headers.get("cache-control")).toBeNull();
  });

  it("serves index.html at /index.html too", async () => {
    const response = await get(build(), "/index.html");
    expect(await response.text()).toContain(TOKEN);
  });

  it("serves assets with a content type and without touching them", async () => {
    const app = build();
    const script = await get(app, "/assets/app.js");
    expect(script.status).toBe(200);
    expect(script.headers.get("content-type")).toContain("text/javascript");
    expect(await script.text()).toBe('console.log("app");\n');
    const css = await get(app, "/assets/app.css");
    expect(css.headers.get("content-type")).toContain("text/css");
  });

  it("carries the security headers on static responses", async () => {
    const response = await get(build(), "/");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("content-security-policy")).toContain("script-src 'self'");
  });

  it("is behind the Host check", async () => {
    const response = await get(build(), "/", "evil.example");
    expect(response.status).toBe(403);
    expect(await response.text()).not.toContain(TOKEN);
  });

  it.each([
    ["a missing file", "/assets/missing.js"],
    ["a directory", "/assets"],
    ["an encoded parent segment", "/%2e%2e/package.json"],
    ["an encoded separator", "/..%2f..%2fpackage.json"],
    ["a backslash", "/assets%5C..%5Cindex.html"],
    ["a NUL byte", "/assets/app.js%00.png"],
    ["a malformed escape", "/%E0%A4%A"],
  ])("answers 404 for %s", async (_label, path) => {
    const response = await get(build(), path);
    expect(response.status).toBe(404);
  });

  it("answers 404 when the web app has not been built", async () => {
    const response = await get(build(`${webRoot}/does-not-exist`), "/");
    expect(response.status).toBe(404);
  });

  it("does not turn an unknown API path into the web page", async () => {
    const app = build();
    const withToken = await app.request("/api/nope", { headers: { host: HOST, "x-caztor-token": TOKEN } });
    expect(withToken.status).toBe(404);
    expect(await withToken.text()).not.toContain("<html");
    const without = await app.request("/api/nope", { headers: { host: HOST } });
    expect(without.status).toBe(401);
  });

  it("does not turn /api itself into the web page", async () => {
    const app = build();
    const withToken = await app.request("/api", { headers: { host: HOST, "x-caztor-token": TOKEN } });
    expect(withToken.status).toBe(404);
    expect(await withToken.text()).not.toContain("<html");
    expect((await app.request("/api", { headers: { host: HOST } })).status).toBe(401);
  });
});
