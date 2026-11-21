import { language } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CodeEditor } from "./CodeEditor.tsx";

function viewOf(container: HTMLElement): EditorView {
  const dom = container.querySelector<HTMLElement>(".cm-editor");
  const view = dom === null ? null : EditorView.findFromDOM(dom);
  if (view === null) throw new Error("The editor view was not rendered");
  return view;
}

/** Types in the view the way the keyboard would: a user-event transaction at the cursor. */
function type(view: EditorView, text: string): void {
  const at = view.state.selection.main.head;
  view.dispatch({ changes: { from: at, insert: text }, selection: { anchor: at + text.length }, userEvent: "input.type" });
}

describe("CodeEditor", () => {
  it("shows the text with line numbers and an accessible name", () => {
    const { container } = render(<CodeEditor path="main.tex" text={"first\nsecond"} label="main.tex" onChange={() => {}} />);
    expect(screen.getByRole("textbox", { name: "main.tex" })).toBeInTheDocument();
    expect(container.querySelector(".cm-lineNumbers")).not.toBeNull();
    expect(viewOf(container).state.doc.toString()).toBe("first\nsecond");
  });

  it("is always editable and reports each edit with the whole new text", () => {
    const onChange = vi.fn();
    const { container } = render(<CodeEditor path="main.tex" text="abc" label="main.tex" onChange={onChange} />);
    const view = viewOf(container);
    expect(view.state.readOnly).toBe(false);
    expect(view.contentDOM.getAttribute("contenteditable")).toBe("true");
    type(view, "X");
    expect(onChange).toHaveBeenLastCalledWith("Xabc");
    type(view, "Y");
    expect(onChange).toHaveBeenLastCalledWith("XYabc");
  });

  it("picks the language from the file extension", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text="" label="a" onChange={() => {}} />);
    expect(viewOf(container).state.facet(language)?.name).toBe("stex");
    rerender(<CodeEditor path="refs.bib" text="" label="a" onChange={() => {}} />);
    expect(viewOf(container).state.facet(language)?.name).toBe("bibtex");
    rerender(<CodeEditor path="notes.txt" text="" label="a" onChange={() => {}} />);
    expect(viewOf(container).state.facet(language)).toBeNull();
  });

  it("shows new text from outside without reporting it as an edit, keeping the cursor", () => {
    const onChange = vi.fn();
    const { container, rerender } = render(<CodeEditor path="main.tex" text="alpha beta gamma" label="a" onChange={onChange} />);
    const view = viewOf(container);
    view.dispatch({ selection: { anchor: 13 } });
    rerender(<CodeEditor path="main.tex" text="alpha BETA2 gamma" label="a" onChange={onChange} />);
    expect(view.state.doc.toString()).toBe("alpha BETA2 gamma");
    // The cursor was after the changed word, so it moves by the length difference and stays on "gamma".
    expect(view.state.selection.main.head).toBe(14);
    expect(onChange).not.toHaveBeenCalled();
    rerender(<CodeEditor path="main.tex" text="ALPHA BETA2 gamma" label="a" onChange={onChange} />);
    expect(view.state.selection.main.head).toBe(14);
  });

  it("keeps a cursor placed before the changed part where it was", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text="one two three" label="a" onChange={() => {}} />);
    const view = viewOf(container);
    view.dispatch({ selection: { anchor: 2 } });
    rerender(<CodeEditor path="main.tex" text="one two THREE and more" label="a" onChange={() => {}} />);
    expect(view.state.selection.main.head).toBe(2);
  });

  it("keeps the scroll position when the text is replaced from outside", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text={"line\n".repeat(200)} label="a" onChange={() => {}} />);
    const view = viewOf(container);
    view.scrollDOM.scrollTop = 420;
    rerender(<CodeEditor path="main.tex" text={`${"line\n".repeat(199)}changed`} label="a" onChange={() => {}} />);
    expect(view.scrollDOM.scrollTop).toBe(420);
  });

  it("restores the cursor of a file when switching back to it, and shows the text it is given", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text="alpha beta" label="a" onChange={() => {}} />);
    const view = viewOf(container);
    view.dispatch({ selection: { anchor: 6 } });
    rerender(<CodeEditor path="refs.bib" text="@book{k}" label="a" onChange={() => {}} />);
    expect(view.state.doc.toString()).toBe("@book{k}");
    expect(view.state.selection.main.head).toBe(0);
    rerender(<CodeEditor path="main.tex" text="alpha beta" label="a" onChange={() => {}} />);
    expect(view.state.doc.toString()).toBe("alpha beta");
    expect(view.state.selection.main.head).toBe(6);
  });

  it("starts from the given text, not the remembered one, when the file changed while it was away", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text="old text" label="a" onChange={() => {}} />);
    const view = viewOf(container);
    rerender(<CodeEditor path="refs.bib" text="x" label="a" onChange={() => {}} />);
    rerender(<CodeEditor path="main.tex" text="new text from disk" label="a" onChange={() => {}} />);
    expect(view.state.doc.toString()).toBe("new text from disk");
  });

  it("does not report a file switch as an edit", () => {
    const onChange = vi.fn();
    const { rerender } = render(<CodeEditor path="main.tex" text="a" label="a" onChange={onChange} />);
    rerender(<CodeEditor path="refs.bib" text="b" label="a" onChange={onChange} />);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes the view when unmounted", () => {
    const { container, unmount } = render(<CodeEditor path="main.tex" text="a" label="a" onChange={() => {}} />);
    act(() => unmount());
    expect(container.querySelector(".cm-editor")).toBeNull();
  });

  describe("revealing a line", () => {
    const text = "line one\nline two\nline three\nline four";
    const show = (reveal?: { line: number; id: number }) => (
      <CodeEditor path="main.tex" text={text} label="a" onChange={() => {}} {...(reveal === undefined ? {} : { reveal })} />
    );

    it("puts the cursor at the start of the requested line (1-based) and focuses the editor", () => {
      const { container, rerender } = render(show());
      const view = viewOf(container);
      rerender(show({ line: 3, id: 1 }));
      expect(view.state.selection.main.head).toBe(text.indexOf("line three"));
      expect(view.state.selection.main.empty).toBe(true);
      expect(view.hasFocus).toBe(true);
    });

    it("moves to another line for a new request, and again for the same line with a new id", () => {
      const { container, rerender } = render(show({ line: 2, id: 1 }));
      const view = viewOf(container);
      expect(view.state.selection.main.head).toBe(text.indexOf("line two"));
      rerender(show({ line: 4, id: 2 }));
      expect(view.state.selection.main.head).toBe(text.indexOf("line four"));
      view.dispatch({ selection: { anchor: 0 } });
      rerender(show({ line: 4, id: 3 }));
      expect(view.state.selection.main.head).toBe(text.indexOf("line four"));
    });

    it("does not jump again when the same request is still passed after the user moved the cursor", () => {
      const { container, rerender } = render(show({ line: 3, id: 1 }));
      const view = viewOf(container);
      view.dispatch({ selection: { anchor: 2 } });
      rerender(show({ line: 3, id: 1 }));
      expect(view.state.selection.main.head).toBe(2);
    });

    it("clamps a line beyond the end of the file to the last line, and a line below 1 to the first", () => {
      const { container, rerender } = render(show());
      const view = viewOf(container);
      rerender(show({ line: 99, id: 1 }));
      expect(view.state.selection.main.head).toBe(text.indexOf("line four"));
      rerender(show({ line: 0, id: 2 }));
      expect(view.state.selection.main.head).toBe(0);
    });

    it("applies a request that comes with the file it belongs to, after that file's text is shown", () => {
      const { container, rerender } = render(<CodeEditor path="a.tex" text="a1\na2" label="a" onChange={() => {}} />);
      rerender(<CodeEditor path="b.tex" text={"b1\nb2\nb3"} label="b" onChange={() => {}} reveal={{ line: 3, id: 1 }} />);
      expect(viewOf(container).state.doc.toString()).toBe("b1\nb2\nb3");
      expect(viewOf(container).state.selection.main.head).toBe("b1\nb2\n".length);
    });
  });
});

