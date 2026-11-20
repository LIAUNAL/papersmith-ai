/** Wait after the last successful save before compiling. */
export const AUTO_COMPILE_DELAY_MS = 1500;

interface AutoCompileOptions {
  /** Subscribes to successful saves; returns the function that unsubscribes. */
  onSaved: (listener: (path: string) => void) => () => void;
  /** Whether auto-compile is switched on and an engine exists. Read again when the wait ends. */
  isEnabled: () => boolean;
  compile: () => void;
}

/** Compiles shortly after a successful save. Further saves restart the wait. Returns the function that stops it. */
export function startAutoCompile(options: AutoCompileOptions): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const unsubscribe = options.onSaved(() => {
    if (!options.isEnabled()) return;
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      if (options.isEnabled()) options.compile();
    }, AUTO_COMPILE_DELAY_MS);
  });
  return () => {
    unsubscribe();
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
}
