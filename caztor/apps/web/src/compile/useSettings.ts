import { useCallback, useRef, useState } from "react";
import type { ApiClient, Settings } from "../api/types.ts";

/**
 * The project's settings as the UI shows them. A change shows at once, is saved through the settings route and is
 * undone, with the message returned, when saving fails. The server keeps the values per project.
 */
export function useSettings(api: Pick<ApiClient, "patchSettings">, initial: Settings): {
  settings: Settings;
  change: (patch: Partial<Settings>) => Promise<string | null>;
} {
  const [settings, setSettings] = useState(initial);
  const latest = useRef(settings);
  latest.current = settings;

  const change = useCallback(
    async (patch: Partial<Settings>): Promise<string | null> => {
      const before = latest.current;
      setSettings({ ...before, ...patch });
      try {
        setSettings(await api.patchSettings(patch));
        return null;
      } catch (error) {
        setSettings((current) => {
          const restored = { ...current };
          for (const key of Object.keys(patch) as Array<keyof Settings>) (restored as Record<string, unknown>)[key] = before[key];
          return restored;
        });
        return error instanceof Error ? error.message : "The setting could not be saved.";
      }
    },
    [api],
  );

  return { settings, change };
}
