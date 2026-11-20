import { useState } from "react";
import type { Capability, Settings } from "../api/types.ts";
import "./CompileOptions.css";

interface CompileOptionsProps {
  settings: Settings;
  /** Whether the OS sandbox can be used on this machine, and why not. */
  sandbox: Capability;
  /** Saves a change; resolves to a readable message when it failed. */
  onChange: (patch: Partial<Settings>) => Promise<string | null>;
}

/** The switches next to the compile button, remembered per project by the server. The sandbox switch needs a usable sandbox. */
export function CompileOptions({ settings, sandbox, onChange }: CompileOptionsProps) {
  const [problem, setProblem] = useState<string | null>(null);

  async function change(patch: Partial<Settings>): Promise<void> {
    setProblem(await onChange(patch));
  }

  return (
    <div className="compile-options">
      <label className="compile-options__switch">
        <input type="checkbox" checked={settings.stopOnFirstError} onChange={(event) => void change({ stopOnFirstError: event.target.checked })} />
        Stop on first error
      </label>
      <label className="compile-options__switch">
        <input type="checkbox" checked={settings.autoCompile} onChange={(event) => void change({ autoCompile: event.target.checked })} />
        Auto-compile
      </label>
      {sandbox.available || settings.sandboxedCompile ? (
        <label className="compile-options__switch">
          <input type="checkbox" checked={settings.sandboxedCompile} onChange={(event) => void change({ sandboxedCompile: event.target.checked })} />
          Sandboxed compile (experimental)
        </label>
      ) : null}
      {!sandbox.available && settings.sandboxedCompile ? (
        <p className="compile-options__problem">{sandbox.reason ?? "The sandbox is not available on this machine."} Turn the option off to compile without it.</p>
      ) : null}
      {problem === null ? null : (
        <p role="alert" className="compile-options__problem">
          {problem}
        </p>
      )}
    </div>
  );
}
