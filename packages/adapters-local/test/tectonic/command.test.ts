import { parseRelPath, type RelPath } from "@caztor/core";
import { describe, expect, it } from "vitest";
import { buildCompileArgs, buildCompileEnv, COMPILE_ENV_ALLOWLIST, OUT_DIR } from "../../src/tectonic/command.ts";

function rel(path: string): RelPath {
  const parsed = parseRelPath(path);
  if (!parsed.ok) throw new Error(`bad test path ${path}`);
  return parsed.value;
}

describe("buildCompileArgs", () => {
  it("continues past errors by default: -Z continue-on-errors, no halting", () => {
    expect(buildCompileArgs({ main: rel("main.tex"), stopOnFirstError: false })).toEqual([
      "-X",
      "compile",
      "./main.tex",
      "--outdir",
      ".caztor/build/out",
      "--keep-logs",
      "--untrusted",
      "-Z",
      "continue-on-errors",
    ]);
  });

  it("halts at the first error when stop-on-first-error is on: no -Z flag at all", () => {
    expect(buildCompileArgs({ main: rel("paper/main.tex"), stopOnFirstError: true })).toEqual([
      "-X",
      "compile",
      "./paper/main.tex",
      "--outdir",
      OUT_DIR,
      "--keep-logs",
      "--untrusted",
    ]);
  });

  it("never passes --synctex or shell escape, in either mode", () => {
    for (const stopOnFirstError of [true, false]) {
      const args = buildCompileArgs({ main: rel("main.tex"), stopOnFirstError });
      expect(args).not.toContain("--synctex");
      expect(args.join(" ")).not.toMatch(/shell-escape|-Z\s+shell/);
      expect(args).toContain("--untrusted");
    }
  });

  it("puts the main file in as ./path, so a name starting with a dash cannot become an option", () => {
    expect(buildCompileArgs({ main: rel("a -b.tex"), stopOnFirstError: true })[2]).toBe("./a -b.tex");
  });

  it("refuses a main file that parseRelPath would reject, such as '-Z shell-escape.tex'", () => {
    for (const main of ["-Z shell-escape.tex", "--outdir", "../escape.tex", "/etc/passwd", ""]) {
      expect(() => buildCompileArgs({ main: main as RelPath, stopOnFirstError: false }), main).toThrow(/main file/i);
    }
  });
});

describe("buildCompileEnv", () => {
  it("keeps only the allowlisted variables and marks the run untrusted", () => {
    const env = buildCompileEnv({
      PATH: "/bin",
      HOME: "/home/u",
      XDG_CACHE_HOME: "/cache",
      TECTONIC_CACHE_DIR: "/tectonic",
      TMPDIR: "/tmp",
      HTTPS_PROXY: "http://proxy:3128",
      https_proxy: "http://proxy:3128",
      NO_PROXY: "localhost",
    });
    expect(env).toEqual({
      PATH: "/bin",
      HOME: "/home/u",
      XDG_CACHE_HOME: "/cache",
      TECTONIC_CACHE_DIR: "/tectonic",
      TMPDIR: "/tmp",
      HTTPS_PROXY: "http://proxy:3128",
      https_proxy: "http://proxy:3128",
      NO_PROXY: "localhost",
      TECTONIC_UNTRUSTED_MODE: "1",
    });
  });

  it("drops every variable that is not on the list, for example a secret set in the parent", () => {
    const env = buildCompileEnv({
      PATH: "/bin",
      ANTHROPIC_API_KEY: "sk-secret",
      AWS_SECRET_ACCESS_KEY: "hunter2",
      CAZTOR_TOKEN: "launch-token",
      OPENAI_API_KEY: "sk-other",
      LD_PRELOAD: "/evil.so",
      TEXINPUTS: "/etc:",
    });
    expect(Object.keys(env).sort()).toEqual(["PATH", "TECTONIC_UNTRUSTED_MODE"]);
  });

  it("forces untrusted mode on even when the parent turns it off", () => {
    expect(buildCompileEnv({ TECTONIC_UNTRUSTED_MODE: "0" })["TECTONIC_UNTRUSTED_MODE"]).toBe("1");
  });

  it("skips variables that are not set", () => {
    const env = buildCompileEnv({ PATH: undefined, HOME: "/h" });
    expect(env).toEqual({ HOME: "/h", TECTONIC_UNTRUSTED_MODE: "1" });
  });

  it("lists the allowlist without LANG or LC_ALL, which tectonic does not need", () => {
    expect(COMPILE_ENV_ALLOWLIST).not.toContain("LANG");
    expect(COMPILE_ENV_ALLOWLIST).toEqual(expect.arrayContaining(["PATH", "HOME", "XDG_CACHE_HOME", "TECTONIC_CACHE_DIR"]));
  });
});
