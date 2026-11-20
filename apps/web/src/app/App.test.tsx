import type { RelPath } from "@caztor/core";
import { EditorView } from "@codemirror/view";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createLayoutStore } from "../layout/storage.ts";
import type { Settings } from "../api/types.ts";
import { AUTOSAVE_MS } from "../editor/session.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { fakeDocument, fakeEngine, type FakeDocument } from "../testing/fake-pdf.ts";
import { App } from "./App.tsx";

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const layoutStore = () => createLayoutStore(window.localStorage);

describe("App with several projects", () => {
  const projects = [
    { path: "/p/a", name: "a", kind: "folder" as const, active: true },
    { path: "/p/b", name: "b", kind: "papersmith" as const, active: false },
  ];

  it("saves open edits, moves the server, and reloads the page", async () => {
    const fake = createFakeApi({ projects, files: [{ path: "main.tex" as RelPath, kind: "file", size: 1 }], contents: { "main.tex": "x" } });
    const reloadPage = vi.fn();
    render(<App api={fake.api} layoutStore={layoutStore()} reloadPage={reloadPage} />);
    await userEvent.click(await screen.findByRole("button", { name: /^b/ }));
    await waitFor(() => expect(reloadPage).toHaveBeenCalledTimes(1));
    expect(fake.calls).toContain("openProject /p/b");
  });

  it("saves open edits, creates the project, and reloads the page", async () => {
    const fake = createFakeApi({ projects, settings: { disclosureAcknowledged: true } });
    const reloadPage = vi.fn();
    render(<App api={fake.api} layoutStore={layoutStore()} reloadPage={reloadPage} />);
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Project name" }), { target: { value: "thesis" } });
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(reloadPage).toHaveBeenCalledTimes(1));
    expect(fake.calls).toContain("createProject thesis");
  });

  it("stays and explains when the server refuses", async () => {
    const fake = createFakeApi({ projects, openProjectError: "Stop the running turn before opening another project." });
    const reloadPage = vi.fn();
    render(<App api={fake.api} layoutStore={layoutStore()} reloadPage={reloadPage} />);
    await userEvent.click(await screen.findByRole("button", { name: /^b/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stop the running turn");
    expect(reloadPage).not.toHaveBeenCalled();
  });

  it("reloads when another page moved the server to a different project", async () => {
    const fake = createFakeApi({ projects });
    const reloadPage = vi.fn();
    render(<App api={fake.api} layoutStore={layoutStore()} reloadPage={reloadPage} />);
    await screen.findByRole("button", { name: /^b/ });
    act(() => fake.emit({ id: null, event: "project_changed", data: { name: "b" } }));
    expect(reloadPage).toHaveBeenCalledTimes(1);
  });
});

describe("App in a PaperSmith workspace", () => {
  const files = [{ path: "paper" as RelPath, kind: "dir" as const, size: 0 }, { path: "paper/main.tex" as RelPath, kind: "file" as const, size: 5 }];

  it("opens the main file at once", async () => {
    const fake = createFakeApi({ files, contents: { "paper/main.tex": "hello" }, papersmith: { main: "paper/main.tex", exists: true } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    expect(await screen.findByRole("textbox", { name: "paper/main.tex" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /main\.tex/ })).toBeNull();
  });

  it("asks before creating a missing main file, creates it the PaperSmith way, and opens it", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true }, papersmith: { main: "paper/main.tex", exists: false } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    const dialog = await screen.findByRole("dialog", { name: "Create paper/main.tex?" });
    expect(dialog).toHaveTextContent("PaperSmith");
    expect(fake.calls).not.toContain("scaffoldPaper");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(fake.calls).toContain("scaffoldPaper"));
    expect(await screen.findByRole("textbox", { name: "paper/main.tex" })).toBeInTheDocument();
    await waitFor(() => expect(fake.calls.filter((call) => call === "listProjects")).toHaveLength(2));
  });

  it("creates nothing when the user declines", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true }, papersmith: { main: "paper/main.tex", exists: false } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Create paper/main.tex?" })).getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fake.calls).not.toContain("scaffoldPaper");
  });

  it("does not ask in a plain project", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    await screen.findByRole("navigation", { name: "Projects" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("App", () => {
  it("shows the project name and the four panes once the session loads", async () => {
    const fake = createFakeApi({ projectName: "thesis" });
    render(<App api={fake.api} layoutStore={layoutStore()} />);

    expect(screen.getByRole("status")).toHaveTextContent("Opening project");
    expect(await screen.findByText("thesis")).toBeInTheDocument();
    expect(screen.getAllByRole("region").map((region) => region.getAttribute("aria-label"))).toEqual(["Files", "LaTeX editor", "PDF preview", "Chat"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("puts the chat in its own pane, apart from the editor, and loads its conversation", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ files: [{ path: "main.tex" as RelPath, kind: "file", size: 24 }], contents: { "main.tex": "\\documentclass{article}" } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);

    const chat = within(await screen.findByRole("region", { name: "Chat" }));
    expect(await chat.findByRole("textbox", { name: "Message to the assistant" })).toBeEnabled();
    expect(fake.calls).toContain("chatHistory claude");
    // jsdom has no layout, so the pane library treats every click as a hit on a divider and takes focus; focus the box directly.
    act(() => chat.getByRole("textbox", { name: "Message to the assistant" }).focus());
    await user.keyboard("Hello{Enter}");
    await waitFor(() => expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "Hello" }]));
    // The editor pane is not part of the chat and stays usable while the turn runs.
    const tree = within(screen.getByRole("region", { name: "Files" }));
    await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
    const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
    expect(await editor.findByRole("textbox", { name: "main.tex" })).toHaveTextContent("documentclass");
    expect(chat.queryByRole("textbox", { name: "main.tex" })).toBeNull();
  });

  it("lists the project files in the file pane and opens one into the editor pane", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({
      files: [{ path: "main.tex" as RelPath, kind: "file", size: 24 }],
      contents: { "main.tex": "\\documentclass{article}" },
    });
    render(<App api={fake.api} layoutStore={layoutStore()} />);

    const tree = within(await screen.findByRole("region", { name: "Files" }));
    await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
    const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
    expect(await editor.findByText("main.tex")).toBeInTheDocument();
    expect(editor.getByRole("textbox", { name: "main.tex" })).toHaveTextContent("\\documentclass{article}");
  });

  it("follows the open file when it is renamed", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }], contents: { "main.tex": "hello" } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    const tree = within(await screen.findByRole("region", { name: "Files" }));
    await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
    const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
    expect(await editor.findByText("main.tex")).toBeInTheDocument();

    await user.click(tree.getByRole("button", { name: "Rename main.tex" }));
    const input = tree.getByRole("textbox", { name: "New name for main.tex" });
    // jsdom does no layout, so a pointer click next to a divider hands focus to it; focus the box by script.
    act(() => input.focus());
    await user.keyboard("{Control>}a{/Control}thesis.tex{Enter}");
    expect(await editor.findByText("thesis.tex")).toBeInTheDocument();
  });

  it("closes the open file in the editor pane when it is deleted", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }], contents: { "main.tex": "hello" } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    const tree = within(await screen.findByRole("region", { name: "Files" }));
    await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
    const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
    expect(await editor.findByRole("textbox", { name: "main.tex" })).toBeInTheDocument();

    await user.click(tree.getByRole("button", { name: "Delete main.tex" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await editor.findByText("No file open")).toBeInTheDocument();
  });

  it("shows the disclosure notice when it was not acknowledged for this project", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: false } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    expect(await screen.findByRole("dialog", { name: "Before you start" })).toBeInTheDocument();
  });

  it("saves the acknowledgement through the settings and does not show the notice again on reopen", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ settings: { disclosureAcknowledged: false } });
    const first = render(<App api={fake.api} layoutStore={layoutStore()} />);

    await user.click(await screen.findByRole("button", { name: "I understand" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fake.calls).toContain('patchSettings {"disclosureAcknowledged":true}');
    expect(fake.state.settings.disclosureAcknowledged).toBe(true);

    first.unmount();
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    expect(await screen.findByText("thesis")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the notice open when the acknowledgement cannot be saved", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi({ settings: { disclosureAcknowledged: false } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    const button = await screen.findByRole("button", { name: "I understand" });
    fake.failNext(apiError("io", "The settings could not be saved.", 500));

    await user.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("The settings could not be saved.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("explains a failed load and retries on request", async () => {
    const user = userEvent.setup();
    const fake = createFakeApi();
    fake.failAll(apiError("network", "Cannot reach the Caztor server. Check that it is still running.", 0));
    render(<App api={fake.api} layoutStore={layoutStore()} />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Cannot reach the Caztor server. Check that it is still running.")).toBeInTheDocument();
    fake.recover();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("thesis")).toBeInTheDocument();
  });

  describe("editing", () => {
    const project = () =>
      createFakeApi({
        files: [
          { path: "main.tex" as RelPath, kind: "file", size: 5 },
          { path: "refs.bib" as RelPath, kind: "file", size: 8 },
        ],
        contents: { "main.tex": "hello", "refs.bib": "@book{k}" },
      });

    const typeInEditor = (text: string) => {
      const dom = within(screen.getByRole("region", { name: "LaTeX editor" })).getByRole("textbox").closest<HTMLElement>(".cm-editor");
      const view = dom === null ? null : EditorView.findFromDOM(dom);
      if (view === null) throw new Error("no editor view");
      act(() => view.dispatch({ changes: { from: view.state.doc.length, insert: text }, userEvent: "input.type" }));
    };

    it("keeps the unsaved edits of a file when another one is opened, saves them, and shows them again", async () => {
      const user = userEvent.setup();
      const fake = project();
      render(<App api={fake.api} layoutStore={layoutStore()} />);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });
      typeInEditor(" draft");

      await user.click(tree.getByRole("button", { name: /^refs\.bib/ }));
      const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
      expect(await editor.findByRole("textbox", { name: "refs.bib" })).toHaveTextContent("@book{k}");
      await waitFor(() => expect(fake.disk("main.tex")?.content).toBe("hello draft"), { timeout: 3000 });

      await user.click(tree.getByRole("button", { name: /^main\.tex/ }));
      expect(await editor.findByRole("textbox", { name: "main.tex" })).toHaveTextContent("hello draft");
    });

    it("asks the browser to confirm leaving the page while an edit is not saved, and not otherwise", async () => {
      const user = userEvent.setup();
      const fake = project();
      render(<App api={fake.api} layoutStore={layoutStore()} />);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });

      const leave = () => {
        const event = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(event);
        return event.defaultPrevented;
      };
      expect(leave()).toBe(false);
      typeInEditor("!");
      expect(leave()).toBe(true);
      await waitFor(() => expect(fake.disk("main.tex")?.content).toBe("hello!"), { timeout: 3000 });
      await waitFor(() => expect(leave()).toBe(false));
    });

    it("follows a rename with the unsaved text and saves it under the new name", async () => {
      const user = userEvent.setup();
      const fake = project();
      render(<App api={fake.api} layoutStore={layoutStore()} />);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });
      await user.click(tree.getByRole("button", { name: "Rename main.tex" }));
      const input = tree.getByRole("textbox", { name: "New name for main.tex" });
      act(() => input.focus());
      await user.keyboard("{Control>}a{/Control}thesis.tex{Enter}");
      const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
      expect(await editor.findByRole("textbox", { name: "thesis.tex" })).toHaveTextContent("hello");
      typeInEditor(" more");
      await waitFor(() => expect(fake.disk("thesis.tex")?.content).toBe("hello more"), { timeout: 3000 });
    });

    it("reloads an open clean file when the server reports a change, and asks about a file with unsaved edits", async () => {
      const user = userEvent.setup();
      const fake = project();
      render(<App api={fake.api} layoutStore={layoutStore()} />);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      const editor = within(screen.getByRole("region", { name: "LaTeX editor" }));
      const box = await editor.findByRole("textbox", { name: "main.tex" });
      expect(box).toHaveTextContent("hello");

      const hash = fake.changeOnDisk("main.tex", "rewritten by the agent");
      act(() => fake.emit({ id: 1, event: "file_changed", data: { path: "main.tex", hash } }));
      await waitFor(() => expect(box).toHaveTextContent("rewritten by the agent"));
      expect(screen.queryByText(/changed on disk while you have unsaved changes/)).toBeNull();

      typeInEditor(" +mine");
      const second = fake.changeOnDisk("main.tex", "rewritten again");
      act(() => fake.emit({ id: 2, event: "file_changed", data: { path: "main.tex", hash: second } }));
      expect(await screen.findByText(/changed on disk while you have unsaved changes/)).toBeInTheDocument();
      expect(box).toHaveTextContent("rewritten by the agent +mine");
    });

    it("checks the open files again when the event stream reconnects", async () => {
      const user = userEvent.setup();
      const fake = project();
      render(<App api={fake.api} layoutStore={layoutStore()} />);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      const box = await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });
      fake.changeOnDisk("main.tex", "changed while offline");
      act(() => fake.emit({ id: null, event: "stream_resumed", data: null }));
      await waitFor(() => expect(box).toHaveTextContent("changed while offline"));
    });
  });

  describe("compiling", () => {
    const project = (settings: Partial<Settings> = {}, extra: Parameters<typeof createFakeApi>[0] = {}) =>
      createFakeApi({
        files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }],
        contents: { "main.tex": "hello" },
        settings,
        ...extra,
      });
    const preview = () => within(screen.getByRole("region", { name: "PDF preview" }));
    const ready = () => screen.findByRole("region", { name: "PDF preview" });
    const renderApp = (fake: ReturnType<typeof createFakeApi>, documents: FakeDocument[] = [fakeDocument("v1", 3)]) => {
      const engine = fakeEngine(...documents);
      render(<App api={fake.api} layoutStore={layoutStore()} previewStorage={null} pdfEngine={engine} />);
      return engine;
    };

    it("starts a compile from the button, shows it running and ends with the PDF on screen", async () => {
      const user = userEvent.setup();
      const fake = project();
      fake.compile.pdf = new Uint8Array([1, 2, 3]);
      const engine = renderApp(fake);
      await ready();
      await user.click(await preview().findByRole("button", { name: "Compile" }));
      expect(fake.calls).toContain("startCompile");
      expect(await preview().findByRole("button", { name: "Cancel" })).toBeInTheDocument();
      act(() => fake.compile.phase("typesetting"));
      expect(preview().getByText("Compiling")).toBeInTheDocument();
      act(() => fake.compile.finish({ pdfRev: "4" }));
      await waitFor(() => expect(preview().getByRole("button", { name: "Compile" })).toBeInTheDocument());
      await waitFor(() => expect(engine.opened).toHaveLength(1));
      expect(fake.calls).toContain("readPdf 4");
      expect(await screen.findByRole("region", { name: "PDF pages" })).toBeInTheDocument();
    });

    it("cancels the running compile", async () => {
      const user = userEvent.setup();
      const fake = project();
      renderApp(fake);
      await ready();
      await user.click(await preview().findByRole("button", { name: "Compile" }));
      await user.click(await preview().findByRole("button", { name: "Cancel" }));
      expect(fake.calls).toContain("cancelCompile");
      expect(await preview().findByRole("button", { name: "Compile" })).toBeInTheDocument();
      expect(preview().getByText("Compile cancelled")).toBeInTheDocument();
    });

    it("shows the preview that exists from an earlier run of the server without compiling", async () => {
      const fake = project({}, { pdf: new Uint8Array([1]) });
      renderApp(fake);
      await waitFor(() => expect(fake.calls).toContain("readPdf current"));
      expect(await screen.findByRole("region", { name: "PDF pages" })).toBeInTheDocument();
    });

    it("tells the user the engine is missing, with what to do, and does not offer a working Compile", async () => {
      const fake = project({}, { engineAvailable: false });
      renderApp(fake);
      await ready();
      expect(await preview().findByRole("alert")).toHaveTextContent(/Tectonic.*not found.*Install Tectonic/);
      expect(preview().getByRole("button", { name: "Compile" })).toBeDisabled();
    });

    it("shows why the engine is unavailable when the server says so", async () => {
      const fake = project({}, { engineAvailable: false, engineReason: "Tectonic was found but failed to run (exit code 2): error: cannot open the cache" });
      renderApp(fake);
      await ready();
      const notice = await preview().findByRole("alert");
      expect(notice).toHaveTextContent(/Install Tectonic/);
      expect(notice).toHaveTextContent("Tectonic was found but failed to run (exit code 2): error: cannot open the cache");
    });

    it("opens the file of a clicked error in the editor with the cursor on its line", async () => {
      const user = userEvent.setup();
      const fake = createFakeApi({
        files: [
          { path: "main.tex" as RelPath, kind: "file", size: 5 },
          { path: "chapter.tex" as RelPath, kind: "file", size: 30 },
        ],
        contents: { "main.tex": "hello", "chapter.tex": "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight" },
      });
      renderApp(fake);
      await ready();
      await user.click(await preview().findByRole("button", { name: "Compile" }));
      act(() =>
        fake.compile.finish({
          status: "failed-with-errors",
          pdfRev: null,
          diagnostics: [{ severity: "error", file: "chapter.tex" as RelPath, line: 7, message: "Undefined control sequence", source: "stderr" }],
        }),
      );
      await user.click(await preview().findByRole("button", { name: "Go to chapter.tex line 7" }));
      const box = await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "chapter.tex" });
      const view = EditorView.findFromDOM(box.closest<HTMLElement>(".cm-editor")!)!;
      await waitFor(() => expect(view.state.selection.main.head).toBe("one\ntwo\nthree\nfour\nfive\nsix\n".length));
    });

    it("keeps the unsaved text of a file that is already open when its error is clicked", async () => {
      const user = userEvent.setup();
      const fake = createFakeApi({ files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }], contents: { "main.tex": "a\nb\nc" } });
      renderApp(fake);
      const tree = within(await screen.findByRole("region", { name: "Files" }));
      await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
      await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });
      await user.click(await preview().findByRole("button", { name: "Compile" }));
      act(() =>
        fake.compile.finish({
          status: "failed-with-errors",
          pdfRev: null,
          diagnostics: [{ severity: "error", file: "main.tex" as RelPath, line: 3, message: "Bad", source: "stderr" }],
        }),
      );
      fake.calls.length = 0;
      await user.click(await preview().findByRole("button", { name: "Go to main.tex line 3" }));
      expect(fake.calls.filter((call) => call.startsWith("readFile"))).toEqual([]);
      const view = EditorView.findFromDOM(screen.getByRole("textbox", { name: "main.tex" }).closest<HTMLElement>(".cm-editor")!)!;
      await waitFor(() => expect(view.state.selection.main.head).toBe("a\nb\n".length));
    });

    it("tells the user when the file of an error cannot be opened", async () => {
      const user = userEvent.setup();
      const fake = project();
      renderApp(fake);
      await ready();
      await user.click(await preview().findByRole("button", { name: "Compile" }));
      act(() =>
        fake.compile.finish({
          status: "failed-with-errors",
          pdfRev: null,
          diagnostics: [{ severity: "error", file: "gone.tex" as RelPath, line: 2, message: "Bad", source: "stderr" }],
        }),
      );
      await user.click(await preview().findByRole("button", { name: "Go to gone.tex line 2" }));
      expect(await preview().findByRole("alert")).toHaveTextContent('"gone.tex" was not found.');
    });

    describe("auto-compile", () => {
      const editAndSave = async (fake: ReturnType<typeof createFakeApi>) => {
        const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
        const tree = within(await screen.findByRole("region", { name: "Files" }));
        await user.click(await tree.findByRole("button", { name: /^main\.tex/ }));
        await within(screen.getByRole("region", { name: "LaTeX editor" })).findByRole("textbox", { name: "main.tex" });
        const dom = screen.getByRole("textbox", { name: "main.tex" }).closest<HTMLElement>(".cm-editor");
        const view = dom === null ? null : EditorView.findFromDOM(dom);
        act(() => view!.dispatch({ changes: { from: view!.state.doc.length, insert: "!" }, userEvent: "input.type" }));
        await act(async () => void (await vi.advanceTimersByTimeAsync(AUTOSAVE_MS)));
        expect(fake.calls.some((call) => call.startsWith("writeFile main.tex"))).toBe(true);
      };

      beforeEach(() => void vi.useFakeTimers({ shouldAdvanceTime: true }));
      afterEach(() => void vi.useRealTimers());

      it("compiles 1.5 s after a successful save", async () => {
        const fake = project();
        renderApp(fake);
        await editAndSave(fake);
        expect(fake.compile.starts).toBe(0);
        await act(async () => void (await vi.advanceTimersByTimeAsync(1300)));
        expect(fake.compile.starts).toBe(0);
        await act(async () => void (await vi.advanceTimersByTimeAsync(400)));
        expect(fake.compile.starts).toBe(1);
      });

      it("does not compile after a save when auto-compile is switched off", async () => {
        const fake = project({ autoCompile: false });
        renderApp(fake);
        await editAndSave(fake);
        await act(async () => void (await vi.advanceTimersByTimeAsync(5000)));
        expect(fake.compile.starts).toBe(0);
      });
    });
  });
});

