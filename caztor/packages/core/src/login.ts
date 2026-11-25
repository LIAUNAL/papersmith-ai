import type { TurnUser } from "./people.ts";
import type { ProviderId, Result } from "./ports.ts";

/** Keys a person can press in a sign-in that runs in a terminal (a CLI menu). */
export const LOGIN_KEYS = ["enter", "up", "down", "escape", "tab"] as const;
export type LoginKey = (typeof LOGIN_KEYS)[number];

/** `signed_in`: the CLI finished the sign-in. The others end it without one. */
export type LoginSessionState = "running" | "signed_in" | "failed" | "cancelled" | "timed_out";

/** What the browser shows of a sign-in: the CLI's text with secrets masked, and the device code when it printed one. */
export interface LoginView {
  provider: ProviderId;
  method: string;
  state: LoginSessionState;
  /** The CLI's output as plain text (terminal codes removed), last lines kept. */
  text: string;
  /** A one-time code the CLI printed for the person to enter on a web page, such as `ABCD-1234`. */
  code?: string;
  /** The CLI runs in a terminal: menu keys work, and a line is sent with Enter. */
  terminal: boolean;
  /** Why it ended, when it ended without a sign-in. */
  message?: string;
}

/** A way to sign in to one provider's CLI. */
export interface LoginMethod {
  id: string;
  label: string;
}

export type LoginStartError = { code: "unknown_method" | "not_installed" | "isolation_failed" | "unavailable"; message: string };
export type LoginInputError = { code: "not_found" | "ended" | "invalid_input"; message: string };

/** The longest line a person may send to a sign-in. A pasted code or URL is far shorter. */
export const MAX_LOGIN_INPUT = 2048;

/**
 * Sign-ins to the providers' CLIs from the browser: one at a time per person, seen only by them. A collaborator's runs
 * inside their sandbox with their private home; the host's runs as the host would in a terminal.
 */
export interface LoginRelayPort {
  methods(provider: ProviderId): LoginMethod[];
  /** Starts a sign-in, ending any other of the same person. */
  start(user: TurnUser, provider: ProviderId, method?: string): Promise<Result<LoginView, LoginStartError>>;
  /** The person's sign-in to this provider, or null. Looking at it keeps it alive. */
  view(user: TurnUser, provider: ProviderId): LoginView | null;
  send(user: TurnUser, provider: ProviderId, input: { line: string } | { key: LoginKey }): Result<LoginView, LoginInputError>;
  /** Ends the person's sign-in to this provider. False when there was none. */
  cancel(user: TurnUser, provider: ProviderId): boolean;
  /** Ends every sign-in. */
  close(): Promise<void>;
}
