import { PAPER_MARKER_PREFIX } from "@caztor/core";
import { EditorState, RangeSetBuilder, type Extension, type Transaction } from "@codemirror/state";
import { Decoration, EditorView, ViewPlugin, type DecorationSet, type ViewUpdate } from "@codemirror/view";

const markerLine = Decoration.line({ class: "cm-paper-marker", attributes: { title: "PaperSmith block marker: it cannot be changed here" } });

function markerRanges(state: EditorState): Array<{ from: number; to: number }> {
  const ranges: Array<{ from: number; to: number }> = [];
  for (let number = 1; number <= state.doc.lines; number += 1) {
    const line = state.doc.line(number);
    if (line.text.startsWith(PAPER_MARKER_PREFIX)) ranges.push({ from: line.from, to: line.to });
  }
  return ranges;
}

function decorate(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  for (const range of markerRanges(view.state)) builder.add(range.from, range.from, markerLine);
  return builder.finish();
}

/**
 * Keeps PaperSmith's block markers as they are: a change that touches a marker line, including its line breaks, is not
 * applied. Changes that come from the file on disk pass, so the editor always shows what is there.
 */
export function protectPaperMarkers(fromOutside: (transaction: Transaction) => boolean): Extension {
  return [
    EditorState.changeFilter.of((transaction) => {
      if (!transaction.docChanged || fromOutside(transaction)) return true;
      const protectedRanges = markerRanges(transaction.startState);
      let touches = false;
      transaction.changes.iterChangedRanges((fromA, toA) => {
        if (protectedRanges.some((range) => fromA <= range.to && toA >= range.from)) touches = true;
      });
      return !touches;
    }),
    ViewPlugin.fromClass(
      class {
        decorations: DecorationSet;
        constructor(view: EditorView) {
          this.decorations = decorate(view);
        }
        update(update: ViewUpdate) {
          if (update.docChanged || update.viewportChanged) this.decorations = decorate(update.view);
        }
      },
      { decorations: (plugin) => plugin.decorations },
    ),
  ];
}
