import type { FileEntry, RelPath } from "@caztor/core";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { apiError, createFakeApi, type FakeApiInit } from "../testing/fake-api.ts";
import { FileTree } from "./FileTree.tsx";

const file = (path: string, size = 10): FileEntry => ({ path: path as RelPath, kind: "file", size });
const dir = (path: string): FileEntry => ({ path: path as RelPath, kind: "dir", size: 0 });

const PROJECT: FileEntry[] = [file("main.tex", 120), dir("chapters"), file("chapters/intro.tex"), file("figure.png", 4000), file("refs.bib")];

const largeProject = (): FileEntry[] => [
  { path: "paper" as RelPath, kind: "dir", size: 0 },
  { path: "paper/main.tex" as RelPath, kind: "file", size: 1 },
  { path: "guidance" as RelPath, kind: "dir", size: 0 },
  ...Array.from({ length: 400 }, (_, index) => ({ path: `guidance/f${index}.md` as RelPath, kind: "file" as const, size: 1 })),
];

function setup(init: FakeApiInit = {}, selectedPath: string | null = null) {
  const fake = createFakeApi({ files: PROJECT, contents: { "main.tex": "\\documentclass{article}" }, ...init });
  const onOpen = vi.fn();
  const view = render(<FileTree api={fake.api} selectedPath={selectedPath} onOpen={onOpen} />);
  return { fake, onOpen, view };
}

/** Visible file and folder names in document order. */
const rows = () => screen.getAllByRole("listitem").map((item) => within(item).getAllByRole("button")[0]?.textContent ?? "");

describe("FileTree listing", () => {
  it("shows folders first, then files by name, with folder content nested", async () => {
    setup();
    expect(await screen.findByRole("button", { name: /^main\.tex/ })).toBeInTheDocument();
    expect(rows().map((name) => name.replace(/Binary|Too large/, ""))).toEqual(["chapters", "intro.tex", "figure.png", "main.tex", "refs.bib"]);
  });

  it("shows a loading state, then an empty state for a project without files", async () => {
    setup({ files: [] });
    expect(screen.getByRole("status")).toHaveTextContent("Loading files");
    expect(await screen.findByText("This project has no files yet")).toBeInTheDocument();
  });

  it("collapses and expands a folder", async () => {
    const user = userEvent.setup();
    setup();
    const folder = await screen.findByRole("button", { name: /^chapters/ });
    expect(folder).toHaveAttribute("aria-expanded", "true");
    await user.click(folder);
    expect(folder).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /^intro\.tex/ })).toBeNull();
    await user.click(folder);
    expect(screen.getByRole("button", { name: /^intro\.tex/ })).toBeInTheDocument();
  });

  it("renders a file name that looks like HTML as plain text and creates no element from it", async () => {
    const hostile = "<img src=x onerror=alert(1)>.tex";
    const { view } = setup({ files: [file("main.tex"), file(hostile)] });
    expect(await screen.findByRole("button", { name: new RegExp(`^${hostile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) })).toBeInTheDocument();
    expect(view.container.querySelector("img")).toBeNull();
    expect(view.container.querySelectorAll("[onerror]")).toHaveLength(0);
  });

  it("never shows reserved folders even if the server lists them", async () => {
    setup({ files: [file("main.tex"), file(".git/config"), dir(".caztor"), file("node_modules/x.js")] });
    await screen.findByRole("button", { name: /^main\.tex/ });
    expect(screen.queryByText(".git")).toBeNull();
    expect(screen.queryByText(".caztor")).toBeNull();
    expect(screen.queryByText("node_modules")).toBeNull();
  });

  it("explains a listing failure and retries on request", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ files: PROJECT });
    fake.failAll(apiError("network", "Cannot reach the Caztor server. Check that it is still running.", 0));
    render(<FileTree api={fake.api} selectedPath={null} onOpen={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the Caztor server.");
    fake.recover();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: /^main\.tex/ })).toBeInTheDocument();
  });
});

describe("FileTree opening files", () => {
  it("reads a text file and hands its content over, marking it as the current file", async () => {
    const user = userEvent.setup();
    const { fake, onOpen } = setup();
    await user.click(await screen.findByRole("button", { name: /^main\.tex/ }));

    expect(fake.calls).toContain("readFile main.tex");
    expect(onOpen).toHaveBeenCalledWith({ path: "main.tex", content: "\\documentclass{article}", hash: "sha256:main.tex#0" });
  });

  it("marks the selected file for assistive technology", async () => {
    setup({}, "refs.bib");
    expect(await screen.findByRole("button", { name: /^refs\.bib/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: /^main\.tex/ })).not.toHaveAttribute("aria-current");
  });

  it("lists a binary file as binary and does not request it", async () => {
    const user = userEvent.setup();
    const { fake, onOpen } = setup();
    const row = await screen.findByRole("button", { name: /^figure\.png/ });
    expect(row).toHaveTextContent("Binary");
    await user.click(row);

    expect(fake.calls).not.toContain("readFile figure.png");
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("figure.png is a binary file and cannot be opened in the editor.");
  });

  it("lists a text file over 2 MB as too large and does not request it", async () => {
    const user = userEvent.setup();
    const { fake, onOpen } = setup({ files: [file("huge.tex", 3 * 1024 * 1024)] });
    const row = await screen.findByRole("button", { name: /^huge\.tex/ });
    expect(row).toHaveTextContent("Too large");
    await user.click(row);

    expect(fake.calls).not.toContain("readFile huge.tex");
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("huge.tex is larger than 2 MB and cannot be opened in the editor.");
  });

  it("learns from the server that a file is not text, shows its message and stops offering it", async () => {
    const user = userEvent.setup();
    const { fake, onOpen } = setup({ files: [file("data.dat", 50)] });
    const row = await screen.findByRole("button", { name: /^data\.dat/ });
    fake.failNext(apiError("not_text", '"data.dat" is not a UTF-8 text file.', 415, "data.dat"));
    await user.click(row);

    expect(await screen.findByRole("status")).toHaveTextContent('"data.dat" is not a UTF-8 text file.');
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^data\.dat/ })).toHaveTextContent("Binary");
    await user.click(screen.getByRole("button", { name: /^data\.dat/ }));
    expect(fake.calls.filter((call) => call === "readFile data.dat")).toHaveLength(1);
  });

  it("shows any other open failure as a readable message", async () => {
    const user = userEvent.setup();
    const { fake } = setup();
    const row = await screen.findByRole("button", { name: /^main\.tex/ });
    fake.failNext(apiError("io", '"main.tex" could not be read or written.', 500, "main.tex"));
    await user.click(row);
    expect(await screen.findByRole("alert")).toHaveTextContent('"main.tex" could not be read or written.');
  });
});

describe("a very large project", () => {
  it("starts with its folders folded, except paper", async () => {
    setup({ files: largeProject() });
    expect(await screen.findByRole("button", { name: /^main\.tex/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /^guidance/ })).toHaveAttribute("aria-expanded", "false"));
    expect(screen.queryByRole("button", { name: /^f0\.md/ })).toBeNull();
  });

  // Drawing a tree of more than 300 entries in jsdom passes the default 5 s when the whole suite runs at once.
  it("opens a folded folder on click", async () => {
    setup({ files: largeProject() });
    await userEvent.click(await screen.findByRole("button", { name: /^guidance/ }));
    expect(await screen.findByRole("button", { name: /^f0\.md/ })).toBeInTheDocument();
  }, 20_000);
});
