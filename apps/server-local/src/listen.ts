/** The address the server binds unless the host exposes it with `--host` (which then needs a public name). */
export const LOOPBACK = "127.0.0.1";
export const DEFAULT_PORT = 4317;
/** How many consecutive ports are tried before giving up. */
export const MAX_PORT_ATTEMPTS = 20;

/** `env` is what the Node adapter passes along (the incoming socket, for the remote address). */
export type FetchHandler = (request: Request, env?: unknown) => Response | Promise<Response>;

export interface Listener {
  /** The port actually bound. */
  port: number;
  close(): Promise<void>;
}

/** Starts an HTTP listener. Rejects with an error whose `code` is `EADDRINUSE` when the port is taken. */
export type ListenFn = (options: { port: number; hostname: string; fetch: FetchHandler }) => Promise<Listener>;

function isAddressInUse(error: unknown): boolean {
  return (error as { code?: string } | null)?.code === "EADDRINUSE";
}

/** Binds `hostname` (loopback by default) on `startPort`, then on each following port while the previous one is busy. */
export async function bindWithFallback(
  listen: ListenFn,
  fetch: FetchHandler,
  startPort: number = DEFAULT_PORT,
  hostname: string = LOOPBACK,
): Promise<Listener> {
  for (let attempt = 0; attempt < MAX_PORT_ATTEMPTS; attempt += 1) {
    try {
      return await listen({ port: startPort + attempt, hostname, fetch });
    } catch (error) {
      if (!isAddressInUse(error)) throw error;
    }
  }
  throw new Error(`No free port found from ${startPort} to ${startPort + MAX_PORT_ATTEMPTS - 1}.`);
}
