import type { CredentialError, CredentialReaderPort, Result } from "@caztor/core";

export interface FakeReader extends CredentialReaderPort {
  /** Every slot that was asked for, in order. */
  reads: string[];
}

/** A key reader over fixed fake keys; `refuse` makes every read fail as a store would. */
export function fakeReader(keys: Record<string, string>, refuse?: CredentialError): FakeReader {
  const reads: string[] = [];
  return {
    reads,
    async read(slot): Promise<Result<string | null, CredentialError>> {
      reads.push(slot);
      if (refuse !== undefined) return { ok: false, error: refuse };
      return { ok: true, value: keys[slot] ?? null };
    },
  };
}
