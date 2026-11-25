import { describe, expect, it } from "vitest";
import { UPLOAD_PATH } from "../src/app.ts";
import { headers, HOST, ORIGIN, probeApp, TOKEN, writeHeaders } from "./support.ts";

const MB = 1024 * 1024;

describe("security middleware: Host allowlist", () => {
  it.each([
    ["a foreign host", "evil.example"],
    ["the right host on another port", "127.0.0.1:9999"],
    ["a lookalike suffix", "127.0.0.1:4173.evil.example"],
    ["no port", "127.0.0.1"],
  ])("rejects %s", async (_label, host) => {
    const { app, calls } = probeApp();
    const response = await app.request("/api/ping", { headers: headers({ host }) });
    expect(response.status).toBe(403);
    expect(calls).toEqual([]);
  });

  it("rejects a request without a Host header", async () => {
    const { app, calls } = probeApp();
    const response = await app.request("/api/ping", { headers: { "x-caztor-token": TOKEN } });
    expect(response.status).toBe(403);
    expect(calls).toEqual([]);
  });

  it("does not trust a forwarded host or an absolute URL to override the Host header", async () => {
    const { app } = probeApp();
    const forwarded = await app.request("/api/ping", { headers: headers({ host: "evil.example", "x-forwarded-host": HOST }) });
    expect(forwarded.status).toBe(403);
    const absolute = await app.request("http://evil.example/api/ping", { headers: headers() });
    expect(absolute.status).toBe(200);
  });

  it("accepts both fixed hosts", async () => {
    const { app } = probeApp();
    for (const host of ["127.0.0.1:4173", "localhost:4173"]) {
      expect((await app.request("/api/ping", { headers: headers({ host }) })).status).toBe(200);
    }
  });

  it("applies to static responses as well", async () => {
    const { app } = probeApp();
    expect((await app.request("/index.html", { headers: { host: "evil.example" } })).status).toBe(403);
    expect((await app.request("/index.html", { headers: { host: HOST } })).status).toBe(200);
  });
});

describe("security middleware: Origin allowlist", () => {
  it.each([["https://evil.example"], ["http://127.0.0.1:9999"], ["null"], ["http://127.0.0.1:4173.evil.example"]])(
    "rejects the origin %s on a read and on a write",
    async (origin) => {
      const { app, calls } = probeApp();
      expect((await app.request("/api/ping", { headers: headers({ origin }) })).status).toBe(403);
      expect((await app.request("/api/echo", { method: "POST", headers: writeHeaders({ origin }), body: "{}" })).status).toBe(403);
      expect(calls).toEqual([]);
    },
  );

  it("requires an Origin on state-changing requests but not on reads", async () => {
    const { app, calls } = probeApp();
    const noOrigin = await app.request("/api/echo", { method: "POST", headers: headers({ "content-type": "application/json" }), body: "{}" });
    expect(noOrigin.status).toBe(403);
    expect(calls).toEqual([]);
    expect((await app.request("/api/ping", { headers: headers() })).status).toBe(200);
  });

  it("accepts every allowed origin", async () => {
    const { app } = probeApp();
    for (const origin of ["http://127.0.0.1:4173", "http://localhost:4173"]) {
      expect((await app.request("/api/echo", { method: "POST", headers: writeHeaders({ origin }), body: "{}" })).status).toBe(200);
    }
  });
});

describe("security middleware: launch token", () => {
  it("requires the token on reads, writes and uploads, and runs no handler without it", async () => {
    const { app, calls } = probeApp();
    const noToken = { host: HOST };
    expect((await app.request("/api/ping", { headers: noToken })).status).toBe(401);
    expect((await app.request("/api/echo", { method: "POST", headers: { ...noToken, origin: ORIGIN, "content-type": "application/json" }, body: "{}" })).status).toBe(401);
    expect((await app.request(UPLOAD_PATH, { method: "POST", headers: { ...noToken, origin: ORIGIN, "content-type": "application/octet-stream" }, body: "x" })).status).toBe(401);
    expect(calls).toEqual([]);
  });

  it("rejects a stale or wrong token, including one that is a prefix of the real token", async () => {
    const { app, calls } = probeApp();
    for (const token of ["old-launch-token", "", TOKEN.slice(0, -1), `${TOKEN}x`]) {
      const response = await app.request("/api/ping", { headers: headers({ "x-caztor-token": token }) });
      expect(response.status).toBe(401);
    }
    expect(calls).toEqual([]);
  });

  it("accepts the right token", async () => {
    const { app, calls } = probeApp();
    const response = await app.request("/api/ping", { headers: headers() });
    expect(await response.json()).toEqual({ ok: true });
    expect(calls).toEqual(["GET /api/ping"]);
  });

  it("does not require the token for static pages, which carry it in the page", async () => {
    const { app } = probeApp();
    expect((await app.request("/index.html", { headers: { host: HOST } })).status).toBe(200);
  });
});

