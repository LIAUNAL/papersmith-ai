import { StateEffect, StateField, type Extension } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import type { Range } from "./passages.ts";

/** Replaces the marked passages; an empty list removes every mark. */
export const setExplained = StateEffect.define<readonly Range[]>();
/** Replaces the passage the arrows brought into view; an empty list removes it. */
export const setCurrentExplained = StateEffect.define<readonly Range[]>();

/** Marks set by `effect`, moving with edits until they are set again. */
function marks(effect: typeof setExplained, decoration: Decoration): Extension {
  return StateField.define<DecorationSet>({
    create: () => Decoration.none,
    update(set, transaction) {
      let next = set.map(transaction.changes);
      for (const one of transaction.effects) {
        if (!one.is(effect)) continue;
        const length = transaction.state.doc.length;
        const ranges = one.value.filter((range) => range.from < range.to && range.to <= length);
        next = Decoration.set(ranges.map((range) => decoration.range(range.from, range.to)), true);
      }
      return next;
    },
    provide: (field) => EditorView.decorations.from(field),
  });
}

/** The soft-yellow marks of the passages the assistant explains. */
export const explainedPassages: Extension = marks(setExplained, Decoration.mark({ class: "cm-explained" }));
/** The stronger mark of the passage the arrows brought into view. */
export const currentExplainedPassage: Extension = marks(setCurrentExplained, Decoration.mark({ class: "cm-explained-current" }));
