import type { FileEntry, RelPath } from "@caztor/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { apiError, createFakeApi, type FakeApiInit } from "../testing/fake-api.ts";
import { FileTree } from "./FileTree.tsx";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const dir = (path: string): FileEntry => ({ path: path as RelPath, kind: "dir", size: 0 });
const PROJECT: FileEntry[] = [file("main.tex", 120), dir("chapters"), file("chapters/intro.tex"), file("chapters/two.tex")];

function setup(init: FakeApiInit = {}) {
  const fake = createFakeApi({ files: PROJECT, ...init });
  const onDeleted = vi.fn();
  render(<FileTree api={fake.api} selectedPath={null} onOpen={() => {}} onDeleted={onDeleted} />);
  return { fake, user: userEvent.setup(), onDeleted };
}

const deleteCalls = (calls: string[]) => calls.filter((call) => call.startsWith("deleteEntry"));

describe("deleting", () => {
  it("asks before deleting a file and deletes nothing when the user cancels", async () => {
    const { fake, user, onDeleted } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Delete main.tex" }));

    const dialog = screen.getByRole("dialog", { name: "Delete main.tex?" });
    expect(dialog).toHaveTextContent("This cannot be undone.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(deleteCalls(fake.calls)).toEqual([]);
    expect(onDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^main\.tex/ })).toBeInTheDocument();
  });

  it("deletes a file after confirmation and tells the app", async () => {
    const { fake, user, onDeleted } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Delete main.tex" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect(deleteCalls(fake.calls)).toEqual(["deleteEntry main.tex plain"]);
    expect(onDeleted).toHaveBeenCalledWith("main.tex");
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: /^main\.tex/ })).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps a folder and everything in it until the user confirms, then deletes it recursively", async () => {
    const { fake, user, onDeleted } = setup();
    await screen.findByRole("button", { name: /^chapters/ });
    await user.click(screen.getByRole("button", { name: "Delete chapters" }));

    const dialog = screen.getByRole("dialog", { name: "Delete folder chapters?" });
    expect(dialog).toHaveTextContent("Everything inside it is deleted too. This cannot be undone.");
    expect(deleteCalls(fake.calls)).toEqual([]);
    expect(fake.state.files).toHaveLength(4);

    await user.click(within(dialog).getByRole("button", { name: "Delete folder" }));
    expect(deleteCalls(fake.calls)).toEqual(["deleteEntry chapters recursive"]);
    expect(fake.state.files.map((entry) => entry.path)).toEqual(["main.tex"]);
    expect(onDeleted).toHaveBeenCalledWith("chapters");
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: /^intro\.tex/ })).toBeNull());
  });

  it("closes the question on Escape without deleting", async () => {
    const { fake, user } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Delete main.tex" }));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(deleteCalls(fake.calls)).toEqual([]);
  });

  it("shows the readable error in the question and keeps the file when deleting fails", async () => {
    const { fake, user, onDeleted } = setup();
    await screen.findByRole("button", { name: /^main\.tex/ });
    await user.click(screen.getByRole("button", { name: "Delete main.tex" }));
    fake.failNext(apiError("io", '"main.tex" could not be read or written.', 500, "main.tex"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent('"main.tex" could not be read or written.');
    expect(onDeleted).not.toHaveBeenCalled();
    expect(fake.state.files.map((entry) => entry.path)).toContain("main.tex");
  });
});
