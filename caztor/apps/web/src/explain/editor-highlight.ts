import { StateEffect, StateField, type Extension } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import type { Range } from "./passages.ts";

/** Replaces the marked passages; an empty list removes every mark. */
export const setExplained = StateEffect.define<readonly Range[]>();

const mark = Decoration.mark({ class: "cm-explained" });

/** The soft-yellow marks of the passages the assistant explains. They move with edits until they are set again. */
export const explainedPassages: Extension = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(marks, transaction) {
    let next = marks.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (!effect.is(setExplained)) continue;
      const length = transaction.state.doc.length;
      const ranges = effect.value.filter((range) => range.from < range.to && range.to <= length);
      next = Decoration.set(ranges.map((range) => mark.range(range.from, range.to)), true);
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});
