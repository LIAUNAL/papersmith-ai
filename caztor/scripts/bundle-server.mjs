// Builds Caztor's server into one file, apps/server-local/dist/main.mjs, that runs on Node.js alone: no TypeScript
// sources and no node_modules. PaperSmith ships it, with the built web app, the agents and the guides, in its wheel.
// The bundle sits three folders below the root, as the modules that find files from their own location expect
// (see packages/adapters-local/src/repository-path.ts and apps/server-local/src/main.ts).
import { rolldown } from "rolldown";
import { builtinModules } from "node:module";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const bundle = await rolldown({
  input: `${root}apps/server-local/src/main.ts`,
  platform: "node",
  external: [...builtinModules, ...builtinModules.map((name) => `node:${name}`)],
  logLevel: "warn",
});
await bundle.write({ file: `${root}apps/server-local/dist/main.mjs`, format: "esm", codeSplitting: false });
await bundle.close();
console.log("Caztor server bundled into apps/server-local/dist/main.mjs");
