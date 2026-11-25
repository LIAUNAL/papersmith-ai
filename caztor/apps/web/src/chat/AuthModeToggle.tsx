import { useId, useState } from "react";
import type { AuthMode, ProviderAuth } from "../api/types.ts";
import "./AuthModeToggle.css";

interface AuthModeToggleProps {
  auth: ProviderAuth;
  /** A turn is running: the sign-in method cannot change now. */
  disabled: boolean;
  /** Asks the server to switch and answers the readable reason when it refuses. */
  onChange: (mode: AuthMode) => Promise<string | null>;
  /** API was chosen but no key is stored: the key form is shown instead of switching. */
  onNeedKey: () => void;
}

const LABELS: Record<AuthMode, string> = { account: "Account", api: "API key" };

/**
 * How the active provider signs in. A provider without API access shows account only. An API choice that has no key
 * behind it is marked not configured and asks for a key instead of switching.
 */
export function AuthModeToggle({ auth, disabled, onChange, onNeedKey }: AuthModeToggleProps) {
  const [problem, setProblem] = useState<string | null>(null);
  const noteId = useId();
  const offered = auth.modes.length > 0 ? auth.modes : (["account"] as AuthMode[]);

  async function choose(mode: AuthMode): Promise<void> {
    setProblem(null);
    if (mode === auth.mode) {
      if (mode === "api") onNeedKey();
      return;
    }
    if (mode === "api" && !auth.apiReady) {
      onNeedKey();
      return;
    }
    setProblem(await onChange(mode));
  }

  return (
    <div className="auth-toggle">
      <div className="auth-toggle__group" role="group" aria-label="Sign-in method">
        {offered.map((mode) => {
          const notConfigured = mode === "api" && !auth.apiReady;
          const checked = mode === auth.mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-describedby={notConfigured ? noteId : undefined}
              disabled={disabled}
              className={`auth-toggle__option${checked ? " auth-toggle__option--checked" : ""}`}
              onClick={() => void choose(mode)}
            >
              {LABELS[mode]}
              {notConfigured ? (
                <span id={noteId} className="auth-toggle__tag" aria-hidden="true">
                  Not configured
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      {offered.length === 1 ? <p className="auth-toggle__note">This provider signs in with its account only.</p> : null}
      {problem === null ? null : (
        <p role="alert" className="auth-toggle__problem">
          {problem}
        </p>
      )}
    </div>
  );
}
