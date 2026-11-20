import type { ContentHash, RelPath, StoreError } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { describeStoreError } from "../src/store-errors.ts";

const hash = `sha256:${"a".repeat(64)}` as ContentHash;

describe("describeStoreError", () => {
  it.each<[StoreError, number, string]>([
    [{ code: "not_found", path: "a.tex" }, 404, "not_found"],
    [{ code: "invalid_path", path: "a\u0000b" }, 400, "invalid_path"],
    [{ code: "outside_root", path: "../x" }, 403, "outside_root"],
    [{ code: "hidden", path: ".git/config" }, 403, "hidden"],
    [{ code: "exists", path: "a.tex" }, 409, "exists"],
    [{ code: "too_large", path: "big.tex" }, 413, "too_large"],
    [{ code: "not_text", path: "logo.png" }, 415, "not_text"],
    [{ code: "io", path: "a.tex" }, 500, "io"],
  ])("maps %j to %i %s with a readable message naming the path", (error, status, code) => {
    const described = describeStoreError(error);
    expect(described.status).toBe(status);
    expect(described.body.error).toBe(code);
    expect(described.body.path).toBe(error.path);
    expect(described.body.message).toContain(`"${error.path}"`);
    expect(described.body.message).toMatch(/\.$/);
  });

  it("returns the current hash on a conflict so the client can offer to reload", () => {
    const described = describeStoreError({ code: "conflict", path: "a.tex" as RelPath, currentHash: hash });
    expect(described).toMatchObject({ status: 409, body: { error: "conflict", path: "a.tex", currentHash: hash } });
  });

  it("returns a null current hash when the file no longer exists", () => {
    const described = describeStoreError({ code: "conflict", path: "a.tex" as RelPath, currentHash: null });
    expect(described.body).toMatchObject({ error: "conflict", currentHash: null });
  });

  it("explains a name collision in plain words", () => {
    const { body } = describeStoreError({ code: "exists", path: "a.tex" });
    expect(body.message).toBe('"a.tex" already exists. Choose another name.');
  });
});
