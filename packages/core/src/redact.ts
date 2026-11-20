/** The text that replaces a secret wherever it would have been shown, stored or logged. */
export const REDACTION_MASK = "[redacted]";
/** Shorter secrets are not masked: a short value would also hide ordinary words and corrupt the text. */
export const MIN_SECRET_LENGTH = 8;

/** Replaces every occurrence of every secret in `text` with the mask. Secrets are plain text, longest first. */
export function redactSecrets(text: string, secrets: readonly string[]): string {
  const usable = secrets.filter((secret) => secret.length >= MIN_SECRET_LENGTH).sort((a, b) => b.length - a.length);
  let out = text;
  for (const secret of usable) out = out.split(secret).join(REDACTION_MASK);
  return out;
}

/** Scrubs every string inside a value (objects and arrays included) and returns a copy; the input is not changed. */
export function redactValue<T>(value: T, secrets: readonly string[]): T {
  if (typeof value === "string") return redactSecrets(value, secrets) as T;
  if (Array.isArray(value)) return value.map((item: unknown) => redactValue(item, secrets)) as T;
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) out[key] = redactValue(item, secrets);
    return out as T;
  }
  return value;
}
