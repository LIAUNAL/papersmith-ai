import type { StorageLike } from "../layout/storage.ts";

export const THEME_KEY = "caztor.theme.v1";
export const THEMES = ["system", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export interface ThemeStore {
  get(): Theme;
  set(theme: Theme): void;
}

function apply(theme: Theme): void {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset["theme"] = theme;
}

/** The chosen theme. `public/theme-init.js` applies the same saved value before the first paint. Never throws. */
export function createThemeStore(storage: StorageLike | null): ThemeStore {
  let current: Theme = "system";
  try {
    const saved = storage?.getItem(THEME_KEY) ?? null;
    if ((THEMES as readonly (string | null)[]).includes(saved)) current = saved as Theme;
  } catch {
    // Blocked storage: the system theme, for this page only.
  }
  apply(current);
  return {
    get: () => current,
    set(theme) {
      current = theme;
      apply(theme);
      try {
        storage?.setItem(THEME_KEY, theme);
      } catch {
        // Remembering the theme is a convenience; blocked or full storage must never break the app.
      }
    },
  };
}
