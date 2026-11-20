import { useEffect, useState, useSyncExternalStore } from "react";
import { Dialog } from "../components/Dialog.tsx";
import { EmptyState } from "../components/EmptyState.tsx";
import { PROVIDER_ORDER } from "./providers.ts";
import { Composer, type SlashCommand } from "./Composer.tsx";
import { LoginHint } from "./LoginHint.tsx";
import type { ChatController } from "./controller.ts";
import { MessageList } from "./MessageList.tsx";
import { ProviderHeader } from "./ProviderHeader.tsx";
import { ANTIGRAVITY_ISOLATION_NOTICE, PI_ISOLATION_NOTICE } from "./providers.ts";
import "./NoticeBanner.css";
import { UndoConflictDialog } from "./UndoConflictDialog.tsx";
import { AgentBar } from "./AgentBar.tsx";
import { addressed, CHAT_AGENTS } from "./papersmith-agents.ts";
import { ProviderUnavailable } from "./ProviderUnavailable.tsx";
import "./ChatPanel.css";

interface ChatPanelProps {
  controller: ChatController;
  /** Opens a project file in the editor. */
  onOpenFile?: (path: string) => void;
  /** What `/compile` does. */
  onCompile?: () => void;
  /** The switch that marks, in the editor and the PDF, the passages the latest reply explains. */
  explain?: { on: boolean; count: number; onToggle: () => void };
}

