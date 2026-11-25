import type { FileEntry, RelPath } from "@caztor/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createFakeApi, type FakeApiInit } from "../testing/fake-api.ts";
import { FileTree } from "./FileTree.tsx";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const dir = (path: string): FileEntry => ({ path: path as RelPath, kind: "dir", size: 0 });
const PROJECT: FileEntry[] = [file("main.tex", 120), dir("chapters"), file("chapters/intro.tex")];

function setup(init: FakeApiInit = {}) {
  const fake = createFakeApi({ files: PROJECT, ...init });
  const onRenamed = vi.fn();
  render(<FileTree api={fake.api} selectedPath={null} onOpen={() => {}} onRenamed={onRenamed} />);
  const user = userEvent.setup();
  return { fake, user, onRenamed };
}

const names = () => screen.getAllByRole("listitem").map((item) => within(item).getAllByRole("button")[0]?.textContent ?? "");

describe("creating files and folders", () => {
  it("creates a file from the toolbar and shows it in the tree", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New file" }));
    await user.type(screen.getByRole("textbox", { name: "New file name" }), "refs.bib{Enter}");

    expect(fake.calls).toContain("createEntry refs.bib file");
    expect(await screen.findByRole("button", { name: /^refs\.bib/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("creates a folder", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New folder" }));
    await user.type(screen.getByRole("textbox", { name: "New folder name" }), "figs{Enter}");

    expect(fake.calls).toContain("createEntry figs dir");
    expect(await screen.findByRole("button", { name: /^figs/ })).toHaveAttribute("aria-expanded");
  });

  it("creates inside the folder that was last selected and says so", async () => {
    const { fake, user } = setup();
    await user.click(await screen.findByRole("button", { name: /^chapters/ }));
    await user.click(screen.getByRole("button", { name: "New file" }));
    expect(screen.getByText("New file in chapters")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "New file name" }), "two.tex{Enter}");

    expect(fake.calls).toContain("createEntry chapters/two.tex file");
    expect(await screen.findByRole("button", { name: /^two\.tex/ })).toBeInTheDocument();
  });

  it("rejects a name collision with the readable message, keeps the form and leaves the existing file alone", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New file" }));
    await user.type(screen.getByRole("textbox", { name: "New file name" }), "main.tex{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent('"main.tex" already exists. Choose another name.');
    expect(screen.getByRole("textbox", { name: "New file name" })).toHaveValue("main.tex");
    expect(names().filter((name) => name === "main.tex")).toHaveLength(1);
    expect(fake.state.files.find((entry) => entry.path === "main.tex")?.size).toBe(120);
  });

  it.each([
    ["an empty name", "{Enter}", "Enter a name."],
    ["a name with a slash", "a/b.tex{Enter}", "Names cannot contain / or \\."],
    ["a name with a backslash", "a\\b.tex{Enter}", "Names cannot contain / or \\."],
  ])("explains %s without sending a request", async (_label, typing, message) => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New file" }));
    await user.type(screen.getByRole("textbox", { name: "New file name" }), typing);

    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(fake.calls.some((call) => call.startsWith("createEntry"))).toBe(false);
  });

  it("closes the form on Escape without creating anything", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New file" }));
    await user.type(screen.getByRole("textbox", { name: "New file name" }), "draft.tex{Escape}");

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(fake.calls.some((call) => call.startsWith("createEntry"))).toBe(false);
  });
});

describe("renaming", () => {
  it("renames a file in place and tells the app", async () => {
    const { fake, user, onRenamed } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Rename main.tex" }));
    const input = screen.getByRole("textbox", { name: "New name for main.tex" });
    expect(input).toHaveValue("main.tex");
    await user.clear(input);
    await user.type(input, "thesis.tex{Enter}");

    expect(fake.calls).toContain("renameEntry main.tex thesis.tex");
    expect(await screen.findByRole("button", { name: /^thesis\.tex/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^main\.tex/ })).toBeNull();
    expect(onRenamed).toHaveBeenCalledWith("main.tex", "thesis.tex");
  });

  it("keeps a renamed file in its folder", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^intro\.tex/ });
    await user.click(screen.getByRole("button", { name: "Rename chapters/intro.tex" }));
    const input = screen.getByRole("textbox", { name: "New name for chapters/intro.tex" });
    await user.clear(input);
    await user.type(input, "ch1.tex{Enter}");

    expect(fake.calls).toContain("renameEntry chapters/intro.tex chapters/ch1.tex");
    expect(await screen.findByRole("button", { name: /^ch1\.tex/ })).toBeInTheDocument();
  });

  it("renames a folder together with its content", async () => {
    const { fake, user, onRenamed } = setup();
    await screen.findByRole("button", { name: /^chapters/ });
    await user.click(screen.getByRole("button", { name: "Rename chapters" }));
    const input = screen.getByRole("textbox", { name: "New name for chapters" });
    await user.clear(input);
    await user.type(input, "parts{Enter}");

    expect(await screen.findByRole("button", { name: /^parts/ })).toBeInTheDocument();
    expect(fake.state.files.map((entry) => entry.path)).toContain("parts/intro.tex");
    expect(onRenamed).toHaveBeenCalledWith("chapters", "parts");
  });

  it("rejects a collision with the readable message and leaves both files", async () => {
    const { fake, user, onRenamed } = setup({ files: [file("a.tex"), file("b.tex")] });
    await screen.findByRole("button", { name: /^a\.tex/ });
    await user.click(screen.getByRole("button", { name: "Rename a.tex" }));
    const input = screen.getByRole("textbox", { name: "New name for a.tex" });
    await user.clear(input);
    await user.type(input, "b.tex{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent('"b.tex" already exists. Choose another name.');
    expect(fake.state.files.map((entry) => entry.path)).toEqual(["a.tex", "b.tex"]);
    expect(onRenamed).not.toHaveBeenCalled();
  });

  it("closes without a request when the name did not change, and on Escape", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Rename main.tex" }));
    await user.type(screen.getByRole("textbox", { name: "New name for main.tex" }), "{Enter}");
    expect(screen.queryByRole("textbox")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Rename main.tex" }));
    await user.type(screen.getByRole("textbox", { name: "New name for main.tex" }), "x{Escape}");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(fake.calls.some((call) => call.startsWith("renameEntry"))).toBe(false);
  });

  it("creates refs.bib and renames it to bib.bib, leaving only bib.bib", async () => {
    const { user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "New file" }));
    await user.type(screen.getByRole("textbox", { name: "New file name" }), "refs.bib{Enter}");
    await screen.findByRole("button", { name: /^refs\.bib/ });
    await user.click(screen.getByRole("button", { name: "Rename refs.bib" }));
    const input = screen.getByRole("textbox", { name: "New name for refs.bib" });
    await user.clear(input);
    await user.type(input, "bib.bib{Enter}");

    expect(await screen.findByRole("button", { name: /^bib\.bib/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^refs\.bib/ })).toBeNull();
  });
});
