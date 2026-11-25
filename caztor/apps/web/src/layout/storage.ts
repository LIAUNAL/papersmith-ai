import { DEFAULT_LAYOUT, parseLayout, type PaneLayout } from "./panes.ts";

export const LAYOUT_KEY = "caztor.layout.v1";

/** The part of `Storage` the layout needs. Both methods may throw (blocked storage, full quota). */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface LayoutStore {
  /** The saved layout, or the defaults when it is missing, unreadable or invalid. Never throws. */
  load(): PaneLayout;
  /** Saves a valid layout. Never throws. */
  save(layout: PaneLayout): void;
}

export function createLayoutStore(storage: StorageLike | null, key: string = LAYOUT_KEY): LayoutStore {
  return {
    load() {
      try {
        const text = storage?.getItem(key) ?? null;
        if (text === null) return DEFAULT_LAYOUT;
        return parseLayout(JSON.parse(text) as unknown) ?? DEFAULT_LAYOUT;
      } catch {
        return DEFAULT_LAYOUT;
      }
    },
    save(layout) {
      if (parseLayout(layout) === null) return;
      try {
        storage?.setItem(key, JSON.stringify(layout));
      } catch {
        // Persisting sizes is a convenience; a blocked or full storage must never break the app.
      }
    },
  };
}
