/** Largest upload the server accepts. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/**
 * Why a file cannot be uploaded to `destination`, or null when it can. Checked before sending, so a rejected
 * file costs no transfer; the server repeats both checks.
 */
export function uploadProblem(file: { name: string; size: number }, destination: string, existing: ReadonlySet<string>): string | null {
  if (file.size > MAX_UPLOAD_BYTES) return `${file.name} is larger than ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB and was not uploaded.`;
  if (existing.has(destination)) return `"${destination}" already exists. Choose another name.`;
  return null;
}