describe("security middleware: content type", () => {
  it.each([["text/plain"], ["application/x-www-form-urlencoded"], ["multipart/form-data; boundary=x"], ["application/octet-stream"], [""]])(
    "rejects a JSON route called with %j",
    async (contentType) => {
      const { app, calls } = probeApp();
      const base = writeHeaders();
      const { "content-type": _drop, ...withoutType } = base;
      const response = await app.request("/api/echo", {
        method: "POST",
        headers: contentType === "" ? withoutType : { ...withoutType, "content-type": contentType },
        body: "{}",
      });
      expect(response.status).toBe(415);
      expect(calls).toEqual([]);
    },
  );

  it("accepts JSON with parameters and in any letter case", async () => {
    const { app } = probeApp();
    for (const type of ["application/json", "application/json; charset=utf-8", "Application/JSON"]) {
      const response = await app.request("/api/echo", { method: "POST", headers: writeHeaders({ "content-type": type }), body: "{}" });
      expect(response.status).toBe(200);
    }
  });

  it("requires JSON on every state-changing method, even without a body", async () => {
    const { app, calls } = probeApp();
    const { "content-type": _drop, ...withoutType } = writeHeaders();
    expect((await app.request("/api/echo", { method: "DELETE", headers: withoutType })).status).toBe(415);
    expect(calls).toEqual([]);
    expect((await app.request("/api/echo", { method: "DELETE", headers: writeHeaders() })).status).toBe(200);
  });

  it("requires a binary stream on the upload route and rejects JSON there", async () => {
    const { app, calls } = probeApp();
    const json = await app.request(UPLOAD_PATH, { method: "POST", headers: writeHeaders(), body: "{}" });
    const text = await app.request(UPLOAD_PATH, { method: "POST", headers: writeHeaders({ "content-type": "text/plain" }), body: "x" });
    expect([json.status, text.status]).toEqual([415, 415]);
    expect(calls).toEqual([]);

    const ok = await app.request(UPLOAD_PATH, { method: "POST", headers: writeHeaders({ "content-type": "application/octet-stream" }), body: "abc" });
    expect(await ok.json()).toEqual({ bytes: 3 });
  });
});

describe("security middleware: preflight and CORS", () => {
  it("refuses a cross-origin preflight and an allowed-origin preflight alike", async () => {
    const { app, calls } = probeApp();
    for (const origin of ["https://evil.example", ORIGIN]) {
      const response = await app.request("/api/echo", {
        method: "OPTIONS",
        headers: headers({ origin, "access-control-request-method": "POST", "access-control-request-headers": "content-type,x-caztor-token" }),
      });
      expect(response.status).toBe(403);
      expect(response.headers.get("access-control-allow-origin")).toBeNull();
    }
    expect(calls).toEqual([]);
  });

  it("never emits CORS headers, on success or on rejection", async () => {
    const { app } = probeApp();
    const responses = [
      await app.request("/api/ping", { headers: headers({ origin: ORIGIN }) }),
      await app.request("/api/ping", { headers: headers({ origin: "https://evil.example" }) }),
      await app.request("/api/ping", { headers: { host: HOST } }),
    ];
    expect(responses.map((response) => response.status)).toEqual([200, 403, 401]);
    for (const response of responses) {
      const cors = [...response.headers.keys()].filter((name) => name.startsWith("access-control-"));
      expect(cors).toEqual([]);
    }
  });
});

describe("security middleware: body limits", () => {
  it("rejects a JSON body over 2 MB before the handler runs and accepts one at the limit", async () => {
    const { app, calls } = probeApp();
    const over = await app.request("/api/echo", { method: "POST", headers: writeHeaders(), body: new Uint8Array(2 * MB + 1) });
    expect(over.status).toBe(413);
    expect(calls).toEqual([]);

    const atLimit = await app.request("/api/echo", { method: "POST", headers: writeHeaders(), body: new Uint8Array(2 * MB) });
    expect(await atLimit.json()).toEqual({ bytes: 2 * MB });
  });

  it("allows uploads up to 20 MB and rejects larger ones", async () => {
    const { app, calls } = probeApp();
    const headersOctet = writeHeaders({ "content-type": "application/octet-stream" });
    const big = await app.request(UPLOAD_PATH, { method: "POST", headers: headersOctet, body: new Uint8Array(3 * MB) });
    expect(await big.json()).toEqual({ bytes: 3 * MB });

    const over = await app.request(UPLOAD_PATH, { method: "POST", headers: headersOctet, body: new Uint8Array(20 * MB + 1) });
    expect(over.status).toBe(413);
    expect(calls).toEqual([`POST ${UPLOAD_PATH}`]);
  });

  it("enforces the limit on a streamed body that declares no length", async () => {
    const { app } = probeApp();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let i = 0; i < 3; i += 1) controller.enqueue(new Uint8Array(MB));
        controller.close();
      },
    });
    const response = await app.request("/api/echo", { method: "POST", headers: writeHeaders(), body: stream, duplex: "half" } as RequestInit);
    expect(response.status).toBe(413);
  });
});

describe("security middleware: response headers", () => {
  it("adds the content security policy, nosniff and no-referrer to static and API responses", async () => {
    const { app } = probeApp();
    for (const path of ["/index.html", "/api/ping"]) {
      const response = await app.request(path, { headers: headers() });
      expect(response.status).toBe(200);
      expect(response.headers.get("x-content-type-options")).toBe("nosniff");
      expect(response.headers.get("referrer-policy")).toBe("no-referrer");
      expect(response.headers.get("content-security-policy")).toBe(
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
      );
    }
  });

  it("never allows inline or remote scripts", async () => {
    const { app } = probeApp();
    const csp = (await app.request("/index.html", { headers: headers() })).headers.get("content-security-policy") ?? "";
    const script = csp.split(";").map((part) => part.trim()).find((part) => part.startsWith("script-src"));
    expect(script).toBe("script-src 'self'");
  });

  it("also protects the rejection responses", async () => {
    const { app } = probeApp();
    const response = await app.request("/api/ping", { headers: { host: HOST } });
    expect(response.status).toBe(401);
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  });
});
