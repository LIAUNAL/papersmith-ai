import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "./client.ts";

interface Recorded {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** A fetch that records each request and answers with the queued responses. */
function fakeFetch(...responses: Response[]) {
  const requests: Recorded[] = [];
  const queue = [...responses];
  const fetchFn = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
      body: init?.body,
    });
    const next = queue.shift();
    if (next === undefined) throw new Error("unexpected request");
    return next;
  };
  return { fetchFn, requests };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const TOKEN = "launch-token-0123456789";

describe("api client", () => {
  it("sends the token on a read and no content type", async () => {
    const { fetchFn, requests } = fakeFetch(json({ entries: [{ path: "main.tex", kind: "file", size: 3 }] }));
    const entries = await createApiClient({ token: TOKEN, fetch: fetchFn }).listFiles();

    expect(entries).toEqual([{ path: "main.tex", kind: "file", size: 3 }]);
    expect(requests).toEqual([{ url: "/api/files", method: "GET", headers: { "x-caztor-token": TOKEN }, body: undefined }]);
  });

  it("sends JSON content type and the token on a state-changing request", async () => {
    const { fetchFn, requests } = fakeFetch(json({ path: "a.tex", kind: "file" }, 201));
    await createApiClient({ token: TOKEN, fetch: fetchFn }).createEntry("a.tex", "file");

    expect(requests).toEqual([
      {
        url: "/api/files",
        method: "POST",
        headers: { "x-caztor-token": TOKEN, "content-type": "application/json" },
        body: JSON.stringify({ path: "a.tex", kind: "file" }),
      },
    ]);
  });

  it("sends the JSON content type on DELETE even though it has no body, and encodes the path", async () => {
    const { fetchFn, requests } = fakeFetch(json({ path: "my dir/a&b.tex" }), json({ path: "x" }));
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    await client.deleteEntry("my dir/a&b.tex", { recursive: false });
    await client.deleteEntry("x", { recursive: true });

    expect(requests.map((request) => [request.method, request.url, request.headers["content-type"]])).toEqual([
      ["DELETE", "/api/files?path=my%20dir%2Fa%26b.tex", "application/json"],
      ["DELETE", "/api/files?path=x&recursive=true", "application/json"],
    ]);
  });

  it("uploads raw bytes with the octet-stream content type", async () => {
    const { fetchFn, requests } = fakeFetch(json({ path: "fig/a.png", hash: "sha256:x" }, 201));
    const bytes = new Uint8Array([1, 2, 3]);
    await createApiClient({ token: TOKEN, fetch: fetchFn }).uploadFile("fig/a.png", bytes);

    expect(requests[0]).toMatchObject({
      url: "/api/files/upload?path=fig%2Fa.png",
      method: "POST",
      headers: { "x-caztor-token": TOKEN, "content-type": "application/octet-stream" },
      body: bytes,
    });
  });

  it("renames, patches settings and reads a file with the documented routes", async () => {
    const { fetchFn, requests } = fakeFetch(
      json({ from: "a.tex", to: "b.tex" }),
      json({ settings: { disclosureAcknowledged: true } }),
      json({ path: "b.tex", content: "hello", hash: "sha256:aa" }),
    );
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    await client.renameEntry("a.tex", "b.tex");
    await client.patchSettings({ disclosureAcknowledged: true });
    const file = await client.readFile("b.tex");

    expect(file).toEqual({ path: "b.tex", content: "hello", hash: "sha256:aa" });
    expect(requests.map((request) => [request.method, request.url, request.body])).toEqual([
      ["POST", "/api/files/rename", JSON.stringify({ from: "a.tex", to: "b.tex" })],
      ["PATCH", "/api/settings", JSON.stringify({ disclosureAcknowledged: true })],
      ["GET", "/api/files/content?path=b.tex", undefined],
    ]);
  });

  it("turns an API error body into a typed error with the readable message", async () => {
    const { fetchFn } = fakeFetch(json({ error: "exists", message: '"a.tex" already exists. Choose another name.', path: "a.tex" }, 409));
    const failure = await createApiClient({ token: TOKEN, fetch: fetchFn }).createEntry("a.tex", "file").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 409, code: "exists", message: '"a.tex" already exists. Choose another name.', path: "a.tex" });
  });

  it("falls back to a generic message when the error body is not the API shape or the network fails", async () => {
    const { fetchFn } = fakeFetch(new Response("<html>bad gateway</html>", { status: 502 }));
    const bad = await createApiClient({ token: TOKEN, fetch: fetchFn }).listFiles().catch((error: unknown) => error);
    expect(bad).toMatchObject({ status: 502, code: "http_error", message: "The server answered with an unexpected error (502)." });

    const offline = async (): Promise<Response> => Promise.reject(new TypeError("Failed to fetch"));
    const down = await createApiClient({ token: TOKEN, fetch: offline }).listFiles().catch((error: unknown) => error);
    expect(down).toMatchObject({ status: 0, code: "network", message: "Cannot reach the Caztor server. Check that it is still running." });
  });

  it("reads the session", async () => {
    const session = {
      project: { name: "thesis" },
      engine: { available: false },
      sandbox: { available: false },
      settings: { stopOnFirstError: false, autoCompile: true, sandboxedCompile: false, mainFile: null, disclosureAcknowledged: false },
    };
    const { fetchFn, requests } = fakeFetch(json(session));
    expect(await createApiClient({ token: TOKEN, fetch: fetchFn }).getSession()).toEqual(session);
    expect(requests[0]?.url).toBe("/api/session");
  });

  it("saves text with the hash it was based on and returns the new hash", async () => {
    const { fetchFn, requests } = fakeFetch(json({ path: "my dir/a.tex", hash: "sha256:bb" }), json({ path: "n.tex", hash: "sha256:cc" }));
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    expect(await client.writeFile("my dir/a.tex", "text", "sha256:aa")).toEqual({ hash: "sha256:bb" });
    expect(await client.writeFile("n.tex", "", null)).toEqual({ hash: "sha256:cc" });

    expect(requests.map((request) => [request.method, request.url, request.headers["content-type"], request.body])).toEqual([
      ["PUT", "/api/files/content?path=my%20dir%2Fa.tex", "application/json", JSON.stringify({ content: "text", baseHash: "sha256:aa" })],
      ["PUT", "/api/files/content?path=n.tex", "application/json", JSON.stringify({ content: "", baseHash: null })],
    ]);
  });

  it("reports a save conflict with the hash now on disk", async () => {
    const { fetchFn } = fakeFetch(json({ error: "conflict", message: '"a.tex" changed on disk.', path: "a.tex", currentHash: "sha256:new" }, 409));
    const failure = await createApiClient({ token: TOKEN, fetch: fetchFn }).writeFile("a.tex", "x", "sha256:old").catch((error: unknown) => error);
    expect(failure).toMatchObject({ status: 409, code: "conflict", currentHash: "sha256:new" });
  });

  it("starts a compile with an empty JSON body and returns the id and whether it was queued", async () => {
    const { fetchFn, requests } = fakeFetch(json({ compileId: "c1", queued: false }, 202), json({ compileId: "c2", queued: true }, 202));
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    expect(await client.startCompile()).toEqual({ compileId: "c1", queued: false });
    expect(await client.startCompile()).toEqual({ compileId: "c2", queued: true });
    expect(requests[0]).toEqual({ url: "/api/compile", method: "POST", headers: { "x-caztor-token": TOKEN, "content-type": "application/json" }, body: undefined });
  });

  it("names the file to compile when one is given", async () => {
    const { fetchFn, requests } = fakeFetch(json({ compileId: "c1", queued: false }, 202));
    await createApiClient({ token: TOKEN, fetch: fetchFn }).startCompile("chapters/one.tex");
    expect(requests[0]).toMatchObject({ url: "/api/compile", method: "POST", body: JSON.stringify({ main: "chapters/one.tex" }) });
  });

  it("surfaces the readable message when the engine is missing", async () => {
    const { fetchFn } = fakeFetch(json({ error: "engine_unavailable", message: "The LaTeX engine (Tectonic) was not found." }, 503));
    await expect(createApiClient({ token: TOKEN, fetch: fetchFn }).startCompile()).rejects.toMatchObject({
      status: 503,
      code: "engine_unavailable",
      message: "The LaTeX engine (Tectonic) was not found.",
    });
  });

  it("cancels a compile and reads the status", async () => {
    const status = { running: null, queued: null, last: null, pdfAvailable: true };
    const { fetchFn, requests } = fakeFetch(json({ cancelled: true }), json(status));
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    expect(await client.cancelCompile()).toEqual({ cancelled: true });
    expect(await client.getCompileStatus()).toEqual(status);
    expect(requests.map((request) => `${request.method} ${request.url}`)).toEqual(["POST /api/compile/cancel", "GET /api/compile/status"]);
  });

  it("reads the preview PDF as bytes with the token header, and the log as text", async () => {
    const pdf = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]);
    const { fetchFn, requests } = fakeFetch(
      new Response(pdf, { status: 200, headers: { "content-type": "application/pdf" } }),
      new Response("This is XeTeX\nline", { status: 200, headers: { "content-type": "text/plain" } }),
    );
    const client = createApiClient({ token: TOKEN, fetch: fetchFn });
    expect([...(await client.readPdf("7"))]).toEqual([...pdf]);
    expect(await client.readLog()).toBe("This is XeTeX\nline");
    expect(requests.map((request) => `${request.url} ${request.headers["x-caztor-token"]}`)).toEqual([
      `/api/compile/pdf?rev=7 ${TOKEN}`,
      `/api/compile/log ${TOKEN}`,
    ]);
  });

  it("reports a missing PDF with the server's message", async () => {
    const { fetchFn } = fakeFetch(json({ error: "no_pdf", message: "No PDF has been produced yet. Compile the project first." }, 404));
    await expect(createApiClient({ token: TOKEN, fetch: fetchFn }).readPdf("1")).rejects.toMatchObject({ code: "no_pdf", status: 404 });
  });
});

describe("a launch token the server no longer accepts", () => {
  it("is reported once per refused request, for ordinary requests and for a turn's stream", async () => {
    const { fetchFn } = fakeFetch(json({ error: "token_required" }, 401), json({ error: "token_required" }, 401), json({ ok: true }));
    const rejected: number[] = [];
    const client = createApiClient({ token: TOKEN, fetch: fetchFn, onTokenRejected: () => rejected.push(1) });
    await expect(client.listProviders()).rejects.toMatchObject({ status: 401 });
    await expect(client.streamTurn({ kind: "start", provider: "claude", prompt: "hi" }, () => {}, new AbortController().signal)).rejects.toMatchObject({ status: 401 });
    expect(rejected).toHaveLength(2);
  });

  it("is not reported for other errors", async () => {
    const { fetchFn } = fakeFetch(json({ error: "busy", message: "Busy." }, 409));
    const rejected: number[] = [];
    const client = createApiClient({ token: TOKEN, fetch: fetchFn, onTokenRejected: () => rejected.push(1) });
    await expect(client.listProviders()).rejects.toMatchObject({ status: 409 });
    expect(rejected).toEqual([]);
  });
});