describe("App and who is signed in", () => {
  it("shows the host's name and a Collaborators dialog", async () => {
    const fake = createFakeApi({ user: { id: "host", name: "Host", role: "host" }, settings: { disclosureAcknowledged: true } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    expect(await screen.findByText("Host", { selector: ".app__user" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Collaborators" }));
    expect(await screen.findByRole("dialog", { name: "Collaborators" })).toBeInTheDocument();
    expect(fake.calls).toContain("listCollaborators");
  });

  it("shows a collaborator's name, no Collaborators button, and their own chat", async () => {
    const fake = createFakeApi({ user: { id: "u1", name: "Ana", role: "collaborator" }, settings: { disclosureAcknowledged: true } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    expect(await screen.findByText("Ana", { selector: ".app__user" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Collaborators" })).toBeNull();
    await waitFor(() => expect(fake.calls).toContain("listProviders"));
    expect(screen.queryByText(/Collaborator chat is not available yet/)).toBeNull();
  });

  it("keeps the header as before when the server names no user", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true } });
    const { container } = render(<App api={fake.api} layoutStore={layoutStore()} />);
    await screen.findByText("thesis");
    expect(container.querySelector(".app__user")).toBeNull();
    expect(screen.queryByRole("button", { name: "Collaborators" })).toBeNull();
    await waitFor(() => expect(fake.calls).toContain("listProviders"));
  });
});

describe("embedded in a PaperSmith dashboard", () => {
  const SMITH = "http://127.0.0.1:8765";

  it("shows no top bar, and takes its theme from the dashboard after saying it is ready", async () => {
    const post = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true }, embed: { origin: SMITH } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    await screen.findByRole("textbox", { name: "Message to the assistant" });
    expect(document.querySelector(".app__bar")).toBeNull();
    expect(screen.queryByRole("combobox", { name: /theme/i })).toBeNull();
    await waitFor(() => expect(post).toHaveBeenCalledWith({ type: "caztor:ready" }, SMITH));
    act(() => {
      window.dispatchEvent(new MessageEvent("message", { data: { type: "caztor:theme", theme: "dark" }, origin: SMITH, source: window.parent }));
    });
    expect(document.documentElement.dataset["theme"]).toBe("dark");
    act(() => {
      window.dispatchEvent(new MessageEvent("message", { data: { type: "caztor:theme", theme: "light" }, origin: SMITH, source: window.parent }));
    });
    expect(document.documentElement.dataset["theme"]).toBe("light");
    post.mockRestore();
  });

  it("hides the project navigator", async () => {
    const fake = createFakeApi({ settings: { disclosureAcknowledged: true }, embed: { origin: SMITH } });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    await screen.findByRole("textbox", { name: "Message to the assistant" });
    expect(screen.queryByRole("navigation", { name: "Projects" })).toBeNull();
    expect(fake.calls).not.toContain("listProjects");
  });

  it("puts the text the dashboard sends into the chat box, after what was typed", async () => {
    const fake = createFakeApi({
      settings: { disclosureAcknowledged: true },
      embed: { origin: SMITH },
      providers: { selected: "claude", providers: [{ id: "claude", installed: true, requiresModel: false, model: null }] },
    });
    render(<App api={fake.api} layoutStore={layoutStore()} />);
    const box = () => screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Message to the assistant" });
    await waitFor(() => expect(fake.calls).toContain("chatHistory claude"));
    fireEvent.change(box(), { target: { value: "Hello." } });
    await waitFor(() => expect(box().value).toBe("Hello."));
    act(() => {
      window.dispatchEvent(new MessageEvent("message", { data: { type: "caztor:compose", text: "Apply the annotations." }, origin: SMITH, source: window.parent }));
    });
    await waitFor(() => expect(box().value).toBe("Hello.\n\nApply the annotations."));
  });
});

describe("explained passages", () => {
  const files = [{ path: "paper" as RelPath, kind: "dir" as const, size: 0 }, { path: "paper/main.tex" as RelPath, kind: "file" as const, size: 80 }];
  const text = "Intro.\nEach colour class is updated in parallel without conflicts.\nEnd.";
  function withReply() {
    const fake = createFakeApi({
      settings: { disclosureAcknowledged: true },
      files,
      contents: { "paper/main.tex": text },
      papersmith: { main: "paper/main.tex", exists: true },
      providers: { selected: "claude", providers: [{ id: "claude", installed: true, requiresModel: false, model: null }] },
    });
    fake.chat.history.claude = {
      provider: "claude",
      turns: [
        {
          turnId: "t1",
          provider: "claude",
          prompt: "/math-tutor explain the update",
          startedAt: 1,
          events: [
            { type: "turn_started", turnId: "t1", provider: "claude", snapshotPartial: false, unprotected: [] },
            { type: "text", messageId: "m1", text: "The key sentence is `each colour class is updated in parallel without conflicts`." },
            { type: "done", reason: "completed" },
          ],
        },
      ],
      undoableTurnId: null,
      undoProblem: null,
      running: false,
      currentTurnId: null,
    };
    return fake;
  }

  afterEach(() => window.localStorage.removeItem("caztor.explain.v1"));

  it("marks in the editor the passage the last reply explains, and the chat's switch turns the marks off and on", async () => {
    const fake = withReply();
    const { container } = render(<App api={fake.api} layoutStore={layoutStore()} previewStorage={window.localStorage} />);
    const toggle = await screen.findByRole("button", { name: /highlight explained passages/i });
    await waitFor(() => expect(container.querySelector(".cm-explained")?.textContent).toContain("Each colour class"));
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(container.querySelector(".cm-explained")).toBeNull());
    expect(window.localStorage.getItem("caztor.explain.v1")).toBe("off");
    await userEvent.click(toggle);
    await waitFor(() => expect(container.querySelector(".cm-explained")).not.toBeNull());
  });
});

