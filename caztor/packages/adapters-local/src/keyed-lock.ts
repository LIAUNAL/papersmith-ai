/** Runs `work` while holding every key; see `createKeyedLock`. */
export type WithLocks = <T>(keys: readonly string[], work: () => Promise<T>) => Promise<T>;

/**
 * Serializes work per key inside this process. Keys are acquired in sorted order, so two operations that
 * share several keys can never wait on each other. A caller that already holds a key must not ask for it again.
 */
export function createKeyedLock(): WithLocks {
  const tails = new Map<string, Promise<void>>();

  async function acquire(key: string): Promise<() => void> {
    const previous = tails.get(key) ?? Promise.resolve();
    let release = () => {};
    const mine = new Promise<void>((resolve) => (release = resolve));
    const tail = previous.then(() => mine);
    tails.set(key, tail);
    await previous;
    return () => {
      release();
      if (tails.get(key) === tail) tails.delete(key);
    };
  }

  return async function withLocks<T>(keys: readonly string[], work: () => Promise<T>): Promise<T> {
    const releases: Array<() => void> = [];
    try {
      for (const key of [...new Set(keys)].sort()) releases.push(await acquire(key));
      return await work();
    } finally {
      for (const release of releases.reverse()) release();
    }
  };
}
