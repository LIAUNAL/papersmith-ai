import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { DEFAULT_LAYOUT } from "./panes.ts";
import { createLayoutStore, LAYOUT_KEY } from "./storage.ts";
import { Workspace } from "./Workspace.tsx";

const WORKSPACE_WIDTH = 1600;

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // jsdom does no layout: give every element the workspace width so the library can measure and resize.
  Object.defineProperty(window, "innerWidth", { configurable: true, value: WORKSPACE_WIDTH });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => WORKSPACE_WIDTH });
  HTMLElement.prototype.getBoundingClientRect = () =>
    ({ x: 0, y: 0, top: 0, left: 0, right: WORKSPACE_WIDTH, bottom: 800, width: WORKSPACE_WIDTH, height: 800, toJSON: () => ({}) }) as DOMRect;
});

const separatorSizes = () => screen.getAllByRole("separator").map((separator) => Number(separator.getAttribute("aria-valuenow")));

describe("Workspace", () => {
  it("renders the four panes in order with their titles and a divider between each pair", () => {
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
    expect(screen.getAllByRole("region").map((region) => region.getAttribute("aria-label"))).toEqual([
      "Files",
      "LaTeX editor",
      "PDF preview",
      "Chat",
    ]);
    expect(screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual(["Files", "LaTeX editor", "PDF preview", "Chat"]);
    expect(screen.getAllByRole("separator")).toHaveLength(3);
  });

  it("shows an empty state in the editor, preview and chat panes", () => {
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
    expect(within(screen.getByRole("region", { name: "LaTeX editor" })).getByText("No file open")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "PDF preview" })).getByText("No preview yet")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Chat" })).getByText("Chat is not connected yet")).toBeInTheDocument();
  });

  it("starts with the 15/35/30 default sizes when nothing was saved", () => {
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
    expect(separatorSizes()).toEqual([DEFAULT_LAYOUT.files, DEFAULT_LAYOUT.editor, DEFAULT_LAYOUT.preview]);
  });

  it("restores the saved sizes", () => {
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify({ files: 18, editor: 28, preview: 32, chat: 22 }));
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
    expect(separatorSizes()).toEqual([18, 28, 32]);
  });

  it.each([["unparseable text", "{oops"], ["three numbers", JSON.stringify({ files: 30, editor: 30, preview: 40 })], ["a zero-sized pane", JSON.stringify({ files: 0, editor: 40, preview: 38, chat: 22 })]])(
    "uses the defaults for a saved layout with %s and renders without an error",
    (_label, saved) => {
      window.localStorage.setItem(LAYOUT_KEY, saved);
      render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
      expect(separatorSizes()).toEqual([15, 35, 30]);
      expect(screen.getAllByRole("region")).toHaveLength(4);
      expect(screen.queryByRole("alert")).toBeNull();
    },
  );

  it("saves the sizes after the user moves a divider with the keyboard", async () => {
    const user = userEvent.setup();
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
    const [divider] = screen.getAllByRole("separator");
    divider?.focus();
    await user.keyboard("{ArrowRight}");
    const saved = JSON.parse(window.localStorage.getItem(LAYOUT_KEY) ?? "null") as Record<string, number> | null;
    expect(saved?.["files"]).toBeGreaterThan(15);
    expect(saved?.["editor"]).toBeLessThan(35);
    expect(saved?.["preview"]).toBe(30);
    expect(saved?.["chat"]).toBe(20);
  });

  it("renders the content it is given in the matching pane and keeps the others on their empty states", () => {
    render(<Workspace layoutStore={createLayoutStore(window.localStorage)} content={{ files: <p>tree goes here</p> }} />);
    expect(within(screen.getByRole("region", { name: "Files" })).getByText("tree goes here")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "PDF preview" })).getByText("No preview yet")).toBeInTheDocument();
  });

  it("keeps a saved layout when the window is narrower than the one it was saved on", () => {
    const saved = { files: 12, editor: 30, preview: 33, chat: 25 };
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(saved));
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 900 });
    try {
      render(<Workspace layoutStore={createLayoutStore(window.localStorage)} />);
      expect(separatorSizes()).toEqual([12, 30, 33]);
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: WORKSPACE_WIDTH });
    }
  });
});