/** The body of the chat pane: the conversation, what went wrong, and the message box. */
export function ChatPanel({ controller, onOpenFile, onCompile, explain }: ChatPanelProps) {
  const [loginNote, setLoginNote] = useState<string | null>(null);
  const [commandProblem, setCommandProblem] = useState<string | null>(null);
  const view = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const provider = view.providers?.selected ?? null;
  const info = view.providers?.providers.find((candidate) => candidate.id === provider);

  const [confirmingNewChat, setConfirmingNewChat] = useState(false);
  const [reviewingConfig, setReviewingConfig] = useState(false);
  const [trustProblem, setTrustProblem] = useState<string | null>(null);

  useEffect(() => () => controller.dispose(), [controller]);

  // The workspace's own agents (PaperSmith's) the chat offers as switches; while one is active, every message goes to it.
  // Asked once the providers are in, so a failing first load is the providers' own.
  const [agents, setAgents] = useState<Array<{ name: string; description: string }>>([]);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const loaded = !view.loading && view.loadError === null;
  useEffect(() => {
    if (!loaded) return;
    let live = true;
    void controller.agents().then((listed) => live && setAgents(listed));
    return () => {
      live = false;
    };
  }, [controller, loaded]);

  if (view.loadError !== null) {
    return (
      <div className="chat-panel chat-panel--centered">
        <div role="alert" className="chat-panel__failure">
          <p>{view.loadError}</p>
          <button type="button" className="button" onClick={() => void controller.load()}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  const config = info?.projectConfig;
  const needsTrust = config !== undefined && !config.confirmed;
  const disabledReason =
    provider === null
      ? "Choose a provider to start."
      : info === undefined || info.installed
        ? needsTrust
          ? "Review this project's CLI configuration before chatting."
          : null
        : (info.unavailableReason ?? `${provider} is not available.`);

  const commands: SlashCommand[] = [
    { name: "new", hint: "Start a new chat" },
    { name: "model", argument: "[name]", hint: "Set the model; with no name, the provider's default" },
    { name: "provider", argument: PROVIDER_ORDER.join("|"), hint: "Change the provider" },
    { name: "login", hint: "How to sign in to this provider" },
    { name: "recheck", hint: "Look for the installed providers again" },
    ...(onCompile === undefined ? [] : [{ name: "compile", hint: "Compile the project" }]),
    { name: "stop", hint: "Stop the running turn" },
  ];
  const chatAgents = CHAT_AGENTS.filter((offered) => agents.some((agent) => agent.name === offered.name));
  const active = chatAgents.some((agent) => agent.name === activeAgent) ? activeAgent : null;

  /** Runs a command typed in the message box, in Caztor; none reaches the assistant. */
  async function runCommand(name: string, argument: string): Promise<void> {
    if (provider !== null) controller.setDraft(provider, "");
    setCommandProblem(null);
    setLoginNote(null);
    if (name === "stop") {
      await controller.stop();
    } else if (view.chat.running) {
      setCommandProblem("Stop the running turn first.");
    } else if (name === "new") {
      setConfirmingNewChat(true);
    } else if (name === "recheck") {
      await controller.recheck();
    } else if (name === "compile") {
      onCompile?.();
    } else if (name === "login") {
      setLoginNote(
        info?.auth === undefined
          ? "This provider has no sign-in step."
          : info.auth.mode === "api"
            ? "This provider is using an API key. Add or change it under Sign-in."
            : info.auth.loginHint,
      );
    } else if (name === "provider") {
      const wanted = PROVIDER_ORDER.find((id) => id === argument);
      if (wanted === undefined) setCommandProblem(`Name a provider: ${PROVIDER_ORDER.join(", ")}.`);
      else await controller.selectProvider(wanted);
    } else if (name === "model" && provider !== null) {
      setCommandProblem(await controller.setModel(provider, argument === "" ? null : argument));
    }
  }

  async function trust(): Promise<void> {
    if (provider === null || config === undefined) return;
    const problem = await controller.trustProjectConfig(provider, config.fingerprint);
    setTrustProblem(problem);
    if (problem === null) setReviewingConfig(false);
  }

  return (
    <div className="chat-panel">
      {view.providers === null ? null : (
        <ProviderHeader
          listing={view.providers}
          running={view.chat.running}
          onSelect={(next) => void controller.selectProvider(next)}
          onModel={(next, model) => controller.setModel(next, model)}
          onAuthMode={(next, mode) => controller.setAuthMode(next, mode)}
          onSaveKey={(slot, key) => controller.saveKey(slot, key)}
          onDeleteKey={(slot) => controller.deleteKey(slot)}
          onNewChat={() => setConfirmingNewChat(true)}
          login={controller.logins === null ? undefined : { api: controller.logins, pollMs: controller.loginPollMs, onEnded: controller.onLoginEnded }}
        />
      )}
      {provider === "antigravity" ? (
        <p role="note" aria-label="Antigravity isolation" className="notice notice--warning chat-panel__isolation">
          {ANTIGRAVITY_ISOLATION_NOTICE}
        </p>
      ) : null}
      {provider === "pi" ? (
        <p role="note" aria-label="Pi isolation" className="notice notice--warning chat-panel__isolation">
          {PI_ISOLATION_NOTICE}
        </p>
      ) : null}
      {provider !== null && info !== undefined && !info.installed ? (
        <ProviderUnavailable provider={provider} reason={info.unavailableReason ?? `${provider} is not installed.`} checking={view.checking} onRecheck={() => void controller.recheck()} />
      ) : null}
      {needsTrust && info?.installed ? (
        <div className="chat-panel__trust">
          <p>This project can run programs when the assistant starts, through its own CLI configuration.</p>
          <button type="button" className="button" onClick={() => { setTrustProblem(null); setReviewingConfig(true); }}>
            Review project configuration
          </button>
        </div>
      ) : null}
      {trustProblem === null || reviewingConfig ? null : (
        <p role="alert" className="chat-panel__problem">
          {trustProblem}
        </p>
      )}
      {view.chat.timeline.length === 0 && !view.loading ? (
        <div className="chat-panel__empty">
          <EmptyState title="Ask the assistant">Describe a change to your document. The assistant edits your files directly, and you can undo each turn.</EmptyState>
        </div>
      ) : (
        <MessageList
          timeline={view.chat.timeline}
          busy={view.chat.running}
          undoableTurnId={view.chat.undoableTurnId}
          undone={view.undone}
          onUndo={(turnId) => void controller.undo(turnId)}
          {...(onOpenFile === undefined ? {} : { onOpenFile })}
          onReplaceDefinition={() => void controller.replaceDefinition()}
          {...(info?.auth === undefined ? {} : { signIn: { mode: info.auth.mode, loginHint: info.auth.loginHint } })}
        />
      )}
      {view.chat.undoProblem === null ? null : <p className="chat-panel__status chat-panel__status--plain">Undo is unavailable: {view.chat.undoProblem}</p>}
      {view.reconnecting ? (
        <p className="chat-panel__status" role="status">
          Reconnecting
        </p>
      ) : null}
      {loginNote === null ? null : (
        <div role="status" className="chat-panel__status chat-panel__status--plain">
          <LoginHint hint={loginNote} />
        </div>
      )}
      {commandProblem === null ? null : (
        <p role="alert" className="chat-panel__problem">
          {commandProblem}
        </p>
      )}
      {view.problem === null ? null : (
        <div role="alert" className="chat-panel__problem">
          <span>{view.problem}</span>
          <button type="button" className="button chat-panel__dismiss" onClick={() => controller.clearProblem()}>
            Dismiss
          </button>
        </div>
      )}
      {explain === undefined ? null : (
        <div className="chat-panel__explain">
          <button type="button" className="chat-panel__explain-toggle" aria-pressed={explain.on} onClick={explain.onToggle} title="Mark in soft yellow, in the editor and the PDF, the passages the last reply quotes">
            <span className="chat-panel__explain-swatch" aria-hidden="true" />
            Highlight explained passages
          </button>
          <span className="chat-panel__explain-count">{explain.count === 0 ? "none in the last reply" : `${explain.count} in the last reply`}</span>
        </div>
      )}
      <AgentBar
        agents={chatAgents}
        active={active}
        onChange={setActiveAgent}
      />
      <Composer
        draft={provider === null ? "" : (view.drafts[provider] ?? "")}
        onDraftChange={(text) => provider !== null && controller.setDraft(provider, text)}
        onSend={(text) => void controller.send(active === null ? text : addressed(active, text))}
        onStop={() => void controller.stop()}
        running={view.chat.running}
        disabledReason={disabledReason}
        commands={commands}
        onCommand={(name, argument) => void runCommand(name, argument)}
      />
      {view.undoChoice === null ? null : (
        <UndoConflictDialog
          conflicts={view.undoChoice.conflicts}
          onCancel={() => controller.cancelUndo()}
          onKeepMine={() => void controller.undo(view.undoChoice!.turnId, "skip_conflicts")}
          onOverwrite={() => void controller.undo(view.undoChoice!.turnId, "force")}
        />
      )}
      {reviewingConfig && config !== undefined ? (
        <Dialog
          title="Trust this project's CLI configuration?"
          onDismiss={() => setReviewingConfig(false)}
          actions={
            <>
              <button type="button" className="button" onClick={() => setReviewingConfig(false)}>
                Cancel
              </button>
              <button type="button" className="button button--danger" onClick={() => void trust()}>
                Trust this project's CLI configuration
              </button>
            </>
          }
        >
          <p>These files in the project are read by the assistant's command-line program:</p>
          <ul className="chat-panel__config-files">
            {config.files.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
          <p>Trusting them lets the project run programs on this computer, as you, whenever you chat. Trust them only if you wrote them or know where they came from.</p>
          <p>The choice is remembered for this project until one of these files changes.</p>
          {trustProblem === null ? null : <p role="alert">{trustProblem}</p>}
        </Dialog>
      ) : null}
      {confirmingNewChat ? (
        <Dialog
          title="Start a new chat?"
          onDismiss={() => setConfirmingNewChat(false)}
          actions={
            <>
              <button type="button" className="button" onClick={() => setConfirmingNewChat(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="button button--primary"
                onClick={() => {
                  setConfirmingNewChat(false);
                  void controller.newChat();
                }}
              >
                Start new chat
              </button>
            </>
          }
        >
          <p>The assistant will not remember this conversation, and it leaves this list. Your files and the undo history are not touched.</p>
        </Dialog>
      ) : null}
    </div>
  );
}
