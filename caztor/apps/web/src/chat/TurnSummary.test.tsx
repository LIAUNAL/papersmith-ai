import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChangedFile, ChatTurn } from "@caztor/core";
import { TurnSummary } from "./TurnSummary.tsx";

const file = (path: string, patch: Partial<ChangedFile> = {}): ChangedFile => ({ path: path as ChangedFile["path"], change: "modified", beforeHash: null, afterHash: null, undoable: true, mixed: false, ...patch });
const turn = (patch: Partial<ChatTurn> = {}): ChatTurn => ({ key: "k", turnId: "t1", prompt: "p", status: "completed", items: [], files: [file("a.tex")], snapshotPartial: false, unprotected: [], notCovered: [], ...patch });

function setup(patch: Partial<ChatTurn> = {}, props: Partial<Parameters<typeof TurnSummary>[0]> = {}) {
  const onUndo = vi.fn();
  const onOpenFile = vi.fn();
  render(<TurnSummary turn={turn(patch)} canUndo undone={false} onUndo={onUndo} onOpenFile={onOpenFile} {...props} />);
  return { onUndo, onOpenFile };
}

describe("TurnSummary", () => {
  it("lists the changed files with what happened to each, and offers undo on the undoable turn", async () => {
    const { onUndo } = setup({ files: [file("a.tex"), file("new.tex", { change: "created" }), file("old.tex", { change: "deleted" })] });
    expect(screen.getByText("Changed files")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "a.tex" })).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Deleted")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo this turn" }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("says No files changed, with no undo", () => {
    setup({ files: [] });
    expect(screen.getByText("No files changed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /undo/i })).toBeNull();
  });

  it("shows no undo action on a turn that is not the undoable one", () => {
    setup({}, { canUndo: false });
    expect(screen.getByRole("button", { name: "a.tex" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /undo/i })).toBeNull();
  });

  it("opens a file in the editor when it is clicked, but a deleted file is only text", async () => {
    const { onOpenFile } = setup({ files: [file("sections/intro.tex"), file("gone.tex", { change: "deleted" })] });
    await userEvent.click(screen.getByRole("button", { name: "sections/intro.tex" }));
    expect(onOpenFile).toHaveBeenCalledWith("sections/intro.tex");
    expect(screen.queryByRole("button", { name: "gone.tex" })).toBeNull();
    expect(screen.getByText("gone.tex")).toBeInTheDocument();
  });

  it("shows nothing while the turn runs or before the list arrives", () => {
    const { container } = render(<TurnSummary turn={turn({ status: "running" })} canUndo={false} undone={false} onUndo={() => {}} onOpenFile={() => {}} />);
    expect(container).toBeEmptyDOMElement();
    const waiting = render(<TurnSummary turn={turn({ files: null })} canUndo={false} undone={false} onUndo={() => {}} onOpenFile={() => {}} />);
    expect(waiting.container).toBeEmptyDOMElement();
  });

  it("lists the changes of a stopped or failed turn and still allows undo", () => {
    setup({ status: "cancelled" });
    expect(screen.getByRole("button", { name: "Undo this turn" })).toBeInTheDocument();
  });

  it("warns about files that undo cannot cover and about files the user also edited", () => {
    setup({ files: [file("a.tex", { mixed: true }), file("big.pdf", { undoable: false })], snapshotPartial: true, unprotected: ["big.pdf" as never] });
    expect(screen.getByText(/also edited by you/i)).toBeInTheDocument();
    expect(screen.getByText(/not covered by undo/i)).toBeInTheDocument();
    expect(screen.getByText("1 file not protected by undo").closest("details")).toHaveTextContent("big.pdf");
  });

  it("reports files with names Caztor cannot read as not covered by undo", () => {
    setup({ notCovered: ["made\uFFFD.tex" as never] });
    expect(screen.getByText(/names Caztor cannot read/i)).toHaveTextContent("made\uFFFD.tex");
    expect(screen.getByText(/not covered by undo/i, { selector: ".turn-summary__warning" })).toBeInTheDocument();
  });

  it("shows Undone instead of the action once the turn was undone", () => {
    setup({}, { undone: true });
    expect(screen.getByText("Undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /undo/i })).toBeNull();
  });
});

describe("TurnSummary files not protected by undo", () => {
  const many = Array.from({ length: 20 }, (_, index) => `data/run-${index}.npz` as ChangedFile["path"]);

  it("says nothing about them when the turn changed no file", () => {
    setup({ files: [], unprotected: many, unprotectedCount: 65 });
    expect(screen.getByText("No files changed")).toBeInTheDocument();
    expect(screen.queryByText(/not protected by undo/i)).toBeNull();
  });

  it("puts them in a folded list when the turn changed files, with the count in its title", async () => {
    setup({ files: [file("a.tex")], unprotected: many, unprotectedCount: 65 });
    const title = screen.getByText("65 files not protected by undo");
    const fold = title.closest("details")!;
    expect(fold.open).toBe(false);
    await userEvent.click(title);
    expect(fold.open).toBe(true);
    expect(fold).toHaveTextContent("data/run-0.npz");
    expect(fold).toHaveTextContent("and 45 more");
  });

  it("says one file in the singular", () => {
    setup({ files: [file("a.tex")], unprotected: ["big.pdf" as ChangedFile["path"]] });
    expect(screen.getByText("1 file not protected by undo")).toBeInTheDocument();
  });
});

