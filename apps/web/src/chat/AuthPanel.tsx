import { useEffect, useState } from "react";
import type { AuthMode, ProviderInfo } from "../api/types.ts";
import { AuthModeToggle } from "./AuthModeToggle.tsx";
import type { LoginApi } from "./controller.ts";
import { KeyForm } from "./KeyForm.tsx";
import { LoginDialog } from "./LoginDialog.tsx";
import { LoginHint } from "./LoginHint.tsx";
import { PROVIDER_META } from "./providers.ts";
import "./AuthPanel.css";

interface AuthPanelProps {
  provider: ProviderInfo;
  /** A turn is running: nothing here can change now. */
  running: boolean;
  onMode: (provider: ProviderInfo["id"], mode: AuthMode) => Promise<string | null>;
  onSaveKey: (slot: string, key: string) => Promise<string | null>;
  onDeleteKey: (slot: string) => Promise<string | null>;
  /** Signing in from the browser, when the server offers it. */
  login?: { api: LoginApi; pollMs: number; onEnded: () => void } | undefined;
}

/** How the active provider signs in: the toggle, the login hint in account mode, and the masked key form in API mode. Folded once there is nothing left to do, because the chat header is narrow. */
export function AuthPanel({ provider, running, onMode, onSaveKey, onDeleteKey, login }: AuthPanelProps) {
  const auth = provider.auth;
  const [askingForKey, setAskingForKey] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [unfolded, setUnfolded] = useState(false);
  useEffect(() => setAskingForKey(false), [provider.id, auth?.mode]);
  useEffect(() => setUnfolded(false), [provider.id]);
  useEffect(() => setSigningIn(false), [provider.id]);
  if (auth === undefined) return null;
  const showKey = auth.mode === "api" || (askingForKey && auth.modes.includes("api"));
  const configured = !askingForKey && auth.storeProblem === undefined && auth.slotProblem === undefined && (auth.mode === "api" ? auth.apiReady : auth.login === "signed_in");
  return (
    <>
      <details
        className="auth-panel"
        open={unfolded || !configured}
        onToggle={(event) => {
          if (configured) setUnfolded(event.currentTarget.open);
        }}
      >
        <summary className="auth-panel__summary">Sign-in: {auth.mode === "api" ? "API key" : "Account"}</summary>
        <AuthModeToggle auth={auth} disabled={running} onChange={(mode) => {
            setUnfolded(true);
            return onMode(provider.id, mode);
          }} onNeedKey={() => setAskingForKey(true)} />
        {showKey ? (
          <KeyForm auth={auth} providerName={PROVIDER_META[provider.id].name} disabled={running} onSave={onSaveKey} onDelete={onDeleteKey} />
        ) : auth.mode === "account" && auth.login !== "signed_in" ? (
          <div className="auth-panel__login">
            {login === undefined ? null : (
              <button type="button" className="button button--primary" disabled={running} onClick={() => setSigningIn(true)}>
                Sign in
              </button>
            )}
            <LoginHint hint={login === undefined ? auth.loginHint : `Or, on the host's computer: ${auth.loginHint}`} />
          </div>
        ) : null}
      </details>
      {/* Outside the panel: once signed in the panel folds, and the dialog must stay to say so. */}
      {signingIn && login !== undefined ? (
        <LoginDialog provider={provider.id} api={login.api} pollMs={login.pollMs} onEnded={login.onEnded} onClose={() => setSigningIn(false)} />
      ) : null}
    </>
  );
}
