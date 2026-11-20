import { describe, expect, it } from "vitest";
import { FakeClock } from "./fake-clock.ts";

describe("FakeClock", () => {
  it("starts at the given time and only moves on advance", () => {
    const clock = new FakeClock(1000);
    expect(clock.now()).toBe(1000);
    clock.advance(250);
    expect(clock.now()).toBe(1250);
  });

  it("fires timers in due order and not before they are due", () => {
    const clock = new FakeClock();
    const fired: string[] = [];
    clock.setTimeout(() => fired.push("late"), 300);
    clock.setTimeout(() => fired.push("early"), 100);

    clock.advance(99);
    expect(fired).toEqual([]);
    clock.advance(1);
    expect(fired).toEqual(["early"]);
    clock.advance(500);
    expect(fired).toEqual(["early", "late"]);
  });

  it("does not fire a cancelled timer", () => {
    const clock = new FakeClock();
    const fired: string[] = [];
    const cancel = clock.setTimeout(() => fired.push("x"), 50);
    cancel();
    clock.advance(100);
    expect(fired).toEqual([]);
    expect(clock.pendingTimers).toBe(0);
  });

  it("runs timers scheduled by a firing timer when they fall inside the advance window", () => {
    const clock = new FakeClock();
    const fired: number[] = [];
    clock.setTimeout(() => {
      fired.push(clock.now());
      clock.setTimeout(() => fired.push(clock.now()), 200);
    }, 100);

    clock.advance(1000);
    expect(fired).toEqual([100, 300]);
    expect(clock.now()).toBe(1000);
  });
});
