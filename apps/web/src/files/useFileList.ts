import type { FileEntry } from "@caztor/core";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../api/types.ts";

export type FileList = { status: "loading" } | { status: "failed"; message: string } | { status: "ready"; entries: FileEntry[] };

/**
 * The project's files. `reload` can be called at any time; calls made while a listing is in flight are merged
 * into one more listing, so a burst of changes never produces a burst of requests.
 */
export function useFileList(api: ApiClient): { list: FileList; reload: () => void } {
  const [list, setList] = useState<FileList>({ status: "loading" });
  const running = useRef(false);
  const again = useRef(false);
  const alive = useRef(true);

  const reload = useCallback(() => {
    if (running.current) {
      again.current = true;
      return;
    }
    running.current = true;
    api.listFiles().then(
      (entries) => alive.current && setList({ status: "ready", entries }),
      (error: unknown) =>
        alive.current && setList({ status: "failed", message: error instanceof Error ? error.message : "The files could not be listed." }),
    ).finally(() => {
      running.current = false;
      if (again.current && alive.current) {
        again.current = false;
        reload();
      }
    });
  }, [api]);

  useEffect(() => {
    alive.current = true;
    reload();
    // Changes made outside the tree (an agent, another editor) arrive as events; after a reconnect some may be missing.
    const unsubscribe = api.subscribeEvents((event) => {
      if (event.event === "file_changed" || event.event === "stream_resumed") reload();
    });
    return () => {
      alive.current = false;
      unsubscribe();
    };
  }, [api, reload]);

  return { list, reload };
}
