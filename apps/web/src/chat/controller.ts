import { chatReducer, INITIAL_CHAT_STATE, type ChatAction, type ChatState } from "@caztor/core";
import { ApiError } from "../api/client.ts";
import type { ApiClient, AuthMode, ProviderId, ProvidersListing, TurnEvent, TurnStreamRequest, UndoConflict, UndoMode } from "../api/types.ts";

type ChatApi = Pick<ApiClient, "listProviders" | "chatHistory" | "streamTurn" | "stopTurn" | "recheckProviders" | "selectProvider" | "setProviderModel" | "setAuthMode" | "saveCredential" | "deleteCredential" | "trustProjectConfig" | "resetChat" | "undoTurn" | "replaceDefinition"> &
  Partial<LoginApi> &
  Partial<Pick<ApiClient, "listAgents">>;

/** Signing in to a provider's CLI from the browser. */
export type LoginApi = Pick<ApiClient, "startLogin" | "followLogin" | "sendLogin" | "cancelLogin">;

export interface ChatControllerOptions {
  api: ChatApi;
  /** Pause between reconnection attempts. Tests replace it. */
  wait?: (ms: number) => Promise<void>;
  /** How often a browser sign-in is read again; tests make it short. */
  loginPollMs?: number;
}

/** Everything the chat pane draws. */
export interface ChatViewState {
  chat: ChatState;
  providers: ProvidersListing | null;
  loading: boolean;
  /** Why the providers or history could not be read. */
  loadError: string | null;
  /** The readable reason the last action was refused, shown above the composer. */
  problem: string | null;
  /** An undo that needs the user's decision: the files that changed after the turn. */
  undoChoice: { turnId: string; conflicts: UndoConflict[] } | null;
  /** Turns whose undo restored everything. */
  undone: string[];
  /** The providers are being detected again. */
  checking: boolean;
  /** The stream of the running turn dropped and is being re-opened. */
  reconnecting: boolean;
  /** What the user has typed and not sent, per provider. */
  drafts: Partial<Record<ProviderId, string>>;
}

/** The order in which an unchosen provider is picked. */
const FIRST_CHOICE: readonly ProviderId[] = ["claude", "opencode", "pi"];
const FIRST_RETRY_MS = 500;
const LONGEST_RETRY_MS = 5000;
const MAX_RECONNECTS = 8;
export const NEW_CHAT_NOTE = "New conversation started. The assistant does not remember the earlier one.";
const LOST_MESSAGE = "The connection to Caztor was lost. The assistant may still be working: reload the page to see where it got to.";

const list = (paths: string[]): string => paths.join(", ");

/** The note shown after an undo. Files that were left alone are named with the reasons they can have. */
function describeUndo(files: string[], skipped: string[], mode: UndoMode): string {
  const restored = files.length === 0 ? "No file was restored." : `Restored: ${list(files)}.`;
  if (skipped.length === 0) return `Undid the turn. ${restored}`;
  const why =
    mode === "skip_conflicts"
      ? "They were left as they are because you changed them after the turn, or because Caztor could not write them safely (for example a file or folder on its path is now a link)."
      : "Caztor left them as they are because it could not write them safely (for example a file or folder on its path is now a link).";
  return `The undo was only partial. ${restored} Not restored: ${list(skipped)}. ${why}`;
}

const messageOf = (error: unknown, fallback: string): string => (error instanceof Error && error.message !== "" ? error.message : fallback);

/** Holds the chat state, reads the turn's event stream and carries out send and stop. Read it with `useSyncExternalStore`. */
export class ChatController {
  private listingsShown = 0;
  private view: ChatViewState = { chat: INITIAL_CHAT_STATE, providers: null, loading: true, loadError: null, problem: null, checking: false, undoChoice: null, undone: [], reconnecting: false, drafts: {} };
  private readonly listeners = new Set<() => void>();
  private readonly api: ChatApi;
  private readonly wait: (ms: number) => Promise<void>;
  private stream: AbortController | null = null;
  private stopWanted = false;
  /** A provider shown as selected because the project never chose one; it is saved when the user acts. */
  private unsaved: ProviderId | null = null;

