import { describe, expect, it } from "vitest";
import { cleanupProjects, harness, HOST } from "./support.ts";

cleanupProjects();

describe("GET /api/session", () => {
  it("is rejected without the launch token", async () => {
    const h = harness();
    const response = await h.call("GET", "/api/session", { headers: { "x-caztor-token": "wrong" } });
    expect(response.status).toBe(401);
  });

  it("is rejected for a foreign Host", async () => {
    const h = harness();
    const response = await h.call("GET", "/api/session", { headers: { host: "evil.example" } });
    expect(response.status).toBe(403);
  });

  it("returns the project name, default settings and unavailable engine and sandbox", async () => {
    const h = harness();
    const response = await h.call("GET", "/api/session");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(await response.json()).toEqual({
      project: { name: h.deps.projectName },
      engine: { available: false, reason: "No LaTeX engine is configured." },
      sandbox: { available: false },
      settings: {
        stopOnFirstError: false,
        autoCompile: true,
        sandboxedCompile: false,
        mainFile: null,
        disclosureAcknowledged: false,
      },
    });
  });

  it("reports the engine and sandbox the server detected", async () => {
    const h = harness({
      engine: async () => ({ ok: true, version: "0.15.0" }),
      sandbox: async () => ({ ok: true }),
    });
    const body = (await (await h.call("GET", "/api/session")).json()) as Record<string, unknown>;
    expect(body["engine"]).toEqual({ available: true, version: "0.15.0" });
    expect(body["sandbox"]).toEqual({ available: true });
  });

  it("passes on why the engine is unavailable", async () => {
    const h = harness({ engine: async () => ({ ok: false, reason: "Tectonic was not found on the PATH." }) });
    const body = (await (await h.call("GET", "/api/session")).json()) as Record<string, unknown>;
    expect(body["engine"]).toEqual({ available: false, reason: "Tectonic was not found on the PATH." });
  });

  it("does not expose provider sessions or provisioning records", async () => {
    const h = harness();
    await h.deps.state.update({ selectedProvider: "claude" });
    const text = await (await h.call("GET", "/api/session")).text();
    expect(text).not.toContain("provisioned");
    expect(text).not.toContain("sessions");
    expect(text).not.toContain(HOST);
  });
});

describe("PATCH /api/settings", () => {
  it("is rejected without the launch token", async () => {
    const h = harness();
    const response = await h.call("PATCH", "/api/settings", { body: { autoCompile: false }, headers: { "x-caztor-token": "" } });
    expect(response.status).toBe(401);
    expect((await h.deps.state.load()).autoCompile).toBe(true);
  });

  it("requires a JSON content type", async () => {
    const h = harness();
    const response = await h.call("PATCH", "/api/settings", { body: "{}", headers: { "content-type": "text/plain" } });
    expect(response.status).toBe(415);
  });

  it("applies a partial update, persists it and returns the settings", async () => {
    const h = harness();
    const response = await h.call("PATCH", "/api/settings", { body: { stopOnFirstError: true, mainFile: "main.tex" } });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      settings: {
        stopOnFirstError: true,
        autoCompile: true,
        sandboxedCompile: false,
        mainFile: "main.tex",
        disclosureAcknowledged: false,
      },
    });
    const saved = await h.deps.state.load();
    expect(saved.stopOnFirstError).toBe(true);
    expect(saved.mainFile).toBe("main.tex");
  });

  it("accepts the disclosure acknowledgement and clearing the main file", async () => {
    const h = harness();
    await h.call("PATCH", "/api/settings", { body: { mainFile: "main.tex" } });
    const response = await h.call("PATCH", "/api/settings", { body: { disclosureAcknowledged: true, mainFile: null } });
    const body = (await response.json()) as { settings: Record<string, unknown> };
    expect(body.settings["disclosureAcknowledged"]).toBe(true);
    expect(body.settings["mainFile"]).toBeNull();
  });

  it.each([
    ["invalid JSON", "{not json"],
    ["an array", "[]"],
    ["a string", '"x"'],
    ["an unknown setting", '{"autoCompile":true,"theme":"dark"}'],
    ["a setting that is not user-editable", '{"provisioned":{}}'],
    ["a session record", '{"sessions":{}}'],
    ["a boolean setting with a string", '{"autoCompile":"yes"}'],
    ["a main file with traversal", '{"mainFile":"../x.tex"}'],
    ["a main file in a reserved folder", '{"mainFile":".caztor/main.tex"}'],
    ["a main file that is not a string", '{"mainFile":3}'],
  ])("rejects %s with 400 and changes nothing", async (_label, body) => {
    const h = harness();
    const response = await h.call("PATCH", "/api/settings", { body });
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: expect.any(String), message: expect.any(String) });
    expect(await h.deps.state.load()).toEqual(await harness().deps.state.load());
  });
});
