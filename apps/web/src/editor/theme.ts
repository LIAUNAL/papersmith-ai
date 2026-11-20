import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { tags } from "@lezer/highlight";

/** Syntax colors come from the design tokens, so the editor follows the light and dark themes without code. */
export const highlightStyle = HighlightStyle.define([
  { tag: [tags.tagName, tags.keyword, tags.standard(tags.tagName)], color: "var(--syntax-command)" },
  { tag: [tags.atom, tags.meta, tags.special(tags.variableName)], color: "var(--syntax-keyword)" },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: "var(--syntax-comment)", fontStyle: "italic" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--syntax-string)" },
  { tag: tags.number, color: "var(--syntax-number)" },
  { tag: [tags.propertyName, tags.attributeName], color: "var(--syntax-property)" },
  { tag: [tags.bracket, tags.operator, tags.punctuation], color: "var(--syntax-bracket)" },
  { tag: [tags.labelName, tags.variableName, tags.typeName], color: "var(--syntax-variable)" },
  { tag: tags.invalid, color: "var(--color-danger)" },
]);

/** Layout, surface, gutter, active line and selection of the editor, all taken from the design tokens. */
const viewTheme = EditorView.theme({
  "&": { height: "100%", color: "var(--color-text)", backgroundColor: "var(--color-surface)", fontSize: "var(--editor-font-size)" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "var(--editor-line-height)", overflow: "auto" },
  ".cm-content": { caretColor: "var(--color-accent)", padding: "var(--space-2) 0" },
  ".cm-line": { padding: "0 var(--space-3)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--color-accent)", borderLeftWidth: "2px" },
  ".cm-gutters": {
    backgroundColor: "var(--color-surface-muted)",
    color: "var(--editor-gutter-text)",
    borderRight: "var(--border-width) solid var(--color-border)",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 var(--space-2) 0 var(--space-3)" },
  ".cm-activeLine": { backgroundColor: "var(--editor-active-line)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--editor-active-line)", color: "var(--color-text)" },
  ".cm-selectionBackground": { backgroundColor: "var(--editor-selection-inactive)" },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground": { backgroundColor: "var(--editor-selection)" },
  ".cm-content ::selection": { backgroundColor: "var(--editor-selection)" },
  ".cm-matchingBracket": { backgroundColor: "var(--editor-selection-inactive)", outline: "none" },
  ".cm-changedLine": { backgroundColor: "var(--editor-added)" },
  ".cm-deletedChunk": { backgroundColor: "var(--editor-removed)" },
});

export const editorTheme: Extension = [viewTheme, syntaxHighlighting(highlightStyle)];
