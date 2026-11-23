import { describe, expect, it } from "vitest";
import { AGENT_CONTEXT_HEADER, expandAgentCommand } from "../src/prompt.ts";

const tutor = { name: "math-tutor", description: "Socratic math tutor", prompt: "Ask one question per turn.", file: ".claude/agents/math-tutor.md" };

describe("a PaperSmith agent named at the start of a message", () => {
  it("puts the agent's instructions before the user's message", () => {
    const text = expandAgentCommand("/math-tutor Why is eq. 3 exact?", [tutor]);
    expect(text).toContain('PaperSmith agent "math-tutor"');
    expect(text).toContain(".claude/agents/math-tutor.md");
    expect(text).toContain("Ask one question per turn.");
    expect(text.endsWith("Why is eq. 3 exact?")).toBe(true);
    expect(text.indexOf("Ask one question per turn.")).toBeLessThan(text.indexOf("Why is eq. 3 exact?"));
    expect(text).toContain("quote it word for word from the paper's LaTeX source in a `>` block");
  });

  it("tells the agent no dashboard panel reaches it and names the workspace files that hold the panel's view", () => {
    const sources = ["proposals/research-concept-x-r15.md", ".papersmith/model_spec.json", "paper/main.tex"];
    const text = expandAgentCommand("/math-tutor why?", [tutor], sources);
    expect(text).toContain(AGENT_CONTEXT_HEADER);
    for (const path of sources) expect(text).toContain(`\`${path}\``);
    expect(text).toContain("by these exact paths");
    expect(text.indexOf(AGENT_CONTEXT_HEADER)).toBeLessThan(text.indexOf("Ask one question per turn."));
    expect(expandAgentCommand("/math-tutor why?", [tutor])).toContain("holds none of the files a panel reads");
  });

  it("tells the agent no image is attached in the chat, so it does not look for the panel's image folder", () => {
    for (const sources of [[], ["paper/main.tex"]]) {
      const text = expandAgentCommand("/math-tutor why?", [tutor], sources);
      expect(text).toContain("No image is attached in this chat");
      expect(text).toContain("do not look for attached images or their folder");
    }
  });

  it("keeps a multi-line message whole, and says when there is none", () => {
    expect(expandAgentCommand("/math-tutor first line\nsecond line", [tutor]).endsWith("first line\nsecond line")).toBe(true);
    expect(expandAgentCommand("/math-tutor", [tutor])).toContain("Do not read files or start tutoring: reply with one short sentence saying you are ready");
  });

  it("leaves any other message unchanged, including an unknown name and a path", () => {
    for (const text of ["/unknown hello", "/paper/main.tex is broken", "math-tutor hi", " /math-tutor hi"]) expect(expandAgentCommand(text, [tutor])).toBe(text);
  });
});