  constructor(options: ChatControllerOptions) {
    this.api = options.api;
    this.wait = options.wait ?? ((ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
    this.loginPollMs = options.loginPollMs ?? 1_000;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };

  getSnapshot = (): ChatViewState => this.view;

  /** Leaves the page: stops reading the stream. The turn itself keeps running on the server. */
  dispose(): void {
    this.stream?.abort();
    this.stream = null;
  }

  protected patch(change: Partial<ChatViewState>): void {
    this.view = { ...this.view, ...change };
    for (const listener of [...this.listeners]) listener();
  }

  protected dispatch(action: ChatAction): void {
    const chat = chatReducer(this.view.chat, action);
    if (chat !== this.view.chat) this.patch({ chat });
  }

  protected get provider(): ProviderId | null {
    return this.view.providers?.selected ?? null;
  }

  setDraft(provider: ProviderId, text: string): void {
    this.patch({ drafts: { ...this.view.drafts, [provider]: text } });
  }

  /** The project's own agents for the slash menu; none when they cannot be read. */
  async agents(): Promise<Array<{ name: string; description: string }>> {
    try {
      return (await this.api.listAgents?.()) ?? [];
    } catch {
      return [];
    }
  }

  /** Adds text to the shown provider's message box, after a blank line when something is typed already. False without a provider. */
  compose(text: string): boolean {
    const provider = this.provider;
    if (provider === null) return false;
    const typed = this.view.drafts[provider] ?? "";
    this.setDraft(provider, typed.trim() === "" ? text : `${typed.replace(/\s+$/, "")}\n\n${text}`);
    return true;
  }

  clearProblem(): void {
    if (this.view.problem !== null) this.patch({ problem: null });
  }

  /** Reads the providers and the selected provider's history, and follows a turn that is running. */
  async load(): Promise<void> {
    this.patch({ loading: true, loadError: null });
    try {
      const listed = await this.api.listProviders();
      // A project that never chose is shown the first provider that can run, so the chat is usable at once. The
      // choice is saved only when the user sends a message or picks a provider.
      this.unsaved = listed.selected === null ? (FIRST_CHOICE.find((id) => listed.providers.some((p) => p.id === id && p.installed)) ?? null) : null;
      const providers = this.shown(listed);
      this.patch({ providers });
      await this.loadHistory(providers.selected);
    } catch (error) {
      this.patch({ loadError: messageOf(error, "The chat could not be loaded.") });
    }
    this.patch({ loading: false });
  }

  /** The listing as the user sees it: the provider that is shown but not saved fills an empty choice. */
  private shown(listing: ProvidersListing): ProvidersListing {
    this.listingsShown += 1;
    if (listing.selected !== null) this.unsaved = null;
    return this.unsaved !== null && listing.selected === null ? { ...listing, selected: this.unsaved } : listing;
  }

  /** Saves the provider that was only shown as selected. */
  private async save(): Promise<void> {
    const provider = this.unsaved;
    if (provider === null) return;
    this.shown(await this.api.selectProvider(provider));
  }

  /** Replaces the visible conversation with the stored one of `provider`, and follows its running turn. */
  protected async loadHistory(provider: ProviderId | null): Promise<void> {
    this.stream?.abort();
    this.patch({ chat: INITIAL_CHAT_STATE });
    if (provider === null) return;
    const history = await this.api.chatHistory(provider);
    this.dispatch({ type: "history", turns: history.turns, undoableTurnId: history.undoableTurnId, undoProblem: history.undoProblem, runningTurnId: history.currentTurnId });
    if (history.running) void this.consume({ kind: "follow", after: 0 });
  }

  /** Makes `provider` the active one and shows its conversation. Not while a turn runs. */
  async selectProvider(provider: ProviderId): Promise<void> {
    if (this.view.chat.running) return;
    if (provider === this.provider && provider !== this.unsaved) return;
    try {
      this.unsaved = null;
      const providers = await this.api.selectProvider(provider);
      this.listingsShown += 1;
      this.patch({ providers, problem: null });
      await this.loadHistory(providers.selected);
    } catch (error) {
      this.patch({ problem: messageOf(error, "The provider could not be changed.") });
    }
  }

  /** Saves the model of a provider. Answers null, or the readable reason the server refused it. */
  async setModel(provider: ProviderId, model: string | null): Promise<string | null> {
    try {
      this.patch({ providers: this.shown(await this.api.setProviderModel(provider, model)) });
      return null;
    } catch (error) {
      return messageOf(error, "The model could not be saved.");
    }
  }

  /** Chooses account or API sign-in. Answers null, or the readable reason the server refused it. */
  async setAuthMode(provider: ProviderId, mode: AuthMode): Promise<string | null> {
    try {
      this.patch({ providers: this.shown(await this.api.setAuthMode(provider, mode)) });
      return null;
    } catch (error) {
      return messageOf(error, "The sign-in method could not be changed.");
    }
  }

  /** Stores a key, then reads the provider list again so the form shows set and its last four. Answers null, or a readable reason. */
  async saveKey(slot: string, key: string): Promise<string | null> {
    try {
      await this.api.saveCredential(slot, key);
    } catch (error) {
      return messageOf(error, "The key could not be saved.");
    }
    return this.refreshProviders();
  }

  async deleteKey(slot: string): Promise<string | null> {
    try {
      await this.api.deleteCredential(slot);
    } catch (error) {
      return messageOf(error, "The key could not be deleted.");
    }
    return this.refreshProviders();
  }

  /** The browser sign-in, when the server offers it. */
  get logins(): LoginApi | null {
    const api = this.api;
    if (api.startLogin === undefined || api.followLogin === undefined || api.sendLogin === undefined || api.cancelLogin === undefined) return null;
    return {
      startLogin: (provider, method) => api.startLogin!(provider, method),
      followLogin: (provider) => api.followLogin!(provider),
      sendLogin: (provider, input) => api.sendLogin!(provider, input),
      cancelLogin: (provider) => api.cancelLogin!(provider),
    };
  }

  readonly loginPollMs: number;

  /** After a sign-in from the browser ended: reads the providers again, so the login state shows. */
  onLoginEnded = (): void => {
    void this.refreshProviders();
  };

  private async refreshProviders(): Promise<string | null> {
    try {
      const before = this.listingsShown;
      const listed = await this.api.listProviders();
      // A newer answer arrived while this one was on its way, and it may hold a choice the user just made.
      if (this.listingsShown === before) this.patch({ providers: this.shown(listed) });
      return null;
    } catch (error) {
      return messageOf(error, "The key was saved, but the provider list could not be read again.");
    }
  }

  /** Trusts the project's CLI configuration the user was shown. Answers null, or the readable reason it was refused. */
  async trustProjectConfig(provider: ProviderId, fingerprint: string): Promise<string | null> {
    try {
      this.patch({ providers: this.shown(await this.api.trustProjectConfig(provider, fingerprint)) });
      return null;
    } catch (error) {
      return messageOf(error, "The project's CLI configuration could not be trusted.");
    }
  }

  /** Detects the provider CLIs again, for one that was installed after the page opened. */
  async recheck(): Promise<void> {
    this.patch({ checking: true });
    try {
      this.patch({ providers: this.shown(await this.api.recheckProviders()) });
    } catch (error) {
      this.patch({ problem: messageOf(error, "The providers could not be checked.") });
    }
    this.patch({ checking: false });
  }

  /** Forgets the conversation with the active provider. Not while a turn runs. */
  async newChat(): Promise<void> {
    const provider = this.provider;
    if (provider === null || this.view.chat.running) return;
    try {
      await this.api.resetChat(provider);
    } catch (error) {
      this.patch({ problem: messageOf(error, "A new chat could not be started.") });
      return;
    }
    this.dispatch({ type: "reset", message: NEW_CHAT_NOTE });
  }

  /** Undoes a turn. Files that changed after it open the choice (`undoChoice`) instead of being overwritten. */
  async undo(turnId: string, mode: UndoMode = "strict"): Promise<void> {
    let outcome;
    try {
      outcome = await this.api.undoTurn(turnId, mode);
    } catch (error) {
      if (mode === "strict" && error instanceof ApiError && error.code === "undo_conflict" && error.conflicts !== undefined) {
        this.patch({ undoChoice: { turnId, conflicts: error.conflicts } });
        return;
      }
      this.patch({ undoChoice: null, problem: messageOf(error, "The turn could not be undone.") });
      return;
    }
    const partial = outcome.skipped.length > 0;
    this.patch({ undoChoice: null, ...(partial ? {} : { undone: [...this.view.undone, turnId] }) });
    this.dispatch({ type: "note", level: partial ? "warning" : "info", message: describeUndo(outcome.files, outcome.skipped, mode) });
    await this.refreshUndoable();
  }

  cancelUndo(): void {
    this.patch({ undoChoice: null });
  }

  /** Writes Caztor's agent definition over the user's modified one, after the user confirmed. */
  async replaceDefinition(): Promise<void> {
    const provider = this.provider;
    if (provider === null) return;
    try {
      await this.api.replaceDefinition(provider);
      this.dispatch({ type: "note", level: "info", message: "The agent definition was replaced. The next message starts with it." });
    } catch (error) {
      this.patch({ problem: messageOf(error, "The agent definition could not be replaced.") });
    }
  }

  /** Sends a message to the selected provider. */
  async send(prompt: string): Promise<void> {
    const text = prompt.trim();
    const provider = this.provider;
    if (text === "" || this.view.chat.running) return;
    if (provider === null) return this.patch({ problem: "Choose a provider first." });
    const info = this.view.providers?.providers.find((candidate) => candidate.id === provider);
    if (info === undefined || !info.installed) return this.patch({ problem: info?.unavailableReason ?? `${provider} is not available.` });
    try {
      await this.save();
    } catch (error) {
      return this.patch({ problem: messageOf(error, "The provider could not be saved.") });
    }
    this.stopWanted = false;
    this.patch({ problem: null, drafts: { ...this.view.drafts, [provider]: "" } });
    this.dispatch({ type: "prompt_sent", prompt: text });
    await this.consume({ kind: "start", provider, prompt: text }, text);
  }

  /** Asks the server to stop the running turn; the stream then ends it as cancelled. */
  async stop(): Promise<void> {
    const running = this.view.chat.turns.findLast((turn) => turn.status === "running");
    if (running === undefined) return;
    if (running.turnId === null) {
      this.stopWanted = true;
      return;
    }
    await this.requestStop(running.turnId);
  }

  private async requestStop(turnId: string): Promise<void> {
    this.stopWanted = false;
    try {
      await this.api.stopTurn(turnId);
    } catch (error) {
      this.patch({ problem: messageOf(error, "The turn could not be stopped.") });
    }
  }

  private onEvent = (event: TurnEvent, seq: number | null): void => {
    this.dispatch(seq === null ? { type: "event", event } : { type: "event", event, seq });
    if (event.type === "turn_started" && this.stopWanted) void this.requestStop(event.turnId);
  };

  /** Reads one stream to its end, re-opening it after a drop, and then refreshes which turn can be undone. */
  private async consume(request: TurnStreamRequest, sentPrompt?: string): Promise<void> {
    this.stream?.abort();
    const stream = new AbortController();
    this.stream = stream;
    try {
      await this.api.streamTurn(request, this.onEvent, stream.signal);
      if (!stream.signal.aborted && this.view.chat.running) await this.resume(stream);
    } catch (error) {
      if (stream.signal.aborted) return;
      if (request.kind === "start" && error instanceof ApiError && error.status > 0) {
        this.dispatch({ type: "prompt_refused" });
        const provider = request.provider;
        this.patch({ problem: error.message, drafts: { ...this.view.drafts, [provider]: sentPrompt ?? "" } });
        return;
      }
      await this.resume(stream);
    }
    if (!stream.signal.aborted) {
      await this.refreshUndoable();
      await this.refreshProviders();
    }
  }

  /** Re-opens the stream of the running turn after the events already applied, until it ends or the attempts run out. */
  private async resume(stream: AbortController): Promise<void> {
    this.patch({ reconnecting: true });
    let pause = FIRST_RETRY_MS;
    for (let attempt = 0; attempt < MAX_RECONNECTS; attempt += 1) {
      await this.wait(pause);
      pause = Math.min(pause * 2, LONGEST_RETRY_MS);
      if (stream.signal.aborted) return;
      try {
        if (await this.neverStarted()) break;
        await this.api.streamTurn({ kind: "follow", after: this.view.chat.lastSeq }, this.onEvent, stream.signal, () => this.patch({ reconnecting: false }));
        if (!this.view.chat.running) return void this.patch({ reconnecting: false });
      } catch (error) {
        if (stream.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) break;
      }
    }
    this.patch({ reconnecting: false });
    this.dispatch({ type: "connection_lost", message: LOST_MESSAGE });
  }

  /** A turn the server never named may not have been accepted; the history tells whether anything is running. */
  private async neverStarted(): Promise<boolean> {
    const open = this.view.chat.turns.findLast((turn) => turn.status === "running");
    const provider = this.provider;
    if (open === undefined || open.turnId !== null || provider === null) return false;
    return !(await this.api.chatHistory(provider)).running;
  }

  /** Reads which turn can be undone now, without touching the visible conversation. */
  protected async refreshUndoable(): Promise<void> {
    const provider = this.provider;
    if (provider === null) return;
    try {
      const history = await this.api.chatHistory(provider);
      this.dispatch({ type: "undoable", turnId: history.undoableTurnId, problem: history.undoProblem });
    } catch {
      // The undo state is a convenience; the next history read corrects it.
    }
  }
}
