import { useMemo, useState, useSyncExternalStore } from "react";
import type { ChatController } from "../chat/controller.ts";
import type { StorageLike } from "../layout/storage.ts";
import { explainedPassages } from "./passages.ts";

export const EXPLAIN_KEY = "caztor.explain.v1";

export interface Explained {
  /** Whether the passages are marked. On unless the user turned it off. */
  on: boolean;
  toggle(): void;
  /** The passages the latest reply quotes, whether or not they are marked. */
  passages: readonly string[];
}

/** The passages of the paper the assistant's latest reply explains, and the switch that marks them. */
export function useExplained(chat: ChatController, storage: StorageLike | null): Explained {
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
  const passages = useMemo(() => explainedPassages(reply), [reply]);
  return {
    on,
    passages,
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
