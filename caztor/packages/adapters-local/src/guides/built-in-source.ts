import { isGuideName, type GuideDocument, type GuideSourcePort } from "@caztor/core";
import type { FileSystem } from "../infra.ts";
import { repositoryPath } from "../repository-path.ts";

export interface BuiltInGuideSourceOptions {
  fs: FileSystem;
  /** Folder with `INDEX.md` and the numbered guides. */
  guidesDir: string;
  /** The Apache-2.0 text; it is served next to the guides as `LICENSE-papersmith-ai.txt`. */
  licensePath: string;
}

/** The license copy travels with the guides under this name. */
export const LICENSE_GUIDE_NAME = "LICENSE-papersmith-ai.txt";

/** The `guides` folder of the repository, found from this file's location. */
export const defaultGuidesDir = (): string => repositoryPath("guides");
/** The Apache-2.0 text of the repository. */
export const defaultLicensePath = (): string => repositoryPath("LICENSES/Apache-2.0.txt");

const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/**
 * The guides that ship with Caztor. Only regular files with a guide name are served; a link, a folder or any other
 * file in the folder (the source record, tests) is ignored.
 */
export function createBuiltInGuideSource(options: BuiltInGuideSourceOptions): GuideSourcePort {
  const { fs } = options;
  return {
    async load() {
      const documents: GuideDocument[] = [];
      try {
        for (const entry of await fs.readdir(options.guidesDir)) {
          if (!isGuideName(entry.name) || !entry.isFile() || entry.isSymbolicLink()) continue;
          documents.push({ name: entry.name, bytes: await fs.readFile(`${options.guidesDir}/${entry.name}`) });
        }
      } catch (error) {
        return { ok: false as const, error: { message: `The built-in writing guides could not be read: ${errorText(error)}` } };
      }
      try {
        documents.push({ name: LICENSE_GUIDE_NAME, bytes: await fs.readFile(options.licensePath) });
      } catch (error) {
        return { ok: false as const, error: { message: `The license text that goes with the writing guides could not be read: ${errorText(error)}` } };
      }
      documents.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
      return { ok: true as const, value: documents };
    },
  };
}
