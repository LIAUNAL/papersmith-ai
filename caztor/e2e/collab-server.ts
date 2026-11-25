// The server for e2e/collaborators.mjs: exposed on loopback under the public name `localhost:<port>`, with its own
// throwaway configuration folder, so the real users store is never touched and nothing leaves the machine. Its PATH
// holds only the system folders and a scripted `claude`, so a sign-in from the browser runs no real CLI.
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { nodeFileSystem } from "@caztor/adapters-local";
import { nodeListen } from "../apps/server-local/src/node-listen.ts";
import { startServer } from "../apps/server-local/src/server.ts";

const projectDir = resolve(process.argv[2] ?? ".");
const port = await new Promise<number>((done, fail) => {
  const probe = createServer();
  probe.once("error", fail);
  probe.listen(0, "127.0.0.1", () => {
    const { port: free } = probe.address() as { port: number };
    probe.close(() => done(free));
  });
});
const configHome = mkdtempSync(join(tmpdir(), "caztor-e2e-config-"));
const bin = mkdtempSync(join(tmpdir(), "caztor-e2e-bin-"));
// The first lines `claude auth login` prints with no terminal, then it reads the pasted code and succeeds.
writeFileSync(
  join(bin, "claude"),
  [
    "#!/bin/sh",
    'if [ "$1" = "--version" ]; then echo "2.1.317 (Claude Code)"; exit 0; fi',
    'if [ "$1" = "auth" ]; then',
    '  echo "Opening browser to sign in…"',
    "  echo \"If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=e2e\"",
    '  printf "Paste code here if prompted > "',
    "  read code",
    '  echo "Login successful."',
    "  exit 0",
    "fi",
    "exit 1",
    "",
  ].join("\n"),
);
chmodSync(join(bin, "claude"), 0o755);
const server = await startServer({
  projectDir,
  webRoot: fileURLToPath(new URL("../apps/web/dist", import.meta.url)),
  env: { ...process.env, XDG_CONFIG_HOME: configHome, PATH: `${bin}:/usr/bin:/bin` },
  fs: nodeFileSystem,
  listen: nodeListen,
  startPort: port,
  publicNames: [`localhost:${port}`],
});
if (server.port !== port) throw new Error("The chosen port was taken before the server bound it.");
console.log(`Host link ${server.hostLink} config ${configHome} bin ${bin}`);
console.log(`Caztor is running at ${server.url} for ${server.root}`);
const stop = () => void server.close().then(() => process.exit(0));
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
