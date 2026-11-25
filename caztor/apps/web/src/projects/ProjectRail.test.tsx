import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ProjectEntry } from "../api/types.ts";
import { ProjectRail, RAIL_KEY } from "./ProjectRail.tsx";

const PROJECTS: ProjectEntry[] = [
  { path: "/p/first", name: "first", kind: "folder", active: true },
  { path: "/p/spin", name: "spin", kind: "papersmith", title: "Spin states", active: false },
  { path: "/p/empty", name: "empty", kind: "papersmith", missingMain: true, active: false },
];
const memory = (initial: Record<string, string> = {}) => {
  const items = new Map(Object.entries(initial));
  return { getItem: (key: string) => items.get(key) ?? null, setItem: (key: string, value: string) => void items.set(key, value) };
};
function setup(options: { list?: () => Promise<ProjectEntry[]>; onOpen?: (path: string) => Promise<string | null>; onCreate?: (name: string) => Promise<string | null>; storage?: ReturnType<typeof memory> } = {}) {
  const onOpen = vi.fn(options.onOpen ?? (async () => null));
  const onCreate = vi.fn(options.onCreate ?? (async () => null));
  render(<ProjectRail list={options.list ?? (async () => PROJECTS)} onOpen={onOpen} onCreate={onCreate} storage={options.storage ?? memory()} />);
  return { onOpen, onCreate };
}
const row = (name: string | RegExp) => screen.findByRole("button", { name });

describe("ProjectRail", () => {
  it("lists the projects, marks the active one, and shows which are PaperSmith workspaces", async () => {
    setup();
    expect(await row(/^first/)).toHaveAttribute("aria-current", "true");
    const spin = await row(/^spin/);
    expect(spin).not.toHaveAttribute("aria-current");
    expect(spin).toHaveAccessibleName(/PaperSmith/);
    expect(spin).toHaveAttribute("title", "Spin states\n/p/spin");
    expect(within(await row(/^empty/)).getByText("No paper/main.tex yet")).toBeInTheDocument();
    expect(within(await row(/^first/)).queryByText("PaperSmith")).toBeNull();
  });

  it("opens a project on click, and does nothing for the active one", async () => {
    const { onOpen } = setup();
    await userEvent.click(await row(/^first/));
    expect(onOpen).not.toHaveBeenCalled();
    await userEvent.click(await row(/^spin/));
    expect(onOpen).toHaveBeenCalledWith("/p/spin");
  });

  it("moves with the arrow keys, wraps, and opens with Enter", async () => {
    const { onOpen } = setup();
    (await row(/^first/)).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(await row(/^spin/)).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(await row(/^empty/)).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(onOpen).toHaveBeenCalledWith("/p/spin");
  });

  it("shows why a project could not be opened", async () => {
    setup({ onOpen: async () => "Stop the running turn before opening another project." });
    await userEvent.click(await row(/^spin/));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stop the running turn");
  });

  it("opens a folder by its path, and keeps the path when that fails", async () => {
    const { onOpen } = setup({ onOpen: async () => "The project folder does not exist: /nope" });
    const input = await screen.findByRole("textbox", { name: "Folder path" });
    expect(screen.getByRole("button", { name: "Open" })).toBeDisabled();
    await userEvent.type(input, "/nope{Enter}");
    expect(onOpen).toHaveBeenCalledWith("/nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist");
    expect(input).toHaveValue("/nope");
  });

  it("creates a project from the New project button, with a name", async () => {
    const { onCreate } = setup();
    await row(/^first/);
    expect(screen.queryByRole("textbox", { name: "Project name" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    const name = screen.getByRole("textbox", { name: "Project name" });
    expect(name).toHaveFocus();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    await userEvent.type(name, " my-thesis {Enter}");
    expect(onCreate).toHaveBeenCalledWith("my-thesis");
  });

  it("keeps the name and shows why when it cannot be created", async () => {
    setup({ onCreate: async () => 'A project named "spin" already exists.' });
    await row(/^first/);
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Project name" }), "spin{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByRole("textbox", { name: "Project name" })).toHaveValue("spin");
  });

  it("closes the form with Escape and with Cancel, creating nothing", async () => {
    const { onCreate } = setup();
    await row(/^first/);
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    await userEvent.keyboard("abc{Escape}");
    expect(screen.queryByRole("textbox", { name: "Project name" })).toBeNull();
    expect(screen.getByRole("button", { name: "New project" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox", { name: "Project name" })).toBeNull();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("folds and remembers it", async () => {
    const storage = memory();
    setup({ storage });
    await row(/^first/);
    await userEvent.click(screen.getByRole("button", { name: "Hide projects" }));
    expect(screen.queryByRole("button", { name: /^first/ })).toBeNull();
    expect(storage.getItem(RAIL_KEY)).toBe("collapsed");
    await userEvent.click(screen.getByRole("button", { name: "Show projects" }));
    expect(await row(/^first/)).toBeInTheDocument();
    expect(storage.getItem(RAIL_KEY)).toBe("open");
  });

  it("starts folded when that was the choice", () => {
    setup({ storage: memory({ [RAIL_KEY]: "collapsed" }) });
    expect(screen.getByRole("button", { name: "Show projects" })).toHaveAttribute("aria-expanded", "false");
  });

  it("says when there is nothing to list, and when the list cannot be read", async () => {
    setup({ list: async () => [] });
    expect(await screen.findByText(/No PaperSmith workspaces found/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("still lets a folder be opened when the list fails", async () => {
    setup({ list: async () => Promise.reject(new Error("The list failed.")) });
    expect(await screen.findByRole("alert")).toHaveTextContent("The list failed.");
    expect(screen.getByRole("textbox", { name: "Folder path" })).toBeEnabled();
  });
});
