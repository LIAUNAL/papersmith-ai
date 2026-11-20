import type { RelPath } from "@caztor/core";
import { EditorView } from "@codemirror/view";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { EditorPane } from "./EditorPane.tsx";
import { AUTOSAVE_MS, EditorSession } from "./session.ts";

function setup() {
  const fake = createFakeApi({
    files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }],
    contents: { "main.tex": "hello" },
  });
  const session = new EditorSession({ api: fake.api });
  return { fake, session };
}

async function openMain(session: EditorSession, api: ReturnType<typeof createFakeApi>["api"]) {
  await act(async () => {
    session.open(await api.readFile("main.tex"));
    session.setActive("main.tex");
  });
}

function viewOf(container: HTMLElement): EditorView {
  const dom = container.querySelector<HTMLElement>(".cm-editor");
  const view = dom === null ? null : EditorView.findFromDOM(dom);
  if (view === null) throw new Error("The editor view was not rendered");
  return view;
}

const typeIn = (view: EditorView, text: string) =>
  act(() => view.dispatch({ changes: { from: view.state.doc.length, insert: text }, userEvent: "input.type" }));

describe("EditorPane", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows an empty state while no file is open", () => {
    const { session } = setup();
    render(<EditorPane session={session} />);
    expect(screen.getByText("No file open")).toBeInTheDocument();
  });

  it("shows the file name, its text and the saved state", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(viewOf(container).state.doc.toString()).toBe("hello");
  });

  it("goes from unsaved to saving to saved and writes the file on disk after the idle period", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    typeIn(viewOf(container), " world");
    expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
    expect(fake.disk("main.tex")?.content).toBe("hello");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(fake.disk("main.tex")?.content).toBe("hello world");
  });

  it("saves at once with the save shortcut", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    const view = viewOf(container);
    typeIn(view, "!");
    await act(async () => {
      fireEvent.keyDown(view.contentDOM, { key: "s", ctrlKey: true });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fake.disk("main.tex")?.content).toBe("hello!");
  });

  it("explains a failed save, keeps the text and retries on request", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    fake.failNext(apiError("io", "The disk is full.", 500));
    typeIn(viewOf(container), " more");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Not saved: The disk is full.");
    expect(viewOf(container).state.doc.toString()).toBe("hello more");

    await user.click(screen.getByRole("button", { name: "Save again" }));
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(fake.disk("main.tex")?.content).toBe("hello more");
  });

  it("shows the conflict state when the file changed on disk, and keeps the text", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    fake.changeOnDisk("main.tex", "other");
    typeIn(viewOf(container), " mine");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_MS);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Conflict");
    expect(viewOf(container).state.doc.toString()).toBe("hello mine");
  });

  it("stays editable whatever else is running", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    const view = viewOf(container);
    expect(view.state.readOnly).toBe(false);
    expect(view.contentDOM.getAttribute("contenteditable")).toBe("true");
  });

  it("moves the cursor to the line a jump asks for, in the file it names", async () => {
    const { fake, session } = setup();
    fake.state.files.push({ path: "chapter.tex" as RelPath, kind: "file", size: 20 });
    fake.changeOnDisk("chapter.tex", "one\ntwo\nthree\nfour");
    const { container } = render(<EditorPane session={session} />);
    await act(async () => {
      session.open(await fake.api.readFile("chapter.tex"));
      session.setActive("chapter.tex");
      session.reveal("chapter.tex", 3);
    });
    expect(viewOf(container).state.selection.main.head).toBe("one\ntwo\n".length);
  });

  it("ignores a jump that names another file than the one shown", async () => {
    const { fake, session } = setup();
    const { container } = render(<EditorPane session={session} />);
    await openMain(session, fake.api);
    act(() => session.reveal("chapter.tex", 3));
    expect(viewOf(container).state.selection.main.head).toBe(0);
  });
});

describe("a paper whose end of document PaperSmith passed", () => {
  const MISPLACED = "\\begin{document}\nHi\n\\end{document}\n%% paper-writing block a begin sha256=" + "c".repeat(64) + "\nText\n%% paper-writing block a end\n";

  it("offers to move \\end{document} to the end, and does it", async () => {
    const fake = createFakeApi({ files: [{ path: "paper/main.tex" as RelPath, kind: "file", size: 1 }], contents: { "paper/main.tex": MISPLACED } });
    const session = new EditorSession({ api: fake.api });
    session.open(await fake.api.readFile("paper/main.tex"));
    session.setActive("paper/main.tex");
    render(<EditorPane session={session} />);
    expect(screen.getByRole("alert")).toHaveTextContent("after \\end{document}");
    await userEvent.click(screen.getByRole("button", { name: "Move \\end{document} to the end" }));
    expect(session.get("paper/main.tex")?.text.endsWith("%% paper-writing block a end\n\\end{document}\n")).toBe(true);
    expect(screen.queryByRole("button", { name: "Move \\end{document} to the end" })).toBeNull();
  });
});
