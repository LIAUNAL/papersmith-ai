import { EditorView } from "@codemirror/view";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CodeEditor } from "./CodeEditor.tsx";

const BEGIN = `%% paper-writing block intro.lead begin sha256=${"a".repeat(64)}`;
const END = "%% paper-writing block intro.lead end";
const DOC = `\\documentclass{article}\n${BEGIN}\nSome text.\n${END}\n`;

function editor(path = "paper/main.tex", text = DOC) {
  const onChange = vi.fn();
  const view = render(<CodeEditor path={path} text={text} label={path} onChange={onChange} />);
  const element = view.container.querySelector(".cm-editor");
  const cm = element === null ? null : EditorView.findFromDOM(element as HTMLElement);
  if (cm === null) throw new Error("no editor");
  return { cm, onChange, view };
}
const lineStart = (cm: EditorView, text: string) => cm.state.doc.toString().indexOf(text);

describe("the block markers of PaperSmith in the editor", () => {
  it("cannot be typed into, deleted, or joined to the next line", () => {
    const { cm, onChange } = editor();
    const at = lineStart(cm, END);
    for (const change of [
      { from: at + 3, insert: "x" },
      { from: at, to: at + END.length },
      { from: at + END.length, to: at + END.length + 1 },
      { from: at - 1, to: at },
      { from: at, insert: "x" },
      { from: 0, to: cm.state.doc.length, insert: "" },
    ]) cm.dispatch({ changes: change, userEvent: "input" });
    expect(cm.state.doc.toString()).toBe(DOC);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("leave the text between them editable", () => {
    const { cm, onChange } = editor();
    const at = lineStart(cm, "Some text.");
    cm.dispatch({ changes: { from: at, to: at + 4, insert: "Other" } });
    expect(cm.state.doc.toString()).toContain("Other text.");
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("are marked so the user sees why", () => {
    const { view } = editor();
    const marked = [...view.container.querySelectorAll(".cm-paper-marker")].map((line) => line.textContent);
    expect(marked).toEqual([BEGIN, END]);
  });

  it("still follow a change made on disk", () => {
    const { cm, view, onChange } = editor();
    view.rerender(<CodeEditor path="paper/main.tex" text={DOC.replace(END, "%% paper-writing block intro.lead end\nextra")} label="paper/main.tex" onChange={onChange} />);
    expect(cm.state.doc.toString()).toContain("extra");
  });

  it("do not limit a file that is not LaTeX", () => {
    const { cm } = editor("notes.md");
    cm.dispatch({ changes: { from: 0, to: cm.state.doc.length, insert: "" } });
    expect(cm.state.doc.toString()).toBe("");
  });
});
