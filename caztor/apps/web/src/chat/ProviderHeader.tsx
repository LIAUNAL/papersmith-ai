import type { ProviderId } from "@caztor/core";
import type { AuthMode, ProviderInfo, ProvidersListing } from "../api/types.ts";
import { Icon } from "../components/Icon.tsx";
import { AuthPanel } from "./AuthPanel.tsx";
import type { LoginApi } from "./controller.ts";
import { ModelSelect } from "./ModelSelect.tsx";
import { ProviderLogo } from "./ProviderLogo.tsx";
import { ProviderSelect } from "./ProviderSelect.tsx";
import "./ProviderHeader.css";

interface ProviderHeaderProps {
  listing: ProvidersListing;
  /** A turn is running: the provider, the model and the conversation cannot change now. */
  running: boolean;
  onSelect: (provider: ProviderId) => void;
  onModel: (provider: ProviderId, model: string | null) => Promise<string | null>;
  onAuthMode: (provider: ProviderId, mode: AuthMode) => Promise<string | null>;
  onSaveKey: (slot: string, key: string) => Promise<string | null>;
  onDeleteKey: (slot: string) => Promise<string | null>;
  onNewChat: () => void;
  login?: { api: LoginApi; pollMs: number; onEnded: () => void } | undefined;
}

/** The top of the chat pane: the active provider's logo, its state, the provider and model choices, and New chat. */
export function ProviderHeader({ listing, running, onSelect, onModel, onAuthMode, onSaveKey, onDeleteKey, onNewChat, login }: ProviderHeaderProps) {
  const active: ProviderInfo | undefined = listing.providers.find((provider) => provider.id === listing.selected);
  return (
    <div className="provider-header" role="group" aria-label="Assistant">
      <div className="provider-header__top">
        <div className="provider-header__identity">
          {active === undefined ? null : <ProviderLogo provider={active.id} size="large" />}
          {active === undefined ? null : (
            <span
              className={`provider-header__state${active.installed ? "" : " provider-header__state--off"}`}
              {...(active.version === undefined ? {} : { title: `Version ${active.version}` })}
            >
              {active.installed ? "Ready" : "Not available"}
            </span>
          )}
        </div>
        <button type="button" className="button provider-header__new" disabled={running || active === undefined} onClick={onNewChat}>
          <Icon name="plus" />
          New chat
        </button>
      </div>
      <div className="provider-header__choices">
        <ProviderSelect providers={listing.providers} selected={listing.selected} disabled={running} onSelect={onSelect} />
        {active === undefined || !active.installed || active.supportsModel === false ? null : <ModelSelect provider={active} disabled={running} onChange={(model) => onModel(active.id, model)} />}
      </div>
      {active === undefined || !active.installed ? null : <AuthPanel provider={active} running={running} onMode={onAuthMode} onSaveKey={onSaveKey} onDeleteKey={onDeleteKey} login={login} />}
      {active?.versionWarning === undefined ? null : <p className="provider-header__warning">{active.versionWarning}</p>}
      {active?.note === undefined ? null : <p className="provider-header__note">{active.note}</p>}
      {active?.id !== "codex" ? null : (
        <p role="note" aria-label="Codex runs commands" className="provider-header__warning">
          Codex can run commands on this computer inside its own sandbox, which limits where it can write. Caztor cannot turn this off.
        </p>
      )}
    </div>
  );
}
