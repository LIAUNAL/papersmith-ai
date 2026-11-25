/** Longest model name accepted. */
export const MAX_MODEL_LENGTH = 200;

const MODEL = /^[A-Za-z0-9._:/-]+$/;

/**
 * Validates a model name typed by the user before it is stored or placed on a command line. A name that starts with a
 * dash could be read as an option by the CLI, so it is refused; an empty value clears the setting (null).
 */
export function parseModel(value: unknown): { ok: true; value: string | null } | { ok: false; message: string } {
  if (value === null) return { ok: true, value: null };
  if (typeof value !== "string") return { ok: false, message: "The model must be text." };
  const model = value.trim();
  if (model === "") return { ok: true, value: null };
  if (model.length > MAX_MODEL_LENGTH) return { ok: false, message: `The model name is too long (the limit is ${MAX_MODEL_LENGTH} characters).` };
  if (model.startsWith("-")) return { ok: false, message: "The model name cannot start with a dash: a CLI could read it as an option." };
  if (!MODEL.test(model)) return { ok: false, message: "The model name can use only letters, digits and . _ : / -" };
  return { ok: true, value: model };
}
