import { describe, expect, it } from "vitest";
import { readLaunchToken } from "./token.ts";

function page(head: string): Document {
  return new DOMParser().parseFromString(`<!doctype html><html><head>${head}</head><body></body></html>`, "text/html");
}

describe("readLaunchToken", () => {
  it("reads the token from the caztor-token meta tag", () => {
    expect(readLaunchToken(page('<meta name="caztor-token" content="abc123def456ghi789">'))).toBe("abc123def456ghi789");
  });

  it("ignores other meta tags", () => {
    expect(readLaunchToken(page('<meta name="viewport" content="width=device-width"><meta name="caztor-token" content="secret-value-0123456789">'))).toBe(
      "secret-value-0123456789",
    );
  });

  it.each([
    ["no meta tag", ""],
    ["an empty value", '<meta name="caztor-token" content="">'],
    ["a blank value", '<meta name="caztor-token" content="   ">'],
    ["the unreplaced placeholder", '<meta name="caztor-token" content="__CAZTOR_TOKEN__">'],
    ["a meta tag without content", '<meta name="caztor-token">'],
  ])("returns null for %s", (_label, head) => {
    expect(readLaunchToken(page(head))).toBeNull();
  });
});
