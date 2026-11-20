import type { RelPath } from "@caztor/core";
import { EditorView } from "@codemirror/view";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createFakeApi } from "../testing/fake-api.ts";
import { EditorPane } from "./EditorPane.tsx";
import { EditorSession } from "./session.ts";

async function setup(options: { dirty?: boolean } = {}) {
  const fake = createFakeApi({ files: [{ path: "main.tex" as RelPath, kind: "file", size: 5 }], contents: { "main.tex": "hello" } });
  const session = new EditorSession({ api: fake.api });
  const view = render(<EditorPane session={session} />);
  await act(async () => {
    session.open(await fake.api.readFile("main.tex"));
    session.setActive("main.tex");
  });
  if (options.dirty !== false) act(() => session.edit("main.tex", "my edit"));
  return { fake, session, container: view.container };
}

/** The disk changes and the server says so. */
async function changeOnDisk(fake: ReturnType<typeof createFakeApi>, session: EditorSession, text: string) {
  const hash = fake.changeOnDisk("main.tex", text);
  await act(async () => {
    await session.handleEvent({ id: 1, event: "file_changed", data: { path: "main.tex", hash } });
  });
}

const editorViews = (container: HTMLElement) =>
  [...container.querySelectorAll<HTMLElement>(".cm-editor")].map((dom) => EditorView.findFromDOM(dom)).filter((view): view is EditorView => view !== null);

describe("EditorPane external changes", () => {
  it("shows new content from disk in a clean buffer without any prompt", async () => {
    const { fake, session, container } = await setup({ dirty: false });
    await changeOnDisk(fake, session, "written by the agent");
    expect(editorViews(container)[0]?.state.doc.toString()).toBe("written by the agent");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("asks what to do when the disk changed under unsaved edits, and keeps the user's text", async () => {
    const { fake, session, container } = await setup();
    await changeOnDisk(fake, session, "their edit");
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("main.tex changed on disk while you have unsaved changes.");
    expect(banner).toHaveTextContent("Autosave is paused until you choose.");
    for (const name of ["Keep mine", "Load disk version", "Save a copy", "Compare"]) {
      expect(within(banner).getByRole("button", { name })).toBeEnabled();
    }
    expect(screen.getByRole("status")).toHaveTextContent("Conflict");
    expect(editorViews(container)[0]?.state.doc.toString()).toBe("my edit");
  });

  it("keeps the editor editable during the conflict", async () => {
    const { fake, session, container } = await setup();
    await changeOnDisk(fake, session, "their edit");
    expect(editorViews(container)[0]?.state.readOnly).toBe(false);
  });

  it("Keep mine saves the user's text and closes the banner", async () => {
    const user = userEvent.setup();
    const { fake, session } = await setup();
    await changeOnDisk(fake, session, "their edit");
    await user.click(screen.getByRole("button", { name: "Keep mine" }));
    expect(fake.disk("main.tex")?.content).toBe("my edit");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("Load disk version shows the disk text and closes the banner", async () => {
    const user = userEvent.setup();
    const { fake, session, container } = await setup();
    await changeOnDisk(fake, session, "their edit");
    await user.click(screen.getByRole("button", { name: "Load disk version" }));
    expect(editorViews(container)[0]?.state.doc.toString()).toBe("their edit");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Save a copy writes the user's text to a new file, says where, and keeps the choice open", async () => {
    const user = userEvent.setup();
    const { fake, session } = await setup();
    await changeOnDisk(fake, session, "their edit");
    await user.click(screen.getByRole("button", { name: "Save a copy" }));
    expect(fake.disk("main-copy.tex")?.content).toBe("my edit");
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Your version was saved as main-copy.tex.");
    expect(within(banner).getByRole("button", { name: "Load disk version" })).toBeEnabled();
  });

  it("Compare shows the disk version and the user's version side by side, and hides again", async () => {
    const user = userEvent.setup();
    const { fake, session, container } = await setup();
    await changeOnDisk(fake, session, "their edit");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    expect(screen.getByText("Disk version")).toBeInTheDocument();
    expect(screen.getByText("Your version")).toBeInTheDocument();
    const texts = editorViews(container).map((view) => view.state.doc.toString());
    expect(texts).toEqual(["their edit", "my edit"]);
    expect(editorViews(container).every((view) => view.state.readOnly || !view.contentDOM.isContentEditable)).toBe(true);

    await user.click(screen.getByRole("button", { name: "Hide comparison" }));
    expect(screen.queryByText("Disk version")).toBeNull();
    expect(editorViews(container)).toHaveLength(1);
  });

  it("leaves the comparison once the conflict is resolved", async () => {
    const user = userEvent.setup();
    const { fake, session, container } = await setup();
    await changeOnDisk(fake, session, "their edit");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await user.click(screen.getByRole("button", { name: "Keep mine" }));
    expect(screen.queryByText("Disk version")).toBeNull();
    expect(editorViews(container)).toHaveLength(1);
  });

  it("explains a deletion and offers to recreate the file or close it", async () => {
    const user = userEvent.setup();
    const { fake, session } = await setup();
    fake.removeFromDisk("main.tex");
    await act(async () => {
      await session.handleEvent({ id: 1, event: "file_changed", data: { path: "main.tex", hash: null } });
    });
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("main.tex was deleted on disk while you have unsaved changes.");
    expect(within(banner).queryByRole("button", { name: "Compare" })).toBeNull();
    await user.click(within(banner).getByRole("button", { name: "Keep mine" }));
    expect(fake.disk("main.tex")?.content).toBe("my edit");
  });

  it("shows a problem from resolving inside the banner", async () => {
    const user = userEvent.setup();
    const { fake, session } = await setup();
    await changeOnDisk(fake, session, "their edit");
    const { apiError } = await import("../testing/fake-api.ts");
    fake.failNext(apiError("io", "The disk is full.", 500));
    await user.click(screen.getByRole("button", { name: "Save a copy" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The disk is full.");
  });
});
