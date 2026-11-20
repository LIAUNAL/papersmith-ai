import { describe, expect, it } from "vitest";
import { hashBytes } from "../src/hash.ts";

const encode = (text: string) => new TextEncoder().encode(text);

describe("hashBytes", () => {
  it("matches the SHA-256 vector for the empty input", async () => {
    expect(await hashBytes(new Uint8Array())).toBe(
      "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("matches the SHA-256 vector for abc", async () => {
    expect(await hashBytes(encode("abc"))).toBe(
      "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("hashes raw bytes, not decoded text", async () => {
    const binary = new Uint8Array([0x00, 0xff, 0x80, 0x0a]);
    expect(await hashBytes(binary)).toBe(
      "sha256:6d6f7836f1e146dc0204afb5133dae52fdc05603d8ac2dc793b481b0e0829fd1",
    );
  });

  it("returns different hashes for different content", async () => {
    expect(await hashBytes(encode("a"))).not.toBe(await hashBytes(encode("b")));
  });
});
