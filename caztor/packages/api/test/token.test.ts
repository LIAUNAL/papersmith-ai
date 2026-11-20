import { describe, expect, it } from "vitest";
import { generateToken, resolveLaunchToken, timingSafeEqual } from "../src/token.ts";

describe("timingSafeEqual", () => {
  it("is true only for identical strings", () => {
    expect(timingSafeEqual("abc123", "abc123")).toBe(true);
    expect(timingSafeEqual("abc123", "abc124")).toBe(false);
    expect(timingSafeEqual("abc123", "Abc123")).toBe(false);
  });

  it("is false for different lengths, including a prefix and the empty string", () => {
    expect(timingSafeEqual("abc", "abcd")).toBe(false);
    expect(timingSafeEqual("abcd", "abc")).toBe(false);
    expect(timingSafeEqual("", "abc")).toBe(false);
    expect(timingSafeEqual("", "")).toBe(true);
  });

  it("compares multi-byte characters by their bytes", () => {
    expect(timingSafeEqual("café", "café")).toBe(true);
    expect(timingSafeEqual("café", "cafe")).toBe(false);
  });
});

describe("generateToken", () => {
  it("returns 32 random bytes as 64 lowercase hex characters, different on every call", () => {
    const first = generateToken();
    const second = generateToken();
    expect(first).toMatch(/^[0-9a-f]{64}$/);
    expect(second).toMatch(/^[0-9a-f]{64}$/);
    expect(first).not.toBe(second);
  });
});

describe("resolveLaunchToken", () => {
  const generate = () => "generated-token";

  it("ignores a token supplied through the environment unless development mode is on", () => {
    expect(resolveLaunchToken({ CAZTOR_TOKEN: "from-env-0123456789abcdef" }, generate)).toBe("generated-token");
    expect(resolveLaunchToken({ CAZTOR_TOKEN: "from-env-0123456789abcdef", CAZTOR_DEV: "0" }, generate)).toBe("generated-token");
    expect(resolveLaunchToken({ CAZTOR_TOKEN: "from-env-0123456789abcdef", CAZTOR_DEV: "true" }, generate)).toBe("generated-token");
  });

  it("honors the environment token in development mode", () => {
    expect(resolveLaunchToken({ CAZTOR_DEV: "1", CAZTOR_TOKEN: "from-env-0123456789abcdef" }, generate)).toBe("from-env-0123456789abcdef");
  });

  it("generates a token in development mode when none, or a too short one, is supplied", () => {
    expect(resolveLaunchToken({ CAZTOR_DEV: "1" }, generate)).toBe("generated-token");
    expect(resolveLaunchToken({ CAZTOR_DEV: "1", CAZTOR_TOKEN: "short" }, generate)).toBe("generated-token");
  });

  it("defaults to the real generator", () => {
    expect(resolveLaunchToken({})).toMatch(/^[0-9a-f]{64}$/);
  });
});
