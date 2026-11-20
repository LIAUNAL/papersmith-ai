// The server for e2e/chat.mjs. By default the providers are scripted fakes that spend no tokens and really edit the
// project files; with CAZTOR_E2E_REAL=1 it is the normal server with the real provider runners.
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createNodeSpawner, nodeFileSystem } from "@caztor/adapters-local";
import type { AgentEvent, AgentRunnerPort, ProviderId, TurnRequest } from "@caztor/core";
import { nodeListen } from "../apps/server-local/src/node-listen.ts";
import { startServer } from "../apps/server-local/src/server.ts";

const projectDir = resolve(process.argv[2] ?? ".");
const pause = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));

function write(path: string, text: string): void {
  const file = join(projectDir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}

/** Plays a script chosen by words in the prompt. `granular` runners send token deltas, the others whole parts. */
function scripted(provider: ProviderId, granular: boolean): AgentRunnerPort {
  async function* run(req: TurnRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    const said = (word: string) => req.prompt.toLowerCase().includes(word);
    const speak = async function* (id: string, text: string): AsyncGenerator<AgentEvent> {
      if (!granular) {
        yield { type: "text", messageId: id, text };
        return;
      }
      for (let i = 0; i < text.length; i += 6) {
        yield { type: "text_delta", messageId: id, text: text.slice(i, i + 6) };
        await pause(15);
      }
    };
    if (said("error")) {
      yield { type: "error", code: "auth", message: "The provider says you are not signed in.", detail: "HTTP 401 from the fake provider" };
      yield { type: "done", reason: "failed" };
      return;
    }
    if (said("slow")) {
      yield* speak("m1", "Working on it, this takes a while.");
      yield { type: "tool_start", toolId: "slow1", name: "Read", kind: "read", path: "main.tex" };
      await new Promise<void>((done) => (signal.aborted ? done() : signal.addEventListener("abort", () => done(), { once: true })));
      yield { type: "done", reason: "cancelled" };
      return;
    }
    yield* speak("m1", "I will update the **title** in `main.tex`, then add a note.\n\n```latex\n\\title{Better title}\n```\n");
    yield { type: "tool_start", toolId: "t1", name: "Edit", kind: "edit", path: "main.tex" };
    await pause(200);
    if (said("two files")) write("extra.tex", `% extra edited by ${provider}\n`);
    write("main.tex", `\\documentclass{article}\n\\title{Better title ${Date.now()}}\n\\begin{document}\nHello.\n\\end{document}\n`);
    yield { type: "tool_update", toolId: "t1", title: "Replaced the title" };
    yield { type: "tool_end", toolId: "t1", status: "done", summary: "1 change" };
    yield* speak("m2", "Done. The title is updated.");
    yield { type: "done", reason: "completed", usage: { costUsd: 0 } };
  }
  return {
    provider,
    isolation: "fake",
    async detect() {
      return { provider, installed: true, version: "0.0-fake", requiresModel: provider === "opencode" };
    },
    runTurn: run,
  };
}

const real = process.env["CAZTOR_E2E_REAL"] === "1";
// With CAZTOR_E2E_ARGV_LOG=<file> every spawn is recorded (argv, environment variable names, working folder, prompt length).
const argvLog = process.env["CAZTOR_E2E_ARGV_LOG"];
const nodeSpawner = createNodeSpawner();
const recording = {
  spawn(spec: Parameters<typeof nodeSpawner.spawn>[0]) {
    if (argvLog !== undefined) {
      appendFileSync(argvLog, `${JSON.stringify({ file: spec.file.split("/").at(-1), args: spec.args, envNames: Object.keys(spec.env), cwd: spec.cwd, stdinChars: spec.stdin?.length ?? 0 })}\n`);
    }
    return nodeSpawner.spawn(spec);
  },
};
const server = await startServer({
  projectDir,
  webRoot: fileURLToPath(new URL("../apps/web/dist", import.meta.url)),
  env: process.env,
  fs: nodeFileSystem,
  listen: nodeListen,
  spawner: recording,
  ...(real ? {} : { runners: { claude: scripted("claude", true), opencode: scripted("opencode", false), antigravity: scripted("antigravity", false), pi: scripted("pi", true) } }),
});
console.log(`Caztor is running at ${server.url} for ${server.root}`);
const stop = () => void server.close().then(() => process.exit(0));
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
