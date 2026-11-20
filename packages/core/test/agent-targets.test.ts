import { describe, expect, it } from "vitest";
import { AGENT_TARGETS, isAgentTarget, PROVIDER_IDS } from "../src/index.ts";

describe("agent targets", () => {
  it("lists five providers, pi last", () => {
    expect([...PROVIDER_IDS]).toEqual(["claude", "opencode", "codex", "antigravity", "pi"]);
  });

  it("puts the Antigravity definition at .agents/agents/caztor.md and recognises it as a target", () => {
    expect(AGENT_TARGETS.antigravity).toBe(".agents/agents/caztor.md");
    expect(isAgentTarget(".agents/agents/caztor.md")).toBe(true);
    expect(isAgentTarget(".agents/hooks.json")).toBe(false);
  });

  it("puts the Pi system prompt inside the internal state folder, never in the project's .pi/", () => {
    expect(AGENT_TARGETS.pi).toBe(".caztor/agents/pi.md");
    expect(isAgentTarget(".caztor/agents/pi.md")).toBe(true);
    expect(Object.values(AGENT_TARGETS).some((target) => target.startsWith(".pi/"))).toBe(false);
  });
});
