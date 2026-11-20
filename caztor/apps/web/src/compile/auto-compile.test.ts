import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTO_COMPILE_DELAY_MS, startAutoCompile } from "./auto-compile.ts";

beforeEach(() => void vi.useFakeTimers());
afterEach(() => void vi.useRealTimers());

function setup(enabled = true) {
  let saved: (path: string) => void = () => {};
  let unsubscribed = false;
  const state = { enabled, engine: true, starts: 0 };
  const stop = startAutoCompile({
    onSaved: (listener) => {
      saved = listener;
      return () => void (unsubscribed = true);
    },
    isEnabled: () => state.enabled && state.engine,
    compile: () => void (state.starts += 1),
  });
  return { state, save: (path = "main.tex") => saved(path), stop, wasUnsubscribed: () => unsubscribed };
}

describe("auto-compile", () => {
  it("compiles 1.5 s after a successful save", () => {
    const { state, save } = setup();
    save();
    vi.advanceTimersByTime(AUTO_COMPILE_DELAY_MS - 1);
    expect(state.starts).toBe(0);
    vi.advanceTimersByTime(1);
    expect(state.starts).toBe(1);
    expect(AUTO_COMPILE_DELAY_MS).toBe(1500);
  });

  it("restarts the wait on every further save, so a burst of saves compiles once", () => {
    const { state, save } = setup();
    save("a.tex");
    vi.advanceTimersByTime(1000);
    save("b.tex");
    vi.advanceTimersByTime(1000);
    expect(state.starts).toBe(0);
    vi.advanceTimersByTime(500);
    expect(state.starts).toBe(1);
  });

  it("does nothing while it is switched off", () => {
    const { state, save } = setup(false);
    save();
    vi.advanceTimersByTime(AUTO_COMPILE_DELAY_MS * 2);
    expect(state.starts).toBe(0);
  });

  it("does not compile when it was switched off during the wait", () => {
    const { state, save } = setup();
    save();
    state.enabled = false;
    vi.advanceTimersByTime(AUTO_COMPILE_DELAY_MS);
    expect(state.starts).toBe(0);
  });

  it("does nothing when the engine is missing", () => {
    const { state, save } = setup();
    state.engine = false;
    save();
    vi.advanceTimersByTime(AUTO_COMPILE_DELAY_MS);
    expect(state.starts).toBe(0);
  });

  it("cancels a pending compile and stops listening when stopped", () => {
    const { state, save, stop, wasUnsubscribed } = setup();
    save();
    stop();
    vi.advanceTimersByTime(AUTO_COMPILE_DELAY_MS);
    expect(state.starts).toBe(0);
    expect(wasUnsubscribed()).toBe(true);
  });
});
