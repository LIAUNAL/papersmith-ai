import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { bracketMatching } from "@codemirror/language";
import { Annotation, EditorState, type Extension } from "@codemirror/state";
import { drawSelection, EditorView, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { currentExplainedPassage, explainedPassages, setCurrentExplained, setExplained } from "../explain/editor-highlight.ts";
import type { PassageFocus } from "../explain/focus.ts";
import { jumpCandidates } from "../explain/source-jump.ts";
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
  reveal?: { line: number; id: number; select?: { column: number; length: number } };
  /** Passages to mark in soft yellow wherever the text holds them; none or an empty list marks nothing. */
  highlights?: readonly string[];
  /** The explained passage to bring into view and mark more strongly, once per nonce. */
  focus?: PassageFocus | null;
  /** Called on a double click with the texts around the clicked word, narrowest first, for the PDF to bring into view. */
  onJumpToPdf?: (candidates: readonly string[]) => void;
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
    currentExplainedPassage,
    ...(language === null ? [] : [language]),
    ...(path.toLowerCase().endsWith(".tex") ? [protectPaperMarkers((transaction) => transaction.annotation(External) === true)] : []),
  ];
}

/**
 * A thin wrapper around a CodeMirror 6 view. It owns the view and nothing else: documents, hashes and saving
 * live in the editor session, which feeds this component `text` and listens to `onChange`.
 */
export function CodeEditor({ path, text, onChange, label, onSave, reveal, highlights, focus, onJumpToPdf }: CodeEditorProps) {
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
  const jumpRef = useRef(onJumpToPdf);
  jumpRef.current = onJumpToPdf;

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
    // The double click has already selected the word by now: its line names what to look for in the PDF.
    const jump = () => {
      const editor = view.current;
      if (editor === null || jumpRef.current === undefined) return;
      const at = editor.state.selection.main.from;
      const line = editor.state.doc.lineAt(at);
      const candidates = jumpCandidates(line.text, at - line.from);
      if (candidates.length > 0) jumpRef.current(candidates);
    };
    created.contentDOM.addEventListener("dblclick", jump);
    const files = remembered.current;
    return () => {
      created.contentDOM.removeEventListener("dblclick", jump);
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
    // A word to select stays inside its line.
    const from = Math.min(line.from + (reveal.select?.column ?? 0), line.to);
    const to = Math.min(from + (reveal.select?.length ?? 0), line.to);
    editor.dispatch({ selection: { anchor: from, head: to }, effects: EditorView.scrollIntoView(from, { y: "center" }) });
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

  // A step to an explained passage: mark it more strongly and scroll to it when this file holds it.
  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    // No step (highlighting turned off, or a new reply): no stronger mark either.
    if (focus === null || focus === undefined) {
      editor.dispatch({ effects: setCurrentExplained.of([]) });
      return;
    }
    const ranges = findPassages(editor.state.doc.toString(), [focus.passage]);
    const first = ranges[0];
    editor.dispatch({
      effects: [setCurrentExplained.of(ranges), ...(first === undefined ? [] : [EditorView.scrollIntoView(first.from, { y: "center" })])],
    });
    // Only a new step (or a new file) moves the view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce ?? null, path]);

  return <div ref={host} className="code-editor" />;
}
