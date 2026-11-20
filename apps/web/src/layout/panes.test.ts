import { describe, expect, it } from "vitest";
import { DEFAULT_LAYOUT, PANES, parseLayout } from "./panes.ts";

describe("pane definitions", () => {
  it("orders the panes file tree, editor, preview, chat", () => {
    expect(PANES.map((pane) => pane.id)).toEqual(["files", "editor", "preview", "chat"]);
    expect(PANES.map((pane) => pane.title)).toEqual(["Files", "LaTeX editor", "PDF preview", "Chat"]);
  });

  it("uses the 15/35/30/20 defaults and the 160/280/280/300 pixel minimums", () => {
    expect(DEFAULT_LAYOUT).toEqual({ files: 15, editor: 35, preview: 30, chat: 20 });
    expect(PANES.map((pane) => pane.minWidth)).toEqual([160, 280, 280, 300]);
  });
});

describe("parseLayout", () => {
  const valid = { files: 18, editor: 30, preview: 30, chat: 22 };

  it("accepts four numbers that fill the container and meet every minimum", () => {
    expect(parseLayout(valid)).toEqual(valid);
  });

  it("tolerates a small rounding error in the total", () => {
    expect(parseLayout({ files: 18.2, editor: 29.9, preview: 30, chat: 22 })).toEqual({ files: 18.2, editor: 29.9, preview: 30, chat: 22 });
  });

  it.each([
    ["null", null],
    ["an array", [20, 30, 30, 20]],
    ["a string", "files"],
    ["a missing pane", { files: 20, editor: 30, preview: 50 }],
    ["an extra pane", { ...valid, extra: 0 }],
    ["a text size", { ...valid, files: "20" }],
    ["NaN", { ...valid, files: Number.NaN }],
    ["Infinity", { ...valid, files: Number.POSITIVE_INFINITY }],
    ["a negative size", { files: -10, editor: 50, preview: 40, chat: 20 }],
    ["a total below 100", { files: 10, editor: 10, preview: 10, chat: 10 }],
    ["a total above 100", { files: 40, editor: 40, preview: 40, chat: 40 }],
  ])("rejects %s", (_label, value) => {
    expect(parseLayout(value)).toBeNull();
  });

  it("accepts a small pane at any window width, because the pane library clamps to the pixel minimums", () => {
    const narrowFiles = { files: 5, editor: 40, preview: 33, chat: 22 };
    expect(parseLayout(narrowFiles)).toEqual(narrowFiles);
    expect(parseLayout({ files: 0.5, editor: 40, preview: 37.5, chat: 22 })).toEqual({ files: 0.5, editor: 40, preview: 37.5, chat: 22 });
  });

  it("still rejects a zero-sized pane", () => {
    expect(parseLayout({ files: 0, editor: 40, preview: 38, chat: 22 })).toBeNull();
  });
});
