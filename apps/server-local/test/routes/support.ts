import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { createProjectStore, createStateStore, nodeFileSystem, systemClock } from "@caztor/adapters-local";
import { createApp, createEventHub, type ApiDeps } from "@caztor/api";
import { afterEach } from "vitest";

export const TOKEN = "launch-token-0123456789abcdef";
export const HOST = "127.0.0.1:4317";
export const ORIGIN = `http://${HOST}`;

const dirs: string[] = [];

/** Call once at the top of a route test file. */
export function cleanupProjects(): void {
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });
}

export interface Harness {
  root: string;
  deps: ApiDeps;
  /** Sends a request with the host, origin, token and (for writes) JSON content type already set. */
  call(method: string, path: string, init?: { body?: unknown; headers?: Record<string, string> }): Promise<Response>;
  /** Sends a raw binary body to an upload-style route. */
  upload(path: string, body: Uint8Array): Promise<Response>;
}

/** The real app over a real temporary project folder: real project store, real state store. */
export function harness(overrides: Partial<ApiDeps> = {}): Harness {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "caztor-routes-")));
  dirs.push(root);
  const deps: ApiDeps = {
    projectName: basename(root),
    store: createProjectStore({ fs: nodeFileSystem, root }),
    state: createStateStore({ fs: nodeFileSystem, root }),
    events: createEventHub(),
    clock: systemClock,
    ...overrides,
  };
  const app = createApp(deps, { token: TOKEN, allowedHosts: [HOST], allowedOrigins: [ORIGIN] });
  const base: Record<string, string> = { host: HOST, "x-caztor-token": TOKEN };
  return {
    root,
    deps,
    call(method, path, init = {}) {
      const headers: Record<string, string> = { ...base, ...init.headers };
      if (method !== "GET") Object.assign(headers, { origin: ORIGIN, "content-type": "application/json" }, init.headers);
      const body = init.body === undefined ? undefined : typeof init.body === "string" ? init.body : JSON.stringify(init.body);
      return Promise.resolve(app.request(path, { method, headers, ...(body === undefined ? {} : { body }) }));
    },
    upload(path, body) {
      const headers = { ...base, origin: ORIGIN, "content-type": "application/octet-stream" };
      return Promise.resolve(app.request(path, { method: "POST", headers, body: body as Uint8Array<ArrayBuffer> }));
    },
  };
}
