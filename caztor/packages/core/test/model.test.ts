import { describe, expect, it } from "vitest";
import { MAX_MODEL_LENGTH, parseModel } from "../src/index.ts";

describe("parseModel", () => {
  it.each(["sonnet", "claude-sonnet-4-5", "anthropic/claude-sonnet-4.5", "gpt-5:high", "openrouter/meta-llama/llama-3.1_70b"])("accepts %s", (model) => {
    expect(parseModel(model)).toEqual({ ok: true, value: model });
  });

  it.each(["--dangerous", "-m", "--model=x", "-"])("rejects %s, which a command line could read as an option", (model) => {
    const parsed = parseModel(model);
    expect(parsed).toEqual({ ok: false, message: expect.stringContaining("cannot start with a dash") });
  });

  it.each(["has space", "semi;colon", "new\nline", "quote\"", "back`tick", "$(x)", "tab\tchar", "ünïcode"])("rejects %j for characters a model name does not use", (model) => {
    expect(parseModel(model)).toEqual({ ok: false, message: expect.stringContaining("letters, digits") });
  });

  it("trims surrounding spaces, and treats an empty value as clearing the setting", () => {
    expect(parseModel("  sonnet \n")).toEqual({ ok: true, value: "sonnet" });
    expect(parseModel("   ")).toEqual({ ok: true, value: null });
    expect(parseModel(null)).toEqual({ ok: true, value: null });
  });

  it("rejects a value that is not text and one that is too long", () => {
    expect(parseModel(42)).toEqual({ ok: false, message: expect.stringContaining("text") });
    expect(parseModel("a".repeat(MAX_MODEL_LENGTH + 1))).toEqual({ ok: false, message: expect.stringContaining("too long") });
    expect(parseModel("a".repeat(MAX_MODEL_LENGTH))).toEqual({ ok: true, value: "a".repeat(MAX_MODEL_LENGTH) });
  });
});
