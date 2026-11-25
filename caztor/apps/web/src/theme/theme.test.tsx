import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { createThemeStore, THEME_KEY } from "./theme.ts";
import { ThemeControl } from "./ThemeControl.tsx";

const memory = (initial: Record<string, string> = {}) => {
  const items = new Map(Object.entries(initial));
  return { getItem: (key: string) => items.get(key) ?? null, setItem: (key: string, value: string) => void items.set(key, value) };
};

afterEach(() => document.documentElement.removeAttribute("data-theme"));

describe("the theme store", () => {
  it("starts with the system theme and sets no attribute", () => {
    createThemeStore(memory());
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("applies and remembers a choice, and a new store reads it back", () => {
    const storage = memory();
    createThemeStore(storage).set("dark");
    expect(document.documentElement.dataset["theme"]).toBe("dark");
    expect(storage.getItem(THEME_KEY)).toBe("dark");
    document.documentElement.removeAttribute("data-theme");
    expect(createThemeStore(storage).get()).toBe("dark");
    expect(document.documentElement.dataset["theme"]).toBe("dark");
  });

  it("removes the attribute when going back to the system theme", () => {
    const store = createThemeStore(memory({ [THEME_KEY]: "light" }));
    store.set("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("ignores an unknown saved value, and survives storage that throws", () => {
    expect(createThemeStore(memory({ [THEME_KEY]: "neon" })).get()).toBe("system");
    const store = createThemeStore({
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    store.set("dark");
    expect(store.get()).toBe("dark");
    expect(createThemeStore(null).get()).toBe("system");
  });
});

describe("the theme control", () => {
  it("offers system, light and dark and applies the choice", async () => {
    const store = createThemeStore(memory());
    render(<ThemeControl store={store} />);
    const control = screen.getByRole("combobox", { name: "Theme" });
    expect(control).toHaveValue("system");
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["System", "Light", "Dark"]);
    await userEvent.selectOptions(control, "dark");
    expect(control).toHaveValue("dark");
    expect(document.documentElement.dataset["theme"]).toBe("dark");
  });
});
