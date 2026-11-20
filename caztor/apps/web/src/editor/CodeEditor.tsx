import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { bracketMatching } from "@codemirror/language";
import { Annotation, EditorState, type Extension } from "@codemirror/state";
import { drawSelection, EditorView, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { explainedPassages, setExplained } from "../explain/editor-highlight.ts";
import { findPassages } from "../explain/passages.ts";
import { minimalChange } from "./diff.ts";
import { languageFor } from "./languages.ts";
import { protectPaperMarkers } from "./markers.ts";
import { editorTheme } from "./theme.ts";
import "./CodeEditor.css";

interface CodeEditorProps {
  /** The file shown. Each path keeps its own cursor and undo history while it is not the current one. */
  path: string;
  /** The text to show. Text that differs from the editor's own is applied as a change from outside. */
  text: string;
  /** Called with the whole new text after every edit by the user. */
  onChange: (text: string) => void;
  /** The accessible name of the text area. */
  label: string;
  /** Called when the user asks to save now (Ctrl or Cmd+S). */
  onSave?: () => void;
  /** Moves the cursor to the start of `line` (1-based) and scrolls it into view. A request is applied once, whatever the `id`. */
  reveal?: { line: number; id: number };
  /** Passages to mark in soft yellow wherever the text holds them; none or an empty list marks nothing. */
  highlights?: readonly string[];
}

/** Marks a change that came from outside the user's typing, so it is not reported back as an edit. */
const External = Annotation.define<boolean>();

function baseExtensions(path: string, label: string, save: () => void): Extension[] {
  const language = languageFor(path);
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightActiveLine(),
    drawSelection(),
    history(),
    bracketMatching(),
    EditorView.lineWrapping,
    keymap.of([
      { key: "Mod-s", preventDefault: true, run: () => (save(), true) },
      ...defaultKeymap,
      ...historyKeymap,
    ]),
    EditorView.contentAttributes.of({ "aria-label": label, spellcheck: "false", autocorrect: "off", autocapitalize: "off" }),
    editorTheme,
    explainedPassages,
    ...(language === null ? [] : [language]),
    ...(path.toLowerCase().endsWith(".tex") ? [protectPaperMarkers((transaction) => transaction.annotation(External) === true)] : []),
  ];
}

/**
 * A thin wrapper around a CodeMirror 6 view. It owns the view and nothing else: documents, hashes and saving
 * live in the editor session, which feeds this component `text` and listens to `onChange`.
 */
export function CodeEditor({ path, text, onChange, label, onSave, reveal, highlights }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const shown = useRef({ path, text });
  const remembered = useRef(new Map<string, { state: EditorState; scrollTop: number }>());
  const report = useRef(onChange);
  const labelRef = useRef(label);
  const saveRef = useRef(onSave);
  saveRef.current = onSave;
  const save = useRef(() => saveRef.current?.()).current;
  report.current = onChange;
  labelRef.current = label;

  useEffect(() => {
    const parent = host.current;
    if (parent === null) return;
    const created = new EditorView({
      parent,
      state: EditorState.create({ doc: shown.current.text, extensions: baseExtensions(shown.current.path, labelRef.current, save) }),
      dispatch(transaction, editor) {
        editor.update([transaction]);
        if (transaction.docChanged && transaction.annotation(External) !== true) {
          const next = transaction.newDoc.toString();
          shown.current.text = next;
          report.current(next);
        }
      },
    });
    view.current = created;
    const files = remembered.current;
    return () => {
      created.destroy();
      view.current = null;
      files.clear();
    };
  }, []);

  // Follow the props: another file was chosen, or the text of this one changed outside the editor.
  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    if (shown.current.path !== path) {
      remembered.current.set(shown.current.path, { state: editor.state, scrollTop: editor.scrollDOM.scrollTop });
      const previous = remembered.current.get(path);
      const state =
        previous !== undefined && previous.state.doc.toString() === text
          ? previous.state
          : EditorState.create({ doc: text, extensions: baseExtensions(path, label, save) });
      editor.setState(state);
      editor.scrollDOM.scrollTop = previous?.scrollTop ?? 0;
      shown.current = { path, text };
      return;
    }
    if (text === shown.current.text) return;
    const change = minimalChange(editor.state.doc.toString(), text);
    shown.current.text = text;
    if (change === null) return;
    // The scroll snapshot keeps the visible lines where they are; the selection follows the change.
    editor.dispatch({ changes: change, effects: editor.scrollSnapshot(), annotations: External.of(true) });
  }, [path, text, label, save]);

  // A jump asked for from outside (a log entry). It runs after the text sync above, so it lands in the right file.
  const revealed = useRef<number | null>(null);
  useEffect(() => {
    const editor = view.current;
    if (editor === null || reveal === undefined || revealed.current === reveal.id) return;
    if (shown.current.path !== path || editor.state.doc.toString() !== text) return;
    revealed.current = reveal.id;
    const line = editor.state.doc.line(Math.min(Math.max(reveal.line, 1), editor.state.doc.lines));
    editor.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: "center" }) });
    editor.focus();
  }, [reveal, path, text]);

  // Mark the explained passages in what is shown now: after the file, its text or the passages change.
  const wanted = (highlights ?? []).join("\n");
  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    const passages = wanted === "" ? [] : wanted.split("\n");
    editor.dispatch({ effects: setExplained.of(passages.length === 0 ? [] : findPassages(editor.state.doc.toString(), passages)) });
  }, [wanted, path, text]);

  return <div ref={host} className="code-editor" />;
}
