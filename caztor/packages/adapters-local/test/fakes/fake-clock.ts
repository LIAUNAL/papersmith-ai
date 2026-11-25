import type { Clock } from "../../src/infra.ts";

interface Timer {
  id: number;
  due: number;
  fn: () => void;
}

/** Deterministic clock: time only moves through `advance`. */
export class FakeClock implements Clock {
  private current: number;
  private nextId = 1;
  private timers: Timer[] = [];

  constructor(start = 0) {
    this.current = start;
  }

  now(): number {
    return this.current;
  }

  setTimeout(fn: () => void, ms: number): () => void {
    const timer: Timer = { id: this.nextId++, due: this.current + ms, fn };
    this.timers.push(timer);
    return () => {
      this.timers = this.timers.filter((candidate) => candidate.id !== timer.id);
    };
  }

  get pendingTimers(): number {
    return this.timers.length;
  }

  /** Moves time forward, firing every timer that falls due, including timers scheduled while firing. */
  advance(ms: number): void {
    const target = this.current + ms;
    for (;;) {
      const next = this.timers
        .filter((timer) => timer.due <= target)
        .sort((a, b) => a.due - b.due || a.id - b.id)[0];
      if (next === undefined) break;
      this.timers = this.timers.filter((timer) => timer.id !== next.id);
      this.current = Math.max(this.current, next.due);
      next.fn();
    }
    this.current = target;
  }
}
