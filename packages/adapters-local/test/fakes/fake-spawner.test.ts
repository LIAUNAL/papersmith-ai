import { describe, expect, it } from "vitest";
import type { SpawnSpec } from "../../src/infra.ts";
import { FakeSpawner, splitBytes } from "./fake-spawner.ts";

const spec: SpawnSpec = { file: "tool", args: ["--flag"], cwd: "/project", env: { PATH: "/bin" }, stdin: "prompt" };

async function collect(stream: AsyncIterable<Uint8Array>): Promise<Uint8Array[]> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) chunks.push(chunk);
  return chunks;
}

describe("splitBytes", () => {
  it("cuts text into byte chunks at the given offsets", () => {
    const parts = splitBytes("abcdef", [2, 4]);
    expect(parts.map((part) => new TextDecoder().decode(part))).toEqual(["ab", "cd", "ef"]);
  });
});

describe("FakeSpawner", () => {
  it("records the spawn spec and replays scripted chunks verbatim, then exits", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ stdout: ["one\n", "two\n"], stderr: ["warn\n"], exit: { code: 0, signal: null } });

    const child = spawner.spawn(spec);
    const [out, err, exit] = await Promise.all([collect(child.stdout), collect(child.stderr), child.exit]);

    expect(spawner.calls).toEqual([spec]);
    expect(out.map((chunk) => new TextDecoder().decode(chunk))).toEqual(["one\n", "two\n"]);
    expect(err.map((chunk) => new TextDecoder().decode(chunk))).toEqual(["warn\n"]);
    expect(exit).toEqual({ code: 0, signal: null });
  });

  it("keeps a multi-byte character split across chunks so consumers must decode in streaming mode", async () => {
    const spawner = new FakeSpawner();
    const chunks = splitBytes("price €5", [8]); // cut inside the 3-byte euro sign
    spawner.enqueue({ stdout: chunks, exit: { code: 0, signal: null } });

    const child = spawner.spawn(spec);
    const received = await collect(child.stdout);

    expect(received).toHaveLength(2);
    expect(new TextDecoder().decode(received[0])).toContain("�");
    const decoder = new TextDecoder();
    const text = received.map((chunk) => decoder.decode(chunk, { stream: true })).join("") + decoder.decode();
    expect(text).toBe("price €5");
  });

  it("hands out scripts in spawn order", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ exit: { code: 1, signal: null } });
    spawner.enqueue({ exit: { code: 2, signal: null } });

    expect(await spawner.spawn(spec).exit).toEqual({ code: 1, signal: null });
    expect(await spawner.spawn(spec).exit).toEqual({ code: 2, signal: null });
  });

  it("keeps a child without an exit script alive until a signal ends it, and records every signal", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ stdout: ["partial"] });
    const child = spawner.spawn(spec);

    let settled = false;
    void child.exit.then(() => (settled = true));
    await Promise.resolve();
    expect(settled).toBe(false);

    child.killGroup("SIGTERM");
    expect(await child.exit).toEqual({ code: null, signal: "SIGTERM" });
    expect(await collect(child.stdout)).toHaveLength(1);
    expect(spawner.signals).toEqual(["SIGTERM"]);
  });

  it("lets a script ignore a signal so escalation can be tested", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ ignores: ["SIGINT", "SIGTERM"] });
    const child = spawner.spawn(spec);

    child.killGroup("SIGINT");
    child.killGroup("SIGTERM");
    let settled = false;
    void child.exit.then(() => (settled = true));
    await Promise.resolve();
    expect(settled).toBe(false);

    child.killGroup("SIGKILL");
    expect(await child.exit).toEqual({ code: null, signal: "SIGKILL" });
    expect(spawner.signals).toEqual(["SIGINT", "SIGTERM", "SIGKILL"]);
  });

  it("rejects exit when the script says the binary cannot start", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ spawnError: "ENOENT" });
    const child = spawner.spawn(spec);
    await expect(child.exit).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("scripts a synchronous-style spawn failure as a rejected exit with empty output and no throw", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ spawnError: "ERR_INVALID_ARG_VALUE" });
    const child = spawner.spawn(spec);

    await expect(child.exit).rejects.toMatchObject({ code: "ERR_INVALID_ARG_VALUE" });
    expect(await collect(child.stdout)).toEqual([]);
    expect(await collect(child.stderr)).toEqual([]);
    expect(spawner.calls).toEqual([spec]);
  });

  it("fails loudly when more children are spawned than scripted", () => {
    const spawner = new FakeSpawner();
    expect(() => spawner.spawn(spec)).toThrow("FakeSpawner: no script queued for spawn #1");
  });

  it("delivers output pushed later to the most recently spawned child", async () => {
    const spawner = new FakeSpawner();
    spawner.enqueue({ stderr: ["first\n"] });
    const child = spawner.spawn(spec);
    spawner.pushStderr("second\n");
    spawner.pushStdout("out\n");
    child.killGroup("SIGTERM");

    const decode = (chunks: Uint8Array[]) => chunks.map((chunk) => new TextDecoder().decode(chunk));
    expect(decode(await collect(child.stderr))).toEqual(["first\n", "second\n"]);
    expect(decode(await collect(child.stdout))).toEqual(["out\n"]);
  });

  it("refuses to push output before any child was spawned", () => {
    expect(() => new FakeSpawner().pushStderr("x")).toThrow("FakeSpawner: no child has been spawned");
  });
});