describe("CodeEditor stepping to an explained passage", () => {
  const text = "Intro.\n" + "filler line\n".repeat(80) + "Each colour class is updated in parallel without conflicts.\nEnd.";
  const passage = "each colour class is updated in parallel without conflicts";
  const current = (container: HTMLElement) => [...container.querySelectorAll(".cm-explained-current")].map((element) => element.textContent).join("");

  it("marks the passage more strongly on a step, and moves the mark on the next step", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[passage]} focus={{ passage, nonce: 1 }} />);
    expect(current(container)).toBe("Each colour class is updated in parallel without conflicts");
    rerender(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[passage, "intro"]} focus={{ passage: "nothing like this anywhere", nonce: 2 }} />);
    expect(container.querySelector(".cm-explained-current")).toBeNull();
  });

  it("removes the stronger mark when highlighting is turned off", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[passage]} focus={{ passage, nonce: 1 }} />);
    expect(current(container)).toBe("Each colour class is updated in parallel without conflicts");
    rerender(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[]} focus={null} />);
    expect(container.querySelector(".cm-explained-current")).toBeNull();
    expect(container.querySelector(".cm-explained")).toBeNull();
  });

  it("marks nothing more strongly without a step", () => {
    const { container } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[passage]} />);
    expect(container.querySelector(".cm-explained-current")).toBeNull();
  });
});

