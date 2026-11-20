import type { ContentHash, RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { createUserWriteLog } from "../src/user-writes.ts";

const hash = (digit: string) => `sha256:${digit.repeat(64)}` as ContentHash;
const rel = (path: string) => path as RelPath;

describe("user write log", () => {
  it("records nothing until a turn begins", async () => {
    const log = createUserWriteLog();
    expect(log.recording()).toBe(false);
    log.record(rel("a.tex"), hash("1"), hash("2"));
    log.begin();
    expect(log.recording()).toBe(true);
    expect((await log.end()).size).toBe(0);
    expect(log.recording()).toBe(false);
  });

  it("keeps the hash before the first change and the hash after the last one", async () => {
    const log = createUserWriteLog();
    log.begin();
    log.record(rel("a.tex"), hash("1"), hash("2"));
    log.record(rel("a.tex"), hash("2"), hash("3"));
    log.record(rel("b.tex"), null, hash("4"));
    log.record(rel("c.tex"), hash("5"), null);

    const writes = await log.end();
    expect(writes.get(rel("a.tex"))).toEqual({ first: hash("1"), last: hash("3") });
    expect(writes.get(rel("b.tex"))).toEqual({ first: null, last: hash("4") });
    expect(writes.get(rel("c.tex"))).toEqual({ first: hash("5"), last: null });
    expect([...writes.keys()].sort()).toEqual(["a.tex", "b.tex", "c.tex"]);
  });

  it("starts every turn with an empty record", async () => {
    const log = createUserWriteLog();
    log.begin();
    log.record(rel("a.tex"), hash("1"), hash("2"));
    await log.end();
    log.begin();
    log.record(rel("b.tex"), hash("3"), hash("4"));
    expect([...(await log.end()).keys()]).toEqual(["b.tex"]);
  });
});
