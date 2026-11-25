import { Fragment, useRef, type KeyboardEvent } from "react";
import type { ProviderId } from "@caztor/core";
import type { ProviderInfo } from "../api/types.ts";
import { ProviderLogo } from "./ProviderLogo.tsx";
import { EXTRA_PROVIDER_ORDER, PROVIDER_META, PROVIDER_ORDER } from "./providers.ts";
import "./ProviderSelect.css";

interface ProviderSelectProps {
  providers: ProviderInfo[];
  selected: ProviderId | null;
  /** The provider cannot be changed now (a turn is running). */
  disabled: boolean;
  onSelect: (provider: ProviderId) => void;
}

/**
 * The main providers as one radio group of names: arrow keys move the choice among them, only the selected one is in
 * the tab order. The other providers follow in a "More providers" dropdown; while one of them is active it shows there
 * and no radio is checked. An unavailable provider can be chosen, so its reason and the re-check are shown, but it
 * cannot start a turn.
 */
export function ProviderSelect({ providers, selected, disabled, onSelect }: ProviderSelectProps) {
  const refs = useRef(new Map<ProviderId, HTMLButtonElement>());
  const listed = PROVIDER_ORDER.flatMap((id) => providers.filter((provider) => provider.id === id));
  const extras = EXTRA_PROVIDER_ORDER.flatMap((id) => providers.filter((provider) => provider.id === id));
  const extraSelected = extras.some((provider) => provider.id === selected);
  const mainSelected = listed.some((provider) => provider.id === selected);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (step === 0 || disabled || listed.length === 0) return;
    event.preventDefault();
    const at = listed.findIndex((provider) => provider.id === selected);
    const next = listed[(at + step + listed.length) % listed.length]!;
    onSelect(next.id);
    refs.current.get(next.id)?.focus();
  }

  return (
    <div className="provider-select-row">
      <div className="provider-select" role="radiogroup" aria-label="Provider" onKeyDown={onKeyDown}>
        {listed.map((provider) => {
          const checked = provider.id === selected;
          const note = provider.installed ? null : (provider.unavailableReason ?? "Not installed.");
          return (
            <Fragment key={provider.id}>
            <button
              ref={(element) => {
                if (element === null) refs.current.delete(provider.id);
                else refs.current.set(provider.id, element);
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-describedby={note === null ? undefined : `provider-note-${provider.id}`}
              tabIndex={checked || (!mainSelected && provider === listed[0]) ? 0 : -1}
              disabled={disabled}
              className={`provider-select__option${checked ? " provider-select__option--checked" : ""}${note === null ? "" : " provider-select__option--unavailable"}`}
              onClick={() => onSelect(provider.id)}
            >
              <ProviderLogo provider={provider.id} />
              {note === null ? null : <span className="provider-select__flag" aria-hidden="true" />}
            </button>
            {note === null ? null : (
              <span id={`provider-note-${provider.id}`} className="visually-hidden">
                {note}
              </span>
            )}
            </Fragment>
          );
        })}
      </div>
      {extras.length === 0 ? null : (
        <select
          className={`provider-select__more${extraSelected ? " provider-select__more--checked" : ""}`}
          aria-label="More providers"
          value={extraSelected ? (selected as ProviderId) : ""}
          disabled={disabled}
          onChange={(event) => {
            const chosen = extras.find((provider) => provider.id === event.target.value);
            if (chosen !== undefined) onSelect(chosen.id);
          }}
        >
          <option value="" disabled>
            More
          </option>
          {extras.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {PROVIDER_META[provider.id].name}
              {provider.installed ? "" : " (not available)"}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
