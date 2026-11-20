import type { ProviderId } from "@caztor/core";
import { Icon } from "../components/Icon.tsx";
import { PROVIDER_META } from "./providers.ts";
import "./ProviderUnavailable.css";

interface ProviderUnavailableProps {
  provider: ProviderId;
  /** The server's reason. */
  reason: string;
  checking: boolean;
  onRecheck: () => void;
}

/** Shown in place of the conversation tools when the chosen provider's CLI is missing or unusable. */
export function ProviderUnavailable({ provider, reason, checking, onRecheck }: ProviderUnavailableProps) {
  const meta = PROVIDER_META[provider];
  return (
    <div className="provider-unavailable">
      <h3 className="provider-unavailable__title">{meta.name} is not available</h3>
      <p className="provider-unavailable__reason">{reason}</p>
      <p className="provider-unavailable__hint">
        Install the <code>{meta.command}</code> command-line tool, make sure it can be started from a terminal, then check again. You can use another provider in the meantime.
      </p>
      <button type="button" className="button" disabled={checking} onClick={onRecheck}>
        <Icon name="refresh" />
        {checking ? "Checking" : "Check again"}
      </button>
    </div>
  );
}
