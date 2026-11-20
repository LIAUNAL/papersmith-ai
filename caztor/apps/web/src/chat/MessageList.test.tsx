import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { chatReducer, INITIAL_CHAT_STATE, type ChatState, type TurnEvent } from "@caztor/core";
import { MessageList } from "./MessageList.tsx";

const play = (events: TurnEvent[], prompt = "Please help"): ChatState =>
  events.reduce<ChatState>((state, event) => chatReducer(state, { type: "event", event }), chatReducer(INITIAL_CHAT_STATE, { type: "prompt_sent", prompt }));
const begin: TurnEvent = { type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: false, unprotected: [] };

describe("MessageList", () => {
  it("is a polite log region labelled for screen readers", () => {
    render(<MessageList timeline={[]} />);
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toHaveAttribute("aria-live", "polite");
  });

  it("shows the user message and the assistant message as styled blocks, with Markdown applied", () => {
    const state = play([begin, { type: "text", messageId: "m", text: "Here is **bold** and `code`." }, { type: "done", reason: "completed" }]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    expect(screen.getByText("Please help").closest(".message--user")).not.toBeNull();
    const reply = container.querySelector(".message--assistant")!;
    expect(within(reply as HTMLElement).getByText("bold").tagName).toBe("STRONG");
    expect(container.querySelector("pre.markdown__code")).toBeNull();
  });

  it("shows tool cards in the order the events came, between pieces of text", () => {
    const state = play([
      begin,
      { type: "text", messageId: "a", text: "Looking." },
      { type: "tool_start", toolId: "x", name: "Edit", kind: "edit", path: "main.tex" },
      { type: "tool_end", toolId: "x", status: "done" },
      { type: "text", messageId: "b", text: "Finished." },
    ]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    const order = [...container.querySelectorAll(".message--assistant, .tool-card")].map((node) => (node.classList.contains("tool-card") ? "tool" : node.textContent));
    expect(order).toEqual(["Looking.", "tool", "Finished."]);
  });

  it("shows the user text as plain text, never as markup", () => {
    const state = play([begin], "<b>hi</b> **not bold**");
    const { container } = render(<MessageList timeline={state.timeline} />);
    expect(container.querySelector(".message--user b, .message--user strong")).toBeNull();
    expect(screen.getByText("<b>hi</b> **not bold**")).toBeInTheDocument();
  });

  it("shows that the assistant is working while a turn runs without output, and not afterwards", () => {
    const running = play([begin]);
    const { rerender } = render(<MessageList timeline={running.timeline} />);
    expect(screen.getByText("Working")).toBeInTheDocument();
    rerender(<MessageList timeline={play([begin, { type: "done", reason: "completed" }]).timeline} />);
    expect(screen.queryByText("Working")).toBeNull();
  });

  it("says when a turn was stopped, and not when it completed", () => {
    const stopped = play([begin, { type: "text", messageId: "m", text: "Half" }, { type: "done", reason: "cancelled" }]);
    const { rerender } = render(<MessageList timeline={stopped.timeline} />);
    expect(screen.getByText("Stopped")).toBeInTheDocument();
    rerender(<MessageList timeline={play([begin, { type: "done", reason: "completed" }]).timeline} />);
    expect(screen.queryByText("Stopped")).toBeNull();
  });

  it("does not repeat a turn's text when rendered again with the same state", () => {
    const state = play([begin, { type: "text_delta", messageId: "m", text: "Hel" }, { type: "text_delta", messageId: "m", text: "lo" }]);
    const { container, rerender } = render(<MessageList timeline={state.timeline} />);
    rerender(<MessageList timeline={state.timeline} />);
    expect(container.querySelectorAll(".message--assistant")).toHaveLength(1);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("is not styled as a terminal: no monospace body, no prompt glyph", () => {
    const state = play([begin, { type: "text", messageId: "m", text: "Hello" }]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    expect(container.textContent).not.toMatch(/[$>❯]\s/);
    expect(container.querySelector(".message--assistant")?.className).not.toMatch(/mono|terminal/);
  });
});

describe("MessageList steps", () => {
  const tool = (id: string, name: string, kind: "read" | "search", path?: string): TurnEvent[] => [
    { type: "tool_start", toolId: id, name, kind, ...(path === undefined ? {} : { path }) },
    { type: "tool_end", toolId: id, status: "done" },
  ];

  it("folds a run of finished steps into one line that counts them, between the texts", () => {
    const state = play([
      begin,
      { type: "text", messageId: "a", text: "I will load the skill." },
      ...tool("1", "find", "search"),
      ...tool("2", "read", "read", "skills/math-tutor/SKILL.md"),
      ...tool("3", "find", "search"),
      { type: "text", messageId: "b", text: "Here is the answer." },
      { type: "done", reason: "completed" },
    ]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    const folds = container.querySelectorAll<HTMLDetailsElement>("details.tool-group");
    expect(folds).toHaveLength(1);
    expect(folds[0]!.open).toBe(false);
    expect(folds[0]!.querySelector("summary")?.textContent).toBe("3 steps: find 2, read 1");
    expect(folds[0]!.querySelectorAll(".tool-card")).toHaveLength(3);
    const order = [...container.querySelectorAll(".message--assistant, details.tool-group")].map((node) => (node.tagName === "DETAILS" ? "steps" : node.textContent));
    expect(order).toEqual(["I will load the skill.", "steps", "Here is the answer."]);
  });

  it("shows a running step on the line, and opens the fold when a step failed", () => {
    const running = play([begin, ...tool("1", "find", "search"), { type: "tool_start", toolId: "2", name: "read", kind: "read", path: "paper/main.tex" }]);
    const { container, unmount } = render(<MessageList timeline={running.timeline} />);
    expect(container.querySelector("details.tool-group summary")?.textContent).toBe("2 steps, working: read paper/main.tex");
    unmount();
    const failed = play([begin, ...tool("1", "find", "search"), { type: "tool_start", toolId: "2", name: "read", kind: "read" }, { type: "tool_end", toolId: "2", status: "failed" }, { type: "done", reason: "completed" }]);
    const second = render(<MessageList timeline={failed.timeline} />);
    const fold = second.container.querySelector<HTMLDetailsElement>("details.tool-group")!;
    expect(fold.open).toBe(true);
    expect(fold.querySelector("summary")?.textContent).toBe("2 steps: find 1, read 1 (1 failed)");
  });
});

describe("MessageList messages to a PaperSmith agent", () => {
  it("names the agent above the user's words instead of showing its command", () => {
    const { container } = render(<MessageList timeline={play([begin], "/math-tutor why is eq. 3 exact?").timeline} />);
    const sent = container.querySelector(".message--user")!;
    expect(sent.querySelector(".message__agent")?.textContent).toBe("Math tutor");
    expect(sent).toHaveTextContent("why is eq. 3 exact?");
    expect(sent).not.toHaveTextContent("/math-tutor");
  });

  it("shows a message with no words as the agent's beginning, and leaves any other slash as typed", () => {
    expect(render(<MessageList timeline={play([begin], "/experiments-tutor").timeline} />).container.querySelector(".message--user")).toHaveTextContent("Experiments tutorBegin");
    const other = render(<MessageList timeline={play([begin], "/paper/main.tex has a typo").timeline} />).container.querySelector(".message--user")!;
    expect(other.textContent).toBe("/paper/main.tex has a typo");
  });
});

describe("MessageList PaperSmith tutor answers", () => {
  const answer = {
    image_reading: "",
    reply: "Equation 3 is exact because the **colouring** is proper.",
    question: "Which bond would break it?",
    latex: ["w=\\min(4, 2^{v_2(B)})"],
    assessment: { level: 1, label: "partial", evidence: "You named the colouring.", gaps: ["detailed balance"] },
    novelty_link: "Pillar P2 rests on it.",
    next_step: "Draw a small lattice.",
  };
  const text = "I will load the skill.\n```json\n" + JSON.stringify(answer, null, 2) + "\n```";

  it("shows the answer as readable sections and keeps the raw JSON folded", () => {
    const state = play([begin, { type: "text", messageId: "m", text }, { type: "done", reason: "completed" }]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    const reply = container.querySelector(".message--assistant")!;
    expect(reply).toHaveTextContent("I will load the skill.");
    expect(reply.querySelector(".tutor-reply strong")?.textContent).toBe("colouring");
    const sections = [...reply.querySelectorAll(".tutor-reply__label")].map((label) => label.textContent);
    expect(sections).toEqual(["Question", "Formulas", "Assessment", "Why it matters for the novelty", "Next step"]);
    expect(reply).toHaveTextContent("partial (level 1)");
    expect(reply.querySelector(".tutor-reply .tex-math--display .katex")).not.toBeNull();
    expect(reply).toHaveTextContent("detailed balance");
    const raw = reply.querySelector<HTMLDetailsElement>("details.tutor-reply__raw")!;
    expect(raw.open).toBe(false);
    expect(raw).toHaveTextContent('"image_reading"');
  });

  it("leaves other JSON blocks as code", () => {
    const state = play([begin, { type: "text", messageId: "m", text: '```json\n{"a": 1}\n```' }, { type: "done", reason: "completed" }]);
    const { container } = render(<MessageList timeline={state.timeline} />);
    expect(container.querySelector(".tutor-reply")).toBeNull();
    expect(container.querySelector(".message--assistant pre")?.textContent).toContain('"a": 1');
  });
});
