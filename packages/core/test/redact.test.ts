import { describe, expect, it } from "vitest";
import { MIN_SECRET_LENGTH, REDACTION_MASK, redactSecrets, redactValue } from "../src/index.ts";

const KEY = "sk-test-abcdef123456";

describe("redactSecrets", () => {
  it("replaces every occurrence of a secret with the mask", () => {
    expect(REDACTION_MASK).toBe("[redacted]");
    expect(redactSecrets(`bad key ${KEY} and again ${KEY}.`, [KEY])).toBe("bad key [redacted] and again [redacted].");
  });

  it("leaves a text without the secret untouched", () => {
    expect(redactSecrets("nothing to hide here", [KEY])).toBe("nothing to hide here");
  });

  it("skips secrets shorter than eight characters, so ordinary words are not masked", () => {
    expect(MIN_SECRET_LENGTH).toBe(8);
    expect(redactSecrets("the word secret appears", ["secret"])).toBe("the word secret appears");
    expect(redactSecrets("the word secrets appears", ["secrets!!"])).toBe("the word secrets appears");
    expect(redactSecrets("a 12345678 b", ["12345678"])).toBe("a [redacted] b");
  });

  it("ignores empty secrets and an empty list", () => {
    expect(redactSecrets("text", [""])).toBe("text");
    expect(redactSecrets("text", [])).toBe("text");
  });

  it("masks several secrets, longest first, so one inside another leaves no tail", () => {
    const short = "abcdefgh";
    const long = "abcdefgh-ijklmnop";
    expect(redactSecrets(`x ${long} y ${short}`, [short, long])).toBe("x [redacted] y [redacted]");
  });

  it("treats the secret as plain text, not as a pattern", () => {
    const odd = "a.b*c+d?e(f)[g]";
    expect(redactSecrets(`see ${odd} and axbbbcde`, [odd])).toBe("see [redacted] and axbbbcde");
  });
});

describe("redactValue", () => {
  it("scrubs every string of nested objects and arrays and keeps the shape", () => {
    const event = {
      type: "error",
      code: "provider_error",
      message: `rejected ${KEY}`,
      detail: { lines: [`header ${KEY}`, "clean"], count: 3, ok: true, none: null },
    };
    expect(redactValue(event, [KEY])).toEqual({
      type: "error",
      code: "provider_error",
      message: "rejected [redacted]",
      detail: { lines: ["header [redacted]", "clean"], count: 3, ok: true, none: null },
    });
  });

  it("does not change the value it was given", () => {
    const event = { message: KEY };
    redactValue(event, [KEY]);
    expect(event.message).toBe(KEY);
  });

  it("returns primitives without secrets as they are", () => {
    expect(redactValue(42, [KEY])).toBe(42);
    expect(redactValue(`x${KEY}`, [KEY])).toBe("x[redacted]");
  });
});
