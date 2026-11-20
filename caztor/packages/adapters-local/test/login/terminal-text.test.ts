import { describe, expect, it } from "vitest";
import { createTerminalText, MAX_ROWS } from "../../src/login/terminal-text.ts";

const fed = (...chunks: Array<string | Uint8Array>) => {
  const screen = createTerminalText();
  for (const chunk of chunks) screen.feed(typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk);
  return screen.text();
};

describe("the text of a CLI's output", () => {
  it("keeps plain lines as they come, and a line still being written", () => {
    expect(fed("Opening browser to sign in…\nIf the browser didn't open, visit: https://x.test/a?b=1\n", "Paste code here if prompted > ")).toBe(
      "Opening browser to sign in…\nIf the browser didn't open, visit: https://x.test/a?b=1\nPaste code here if prompted >",
    );
  });

  it("drops colours, links and titles, keeping their text (codex's device code)", () => {
    expect(fed("1. Open this link\n   \u001b[94mhttps://auth.openai.com/codex/device\u001b[0m\n\u001b]8;;\u0007\u001b]0;π - p\u0007   \u001b[94mXZIF-17WOH\u001b[0m\n")).toBe(
      "1. Open this link\n   https://auth.openai.com/codex/device\n   XZIF-17WOH",
    );
  });

  it("shows only the last frame of a spinner that redraws its line (opencode)", () => {
    const frames = "◒  Waiting for authorization\u001b[999D\u001b[J◐  Waiting for authorization.\u001b[999D\u001b[J◓  Waiting for authorization..";
    expect(fed("●  Enter code: XZH3-GJO81\n\u001b[?25l│\n", frames)).toBe("●  Enter code: XZH3-GJO81\n│\n◓  Waiting for authorization..");
    expect(fed("50%\r100%\n")).toBe("100%");
  });

  it("places a full-screen program's rows where it draws them (pi, agy)", () => {
    const screen = "\u001b[?1049h\u001b[2J\u001b[H\u001b[2J\u001b[1;1H\u001b[2K\u001b[0m\u001b[2;1H\u001b[2K v1.4.0\u001b[3;1H\u001b[2K Select provider\u001b[2;1H\u001b[2K v1.4.1";
    expect(fed(screen)).toBe("\n v1.4.1\n Select provider");
  });

  it("joins characters and escape sequences split between chunks", () => {
    const bytes = new TextEncoder().encode("é\u001b[94mlink\u001b[0m\n");
    expect(fed(bytes.slice(0, 1), bytes.slice(1, 4), bytes.slice(4))).toBe("élink");
  });

  it("keeps a bounded number of rows and characters per row", () => {
    const many = Array.from({ length: MAX_ROWS + 50 }, (_, index) => `line ${index}\n`).join("");
    const rows = fed(many).split("\n");
    expect(rows.length).toBeLessThanOrEqual(MAX_ROWS);
    expect(rows.length).toBeGreaterThan(MAX_ROWS - 2);
    expect(rows.at(-1)).toBe(`line ${MAX_ROWS + 49}`);
    expect(fed("x".repeat(10_000)).length).toBeLessThanOrEqual(2_000);
  });
});
