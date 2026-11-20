import { useState } from "react";
import { THEMES, type Theme, type ThemeStore } from "./theme.ts";
import "./ThemeControl.css";

const LABELS: Readonly<Record<Theme, string>> = { system: "System", light: "Light", dark: "Dark" };

/** Chooses the color theme. The PDF page keeps its own colors, because it shows the paper as it will print. */
export function ThemeControl({ store }: { store: ThemeStore }) {
  const [theme, setTheme] = useState(store.get);
  return (
    <label className="theme-control">
      <span>Theme</span>
      <select
        value={theme}
        onChange={(event) => {
          const next = event.target.value as Theme;
          store.set(next);
          setTheme(next);
        }}
      >
        {THEMES.map((option) => (
          <option key={option} value={option}>
            {LABELS[option]}
          </option>
        ))}
      </select>
    </label>
  );
}
