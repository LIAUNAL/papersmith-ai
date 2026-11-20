import { useEffect, useId, useState } from "react";
import type { ProviderInfo } from "../api/types.ts";
import "./ModelSelect.css";

interface ModelSelectProps {
  provider: ProviderInfo;
  /** A turn is running: the model cannot change now. */
  disabled: boolean;
  /** Saves the model (null clears it) and answers the readable reason when the server refuses it. */
  onChange: (model: string | null) => Promise<string | null>;
}

/** The model of the active provider: a list when the CLI knows its models, else a text box saved with Enter or Set. */
export function ModelSelect({ provider, disabled, onChange }: ModelSelectProps) {
  const [text, setText] = useState(provider.model ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const hintId = useId();
  useEffect(() => {
    setText(provider.model ?? "");
    setProblem(null);
  }, [provider.id, provider.model]);

  async function save(model: string | null): Promise<void> {
    setProblem(await onChange(model));
  }

  const missing = provider.requiresModel && provider.model === null;
  const listed = provider.models !== undefined && provider.models.length > 0;
  // A provider that names its default shows that model instead of a separate "Default" entry.
  const shown = provider.model ?? provider.defaultModel ?? null;
  const hint = missing ? `${provider.id} needs a model before it can start a turn.` : null;

  return (
    <div className="model-select">
      {listed ? (
        <select
          className="model-select__control"
          aria-label="Model"
          aria-describedby={hint === null ? undefined : hintId}
          disabled={disabled}
          value={shown ?? ""}
          onChange={(event) => void save(event.target.value === "" ? null : event.target.value)}
        >
          {provider.defaultModel === undefined ? <option value="">{provider.requiresModel ? "Choose a model" : "Default"}</option> : null}
          {shown !== null && !provider.models!.includes(shown) ? <option value={shown}>{shown}</option> : null}
          {provider.models!.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
      ) : (
        <form
          className="model-select__form"
          onSubmit={(event) => {
            event.preventDefault();
            void save(text.trim() === "" ? null : text.trim());
          }}
        >
          <input
            className="text-input model-select__control"
            type="text"
            aria-label="Model"
            aria-describedby={hint === null ? undefined : hintId}
            placeholder={provider.requiresModel ? "Model (required)" : "Model (default)"}
            spellCheck={false}
            autoComplete="off"
            disabled={disabled}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" className="button model-select__set" aria-label="Set model" disabled={disabled || text.trim() === (provider.model ?? "")}>
            Set
          </button>
        </form>
      )}
      {hint === null ? null : (
        <p id={hintId} className="model-select__hint">
          {hint}
        </p>
      )}
      {problem === null ? null : (
        <p role="alert" className="model-select__problem">
          {problem}
        </p>
      )}
    </div>
  );
}
