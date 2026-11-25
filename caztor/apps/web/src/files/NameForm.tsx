import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

interface NameFormProps {
  /** Accessible name of the text box. */
  label: string;
  initial?: string;
  submitLabel: string;
  /** Resolves to an error message to show in the form, or null when the operation worked. */
  onSubmit: (name: string) => Promise<string | null>;
  onCancel: () => void;
  /** A short line above the box, such as where a new file will be created. */
  caption?: string;
}

/** A single file or folder name is never a path: it cannot contain a separator. */
export function validateEntryName(raw: string): string | null {
  const name = raw.trim();
  if (name === "") return "Enter a name.";
  if (/[/\\]/.test(name)) return "Names cannot contain / or \\.";
  return null;
}

/** The inline form used to name a new entry or rename an existing one. Enter confirms, Escape cancels. */
export function NameForm({ label, initial = "", submitLabel, onSubmit, onCancel, caption }: NameFormProps) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (busy) return;
    const invalid = validateEntryName(value);
    if (invalid !== null) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(await onSubmit(value.trim()));
    setBusy(false);
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCancel();
    }
  }

  return (
    <form className="name-form" onSubmit={(event) => void submit(event)} onKeyDown={onKeyDown}>
      {caption === undefined ? null : <p className="name-form__caption">{caption}</p>}
      <input
        ref={input}
        className="text-input"
        aria-label={label}
        value={value}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="name-form__buttons">
        <button type="submit" className="button button--primary" disabled={busy}>
          {submitLabel}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error === null ? null : (
        <p role="alert" className="name-form__error">
          {error}
        </p>
      )}
    </form>
  );
}
