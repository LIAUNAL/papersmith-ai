import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { nodeFileSystem } from "@caztor/adapters-local";
import { afterEach, describe, expect, it } from "vitest";
import { runUserCommand } from "../src/user-commands.ts";

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("trust-build", () => {
  it("confirms the project's recipe with the key in the configuration folder and says what will run", async () => {
    const home = realpathSync(mkdtempSync(join(tmpdir(), "caztor-trust-build-")));
    dirs.push(home);
    const root = join(home, "paper-project");
    mkdirSync(join(root, ".caztor"), { recursive: true });
    writeFileSync(join(root, ".caztor", "build.json"), JSON.stringify({ when: ["paper/main.tex"], before: ["python3", "paper/build_preview.py"], root: "paper/preview.tex" }));
    const result = await runUserCommand({ ok: true, command: "trust-build", projectDir: root }, { fs: nodeFileSystem, env: { HOME: home } });
    expect(result.code).toBe(0);
    expect(result.lines.join("\n")).toContain("`python3 paper/build_preview.py`");
    expect(readFileSync(join(root, ".caztor", "build.seal"), "utf8")).toMatch(/^hmac1:/);
  });

  it("refuses a folder without a valid recipe", async () => {
    const home = realpathSync(mkdtempSync(join(tmpdir(), "caztor-trust-build-")));
    dirs.push(home);
    const result = await runUserCommand({ ok: true, command: "trust-build", projectDir: home }, { fs: nodeFileSystem, env: { HOME: home } });
    expect(result.code).toBe(1);
    expect(result.lines[0]).toContain(".caztor/build.json");
  });
});
