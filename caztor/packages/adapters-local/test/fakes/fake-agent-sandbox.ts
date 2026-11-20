import type { AgentSandbox } from "../../src/agent-sandbox.ts";
import type { SpawnSpec } from "../../src/infra.ts";

/**
 * An agent sandbox that records what it was asked for and wraps a spec as `bwrap -- <file> <args>`, keeping the
 * environment as the runner built it. With `refuse` set, every wrapper is refused with that reason.
 */
export function fakeAgentSandbox(options: { refuse?: string } = {}) {
  const asked: Array<{ binary: string; home: string }> = [];
  const wrapped: SpawnSpec[] = [];
  const sandbox: AgentSandbox = {
    async wrapper(input) {
      asked.push(input);
      if (options.refuse !== undefined) return { ok: false, reason: options.refuse };
      return {
        ok: true,
        value: (spec) => {
          wrapped.push(spec);
          return { ...spec, file: "/usr/bin/bwrap", args: ["--", spec.file, ...spec.args] };
        },
      };
    },
  };
  return { sandbox, asked, wrapped };
}
