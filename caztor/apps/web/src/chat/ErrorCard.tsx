import { useId, useState } from "react";
import type { TurnErrorCode } from "@caztor/core";
import { Icon } from "../components/Icon.tsx";
import { HintText } from "./LoginHint.tsx";
import "./ErrorCard.css";

export type ErrorCode = TurnErrorCode | "connection_lost";

const HELP: Record<ErrorCode, { title: string; action: string }> = {
  not_installed: { title: "The provider is not installed", action: "Install its command-line tool, then check again from the provider header." },
  auth: { title: "The provider needs you to sign in", action: "Sign in to the provider in a terminal, then send your message again." },
  model_unavailable: { title: "The model is not available", action: "Choose another model in the header, or clear it to use the default." },
  model_required: { title: "A model is required", action: "Choose a model in the header before sending a message." },
  rate_limited: { title: "The provider is limiting requests", action: "Wait a little, then send your message again." },
  permission_denied: { title: "The provider was not allowed to do that", action: "Ask for something that only needs to read and edit your project files." },
  isolation_failed: { title: "Caztor could not keep the assistant isolated", action: "No message was processed. Review the project's assistant configuration, then try again." },
  snapshot_failed: { title: "Caztor could not protect your files first", action: "Nothing was changed. Free some disk space or check the project folder, then try again." },
  malformed_output: { title: "The provider answered in a way Caztor cannot read", action: "Try again. If it keeps happening, update the provider's command-line tool." },
  timeout: { title: "The provider took too long", action: "Try again with a smaller request." },
  mode_unsupported: { title: "This provider cannot use that sign-in", action: "Switch the provider to its account sign-in, then send your message again." },
  provider_error: { title: "The provider reported a problem", action: "Try again. The details below may help you if it keeps happening." },
  connection_lost: { title: "The connection to Caztor was lost", action: "Reload the page to see where the assistant got to." },
};

/** How the provider was signed in when the turn ran, so an authentication failure can name the right fix. */
export interface SignInContext {
  mode: "account" | "api";
  /** The terminal step that signs in to the provider's CLI. */
  loginHint: string;
}

interface ErrorCardProps {
  code: ErrorCode;
  message: string;
  detail?: string;
  signIn?: SignInContext;
}

/** A failed turn in plain language: what happened, what to do next, and the raw detail only when asked. */
export function ErrorCard({ code, message, detail, signIn }: ErrorCardProps) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const help = HELP[code];
  return (
    <div className="error-card" role="alert">
      <div className="error-card__head">
        <Icon name="alert" className="error-card__icon" />
        <h3 className="error-card__title">{help.title}</h3>
      </div>
      <p className="error-card__message">{message}</p>
      {code === "auth" && signIn?.mode === "api" ? (
        <p className="error-card__action">Check the API key in the sign-in settings above, then send your message again.</p>
      ) : code === "auth" && signIn?.mode === "account" ? (
        <p className="error-card__action">
          <HintText text={signIn.loginHint} /> Then send your message again.
        </p>
      ) : (
        <p className="error-card__action">{help.action}</p>
      )}
      {detail === undefined || detail === "" ? null : (
        <>
          <button type="button" className="error-card__toggle" aria-expanded={open} aria-controls={detailId} onClick={() => setOpen(!open)}>
            {open ? "Hide details" : "Show details"}
          </button>
          {open ? (
            <pre id={detailId} className="error-card__detail">
              {detail}
            </pre>
          ) : null}
        </>
      )}
    </div>
  );
}
