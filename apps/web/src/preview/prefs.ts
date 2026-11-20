import type { StorageLike } from "../layout/storage.ts";
import { clampPercent, type Anchor, type Zoom } from "./layout.ts";

export interface PreviewPrefs {
  zoom: Zoom;
  anchor: Anchor;
}

export const DEFAULT_PREFS: PreviewPrefs = { zoom: { mode: "fit" }, anchor: { page: 0, offset: 0 } };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The preferences in `value`, or null when its shape is wrong. A percentage outside the supported range is clamped. */
export function parsePrefs(value: unknown): PreviewPrefs | null {
  if (!isRecord(value) || !isRecord(value["zoom"]) || !isRecord(value["anchor"])) return null;
  const { zoom, anchor } = value as { zoom: Record<string, unknown>; anchor: Record<string, unknown> };
  const page = anchor["page"];
  const offset = anchor["offset"];
  if (typeof page !== "number" || !Number.isInteger(page) || page < 0) return null;
  if (typeof offset !== "number" || !Number.isFinite(offset) || offset < 0 || offset > 1) return null;
  if (zoom["mode"] === "fit") return { zoom: { mode: "fit" }, anchor: { page, offset } };
  if (zoom["mode"] === "percent" && typeof zoom["percent"] === "number" && Number.isFinite(zoom["percent"])) {
    return { zoom: { mode: "percent", percent: clampPercent(zoom["percent"]) }, anchor: { page, offset } };
  }
  return null;
}

export interface PrefsStore {
  /** The saved preferences, or the defaults. Never throws. */
  load(): PreviewPrefs;
  /** Saves valid preferences. Never throws. */
  save(prefs: PreviewPrefs): void;
}

/** Zoom and scroll position of the preview, one record per project. */
export function createPrefsStore(storage: StorageLike | null, project: string): PrefsStore {
  const key = `caztor.preview.v1.${encodeURIComponent(project)}`;
  return {
    load() {
      try {
        const text = storage?.getItem(key) ?? null;
        return text === null ? DEFAULT_PREFS : (parsePrefs(JSON.parse(text) as unknown) ?? DEFAULT_PREFS);
      } catch {
        return DEFAULT_PREFS;
      }
    },
    save(prefs) {
      if (parsePrefs(prefs) === null) return;
      try {
        storage?.setItem(key, JSON.stringify(prefs));
      } catch {
        // Remembering the position is a convenience; a blocked or full storage must never break the preview.
      }
    },
  };
}
