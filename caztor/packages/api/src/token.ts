const TOKEN_BYTES = 32;
const MIN_ENV_TOKEN_LENGTH = 16;

/** 32 random bytes from the Web Crypto generator, as 64 lowercase hex characters. */
export function generateToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(TOKEN_BYTES));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Compares in time that depends on the longer input only, never on where the first difference is. */
export function timingSafeEqual(a: string, b: string): boolean {
  const left = new TextEncoder().encode(a);
  const right = new TextEncoder().encode(b);
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i += 1) difference |= (left[i] ?? 0) ^ (right[i] ?? 0);
  return difference === 0;
}

/**
 * The token for this launch. `CAZTOR_TOKEN` is honored only when `CAZTOR_DEV` is exactly `1`;
 * in production the token is generated, kept in memory and never read from the environment.
 */
export function resolveLaunchToken(
  env: Readonly<Record<string, string | undefined>>,
  generate: () => string = generateToken,
): string {
  const supplied = env["CAZTOR_TOKEN"];
  if (env["CAZTOR_DEV"] === "1" && supplied !== undefined && supplied.length >= MIN_ENV_TOKEN_LENGTH) return supplied;
  return generate();
}
