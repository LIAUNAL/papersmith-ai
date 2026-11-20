import type { ContentHash } from "./ports.ts";

/** SHA-256 of the raw bytes, formatted as `sha256:<lowercase hex>`. Uses Web Crypto only. */
export async function hashBytes(bytes: Uint8Array): Promise<ContentHash> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes as Uint8Array<ArrayBuffer>));
  let hex = "";
  for (const byte of digest) hex += byte.toString(16).padStart(2, "0");
  return `sha256:${hex}`;
}
