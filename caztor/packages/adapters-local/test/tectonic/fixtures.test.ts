import { homedir, tmpdir, userInfo } from "node:os";
import { describe, expect, it } from "vitest";
import { fixture, fixtureNames } from "../support/fixtures.ts";

describe("tectonic fixtures", () => {
  it("ships the recorded outputs the parsers are tested against", () => {
    expect(fixtureNames()).toEqual(
      expect.arrayContaining([
        "halt-undefined.stderr",
        "continue-undefined.stderr",
        "offline-first-run.stderr",
        "first-run-download.stderr",
        "undefined-reference.log",
        "package-warnings.log",
      ]),
    );
  });

  it("holds no user-specific path, user name or temporary directory", () => {
    const forbidden = [homedir(), tmpdir(), userInfo().username, "/home/", "/Users/", "/tmp/", "claude-"];
    for (const name of fixtureNames()) {
      const text = fixture(name);
      for (const needle of forbidden) {
        expect(text.includes(needle), `${name} contains ${needle}`).toBe(false);
      }
    }
  });

  it("keeps each fixture non-empty so an empty file cannot pass the scan", () => {
    for (const name of fixtureNames()) expect(fixture(name).length, name).toBeGreaterThan(50);
  });
});
