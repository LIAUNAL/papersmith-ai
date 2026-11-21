import { useMemo, useState, useSyncExternalStore } from "react";
import type { PassageFocus } from "./focus.ts";
import type { ChatController } from "../chat/controller.ts";
import type { StorageLike } from "../layout/storage.ts";
import { explainedPassages, findPassages } from "./passages.ts";

export const EXPLAIN_KEY = "caztor.explain.v1";

export interface Explained {
  /** Whether the passages are marked. On unless the user turned it off. */
  on: boolean;
  toggle(): void;
  /** The passages of the paper the latest reply quotes, whether or not they are marked. */
  passages: readonly string[];
  /** Which passage the arrows last brought into view (zero-based), or null before the first step. */
  current: number | null;
  /** Brings the next (1) or previous (-1) passage into view, going round at either end. */
  step(direction: 1 | -1): void;
  /** What the editor and the PDF bring into view; null until a step. */
  focus: PassageFocus | null;
}

/** The passages of the paper the assistant's latest reply explains, and the switch that marks them. */
/**
 * `paper` is the text of the paper's main file: a quotation it does not hold (the experiments protocol, a proposal) is
 * left out, so only the paper is marked and stepped through. Null while that text is not known, and then nothing is.
 */
export function useExplained(chat: ChatController, storage: StorageLike | null, paper: string | null): Explained {
  const view = useSyncExternalStore(chat.subscribe, chat.getSnapshot);
  const [on, setOn] = useState(() => {
    try {
      return storage?.getItem(EXPLAIN_KEY) !== "off";
    } catch {
      return true;
    }
  });
  const latest = [...view.chat.turns].reverse().find((turn) => turn.items.some((item) => item.kind === "text"));
  const reply = latest?.items.flatMap((item) => (item.kind === "text" ? [item.text] : [])).join("\n") ?? "";
  const quoted = useMemo(() => explainedPassages(reply), [reply]);
  const passages = useMemo(() => (paper === null ? [] : quoted.filter((passage) => findPassages(paper, [passage]).length > 0)), [quoted, paper]);
  // The position belongs to one list of passages: a new reply starts again before the first.
  const [position, setPosition] = useState<{ of: readonly string[]; index: number; nonce: number } | null>(null);
  const current = position !== null && position.of === passages && position.index < passages.length ? position : null;
  return {
    on,
    passages,
    current: current?.index ?? null,
    focus: current === null ? null : { passage: passages[current.index]!, nonce: current.nonce },
    step(direction) {
      if (passages.length === 0) return;
      setPosition((last) => {
        const from = last !== null && last.of === passages ? last.index : direction === 1 ? -1 : 0;
        return { of: passages, index: (from + direction + passages.length) % passages.length, nonce: (last?.nonce ?? 0) + 1 };
      });
    },
    toggle() {
      setOn((current) => {
        try {
          storage?.setItem(EXPLAIN_KEY, current ? "off" : "on");
        } catch {
          // Remembering the switch is a convenience.
        }
        return !current;
      });
    },
  };
}
