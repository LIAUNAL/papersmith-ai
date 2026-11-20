import { useId, useState, type FormEvent } from "react";
import type { ProviderAuth } from "../api/types.ts";
import "./KeyForm.css";

interface KeyFormProps {
  auth: ProviderAuth;
  /** The name of the provider, for the labels. */
  providerName: string;
  disabled: boolean;
  /** Stores the key and answers the readable reason when it cannot. */
  onSave: (slot: string, key: string) => Promise<string | null>;
  onDelete: (slot: string) => Promise<string | null>;
}

/** Removes the key from a message, in case a server or a provider repeated it. */
function scrub(message: string, key: string): string {
  return key === "" ? message : message.split(key).join("[redacted]");
}

/**
 * A write-only form for the provider's API key. It shows only whether a key is set and its last four characters, the
 * field is never filled in, and what was typed is cleared the moment it is submitted, whether the save works or not.
 */
export function KeyForm({ auth, providerName, disabled, onSave, onDelete }: KeyFormProps) {
  const [key, setKey] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();
  const slot = auth.slot;
  const status = slot === null ? undefined : auth.keys.find((candidate) => candidate.slot === slot);
  const isSet = status?.set === true;
  const vendor = slot?.startsWith("opencode:") === true ? slot.slice("opencode:".length) : null;
  const unusable = auth.storeProblem !== undefined;

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (slot === null || key === "" || busy) return;
    const submitted = key;
    // The key leaves the page before anything is awaited.
    setKey("");
    setBusy(true);
    setProblem(null);
    const failure = await onSave(slot, submitted);
    setBusy(false);
    setProblem(failure === null ? null : scrub(failure, submitted));
  }

  async function remove(): Promise<void> {
    if (slot === null || busy) return;
    setBusy(true);
    setProblem(null);
    const failure = await onDelete(slot);
    setBusy(false);
    setProblem(failure);
  }

  if (slot === null) {
    return (
      <div className="key-form">
        <p className="key-form__hint">{auth.slotProblem ?? `${providerName} needs a model before a key can be chosen.`}</p>
      </div>
    );
  }

  return (
    <form className="key-form" onSubmit={(event) => void submit(event)} aria-label={`${providerName} API key`}>
      <div className="key-form__summary">
        <p className="key-form__status">
          {vendor === null ? null : <span>{`Key for ${vendor}: `}</span>}
          {isSet ? (
            <span className="key-form__set">
              Key set{status?.last4 === undefined ? "" : <> ending in <code>{status.last4}</code></>}
            </span>
          ) : (
            <span className="key-form__unset">No key set</span>
          )}
        </p>
        {isSet ? (
          <button type="button" className="button key-form__delete" disabled={disabled || unusable || busy} onClick={() => void remove()}>
            Delete key
          </button>
        ) : null}
      </div>
      {isSet ? null : (
        <p className="key-form__hint">{vendor === null ? `Add an API key to use ${providerName} without an account sign-in.` : `Add an API key to use ${vendor} models.`}</p>
      )}
      <label className="visually-hidden" htmlFor={fieldId}>
        API key
      </label>
      <div className="key-form__row">
        <input
          id={fieldId}
          className="text-input key-form__field"
          type="password"
          value={key}
          autoComplete="off"
          spellCheck={false}
          placeholder={isSet ? "Paste a new key" : "Paste a key"}
          disabled={disabled || unusable || busy}
          onChange={(event) => setKey(event.target.value)}
        />
        <button type="submit" className="button button--primary" disabled={disabled || unusable || busy || key === ""}>
          {isSet ? "Replace key" : "Save key"}
        </button>
      </div>
      {unusable ? (
        <p role="alert" className="key-form__problem">
          {auth.storeProblem}
        </p>
      ) : null}
      {problem === null ? null : (
        <p role="alert" className="key-form__problem">
          {problem}
        </p>
      )}
    </form>
  );
}
