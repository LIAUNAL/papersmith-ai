import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UndoConflictDialog } from "./UndoConflictDialog.tsx";

const conflicts = [
  { path: "main.tex", expected: "sha256:a", actual: "sha256:b" },
  { path: "refs.bib", expected: "sha256:c", actual: null },
];

function setup() {
  const handlers = { onCancel: vi.fn(), onKeepMine: vi.fn(), onOverwrite: vi.fn() };
  render(<UndoConflictDialog conflicts={conflicts} {...handlers} />);
  return { handlers, dialog: screen.getByRole("dialog", { name: "Some files changed after this turn" }) };
}

describe("UndoConflictDialog", () => {
  it("names the files that changed and offers the three choices", () => {
    const { dialog } = setup();
    expect(within(dialog).getByText("main.tex")).toBeInTheDocument();
    expect(within(dialog).getByText("refs.bib")).toBeInTheDocument();
    expect(within(dialog).getAllByRole("button").map((button) => button.textContent)).toEqual(["Cancel", "Undo the rest and keep my edits", "Overwrite my edits"]);
  });

  it("calls the handler of the chosen action", async () => {
    const { handlers, dialog } = setup();
    await userEvent.click(within(dialog).getByRole("button", { name: "Undo the rest and keep my edits" }));
    expect(handlers.onKeepMine).toHaveBeenCalledTimes(1);
    await userEvent.click(within(dialog).getByRole("button", { name: "Overwrite my edits" }));
    expect(handlers.onOverwrite).toHaveBeenCalledTimes(1);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(handlers.onCancel).toHaveBeenCalledTimes(1);
  });

  it("cancels with Escape and puts the safe choice first", async () => {
    const { handlers } = setup();
    await userEvent.keyboard("{Escape}");
    expect(handlers.onCancel).toHaveBeenCalled();
  });

  it("explains that overwriting loses the edits but takes a safety snapshot first", () => {
    const { dialog } = setup();
    expect(within(dialog).getByText(/safety snapshot/i)).toBeInTheDocument();
  });
});
