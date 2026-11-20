import { describe, expect, it } from "vitest";
import { boundLogText, MAX_SHOWN_LOG_CHARS } from "./log-text.ts";

describe("boundLogText", () => {
  it("shows a short log as it is", () => {
    expect(boundLogText("short\nlog")).toEqual({ text: "short\nlog", hidden: 0 });
  });

  it("shows the end of a long log, which is where a run reports, and says how much is hidden", () => {
    const text = `${"a".repeat(MAX_SHOWN_LOG_CHARS)}THE END`;
    const shown = boundLogText(text);
    expect(shown.hidden).toBe(7);
    expect(shown.text.length).toBe(MAX_SHOWN_LOG_CHARS);
    expect(shown.text.endsWith("THE END")).toBe(true);
  });
});
