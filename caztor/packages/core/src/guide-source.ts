import { isGuideName } from "./agent-targets.ts";
import type { GuideDocument, GuideSourcePort, Result } from "./ports.ts";

/** Why a set of guide documents cannot be provisioned, or null when it can. */
export function guideSetProblem(documents: readonly GuideDocument[]): string | null {
  const seen = new Set<string>();
  for (const { name } of documents) {
    if (!isGuideName(name)) return `"${name}" is not a valid guide name`;
    if (seen.has(name)) return `"${name}" appears twice`;
    seen.add(name);
  }
  return seen.has("INDEX.md") ? null : "INDEX.md is missing";
}

const messageOf = (error: unknown): string => (error instanceof Error ? error.message : String(error));

async function loadChecked(source: GuideSourcePort): Promise<Result<readonly GuideDocument[], { message: string }>> {
  try {
    const loaded = await source.load();
    if (!loaded.ok) return loaded;
    const problem = guideSetProblem(loaded.value);
    return problem === null ? loaded : { ok: false, error: { message: problem } };
  } catch (error) {
    return { ok: false, error: { message: messageOf(error) } };
  }
}

/**
 * Uses `primary` while it supplies a usable set, and `fallback` otherwise. When neither works the error carries both
 * reasons, so the user can tell which source to look at.
 */
export function withFallback(primary: GuideSourcePort, fallback: GuideSourcePort): GuideSourcePort {
  return {
    async load() {
      const first = await loadChecked(primary);
      if (first.ok) return first;
      const second = await loadChecked(fallback);
      if (second.ok) return second;
      return { ok: false, error: { message: `${second.error.message} (the configured source also failed: ${first.error.message})` } };
    },
  };
}
