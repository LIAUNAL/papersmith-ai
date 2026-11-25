import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { parseCommand } from "./cli.ts";
import { nodeListen } from "./node-listen.ts";
import { startServer } from "./server.ts";
import { runUserCommand } from "./user-commands.ts";

const args = parseCommand(process.argv, process.env);
// The frame key is read once: Caztor's agents and compiles, which inherit this environment, never see it.
delete process.env["CAZTOR_EMBED_KEY"];
if (!args.ok) {
  console.error(args.usage);
  process.exit(2);
}

if (args.command !== "serve") {
  // A project folder is given relative to where the user typed the command, as for serving.
  const command = args.command === "trust-build" ? { ...args, projectDir: resolve(process.env["INIT_CWD"] ?? process.cwd(), args.projectDir) } : args;
  const result = await runUserCommand(command, { fs: nodeFileSystem, env: process.env });
  for (const line of result.lines) (result.code === 0 ? console.log : console.error)(line);
  process.exit(result.code);
}

try {
  const { exposure } = args;
  const server = await startServer({
    // npm runs scripts from the repository root; INIT_CWD is where the user typed the command.
    projectDir: resolve(process.env["INIT_CWD"] ?? process.cwd(), args.projectDir),
    webRoot: fileURLToPath(new URL("../../web/dist", import.meta.url)),
    env: process.env,
    // The source under npm start, or the bundle a papersmith install carries: either confirms a recipe the same way.
    trustCommand: [process.execPath, process.argv[1] ?? fileURLToPath(import.meta.url)],
    fs: nodeFileSystem,
    listen: nodeListen,
    host: exposure.host,
    publicNames: exposure.publicNames,
    secure: exposure.secure,
    ...(args.embedOrigins === undefined ? {} : { embedOrigin: args.embedOrigins }),
    ...(args.embedKey === undefined ? {} : { embedKey: args.embedKey }),
  });
  console.log(`Caztor is running at ${server.url} for ${server.root}`);
  if (server.hostLink !== undefined) {
    const names = exposure.publicNames.map((name) => ` --public-name ${name}`).join("");
    console.log(`Collaborators reach it at ${exposure.secure ? "https" : "http"}://${exposure.publicNames[0]}`);
    // The host link is the one secret printed: it works once, for this launch, and signs this browser in as the host.
    console.log(`Open this host link once to use Caztor yourself: ${server.hostLink}`);
    console.log(`Invite someone with: npm start -- invite <name> [--for 7d]${names}${exposure.secure ? " --secure" : ""}`);
  }
  const stop = () => void server.close().then(() => process.exit(0));
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