describe("CodeEditor explained passages", () => {
  const text = "Intro.\nEach colour class is updated in parallel without conflicts.\nEnd.";
  const passage = ["each colour class is updated in parallel without conflicts"];
  const marked = (container: HTMLElement) => [...container.querySelectorAll(".cm-explained")].map((element) => element.textContent).join("");

  it("marks the passages it is given, follows new ones, and removes the marks when given none", () => {
    const { container, rerender } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={passage} />);
    expect(marked(container)).toBe("Each colour class is updated in parallel without conflicts");
    rerender(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={[]} />);
    expect(container.querySelector(".cm-explained")).toBeNull();
  });

  it("marks nothing without the prop, as before", () => {
    const { container } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} />);
    expect(container.querySelector(".cm-explained")).toBeNull();
  });

  it("finds the passage again in a file opened later", () => {
    const { container, rerender } = render(<CodeEditor path="a.tex" text="nothing here" label="a.tex" onChange={() => {}} highlights={passage} />);
    expect(container.querySelector(".cm-explained")).toBeNull();
    rerender(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} highlights={passage} />);
    expect(marked(container)).toContain("Each colour class");
  });
});

describe("CodeEditor double click", () => {
  it("names the texts around the clicked word for the PDF to find", () => {
    const text = "Intro.\nClassical spin models describe how magnetic order emerges from the interactions between localized moments.\nEnd.";
    const asked: string[][] = [];
    const { container } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} onJumpToPdf={(candidates) => asked.push([...candidates])} />);
    const view = viewOf(container);
    const at = text.indexOf("emerges");
    act(() => view.dispatch({ selection: { anchor: at, head: at + "emerges".length } }));
    view.contentDOM.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    expect(asked).toEqual([
      ["spin models describe how magnetic order emerges from the interactions between localized moments.", "Classical spin models describe how magnetic order emerges from the interactions between localized moments."],
    ]);
  });

  it("asks nothing on a comment line", () => {
    const text = "% a note to myself about the introduction\nBody.";
    const asked: string[][] = [];
    const { container } = render(<CodeEditor path="main.tex" text={text} label="main.tex" onChange={() => {}} onJumpToPdf={(candidates) => asked.push([...candidates])} />);
    viewOf(container).contentDOM.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    expect(asked).toEqual([]);
  });
});
