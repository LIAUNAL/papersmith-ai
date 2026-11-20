import { fileURLToPath } from "node:url";

/**
 * A path inside Caztor's repository, found from this module's location: `packages/adapters-local/src/`, three folders
 * below the root. The server bundle (`apps/server-local/dist/main.mjs`) sits three folders below the root too, so the
 * same expression holds once this module is inlined there. Keep both at that depth.
 */
export const repositoryPath = (relative: string): string => fileURLToPath(new URL(`../../../${relative}`, import.meta.url)).replace(/\/$/, "");
