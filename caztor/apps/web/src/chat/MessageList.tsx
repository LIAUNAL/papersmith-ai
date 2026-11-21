import { useLayoutEffect, useRef } from "react";
import type { ChatItem, ChatTurn, TimelineEntry } from "@caztor/core";
import { ErrorCard, type SignInContext } from "./ErrorCard.tsx";
import { Markdown } from "./Markdown.tsx";
import { NoticeBanner } from "./NoticeBanner.tsx";
import { TurnSummary } from "./TurnSummary.tsx";
import { ToolActivityCard } from "./ToolActivityCard.tsx";
import { splitTutorAnswer, streamingTutorAnswer, TutorReply } from "./TutorReply.tsx";
import { splitAddressed } from "./papersmith-agents.ts";
import "./MessageList.css";
import { TURN_ISOLATION_NOTICE_STARTS } from "./providers.ts";

/** How close to the end the reader must be for new output to keep the view at the end. */
const STICK_DISTANCE_PX = 48;

interface MessageListProps {
  timeline: TimelineEntry[];
  /** A turn is streaming: screen readers hear the finished reply instead of every fragment. */
  busy?: boolean;
  /** The turn the undo action applies to. */
  undoableTurnId?: string | null;
  /** Turns whose undo restored everything. */
  undone?: readonly string[];
  onUndo?: (turnId: string) => void;
  onOpenFile?: (path: string) => void;
  onReplaceDefinition?: () => void;
  /** How the active provider signs in, so an authentication failure names the right fix. */
  signIn?: SignInContext;
}

/** One item of a reply. */
/** An assistant's text; a PaperSmith tutor's JSON answer inside it is shown as readable sections. */
function AssistantText({ text, running }: { text: string; running: boolean }) {
  const tutor = splitTutorAnswer(text);
  // While a tutor's JSON answer is arriving, its reply reads as text and the rest waits for the closed block.
  const arriving = tutor === null && running ? streamingTutorAnswer(text) : null;
  if (arriving !== null) {
    return (
      <>
        {arriving.before === "" ? null : <Markdown text={arriving.before} />}
        {arriving.reply === null || arriving.reply === "" ? null : <Markdown text={arriving.reply} />}
        <p className="tutor-reply__writing" role="status">
          Writing the answer…
        </p>
      </>
    );
  }
  if (tutor === null) return <Markdown text={text} />;
  return (
    <>
      {tutor.before === "" ? null : <Markdown text={tutor.before} />}
      <TutorReply answer={tutor.answer} raw={tutor.raw} />
      {tutor.after === "" ? null : <Markdown text={tutor.after} />}
    </>
  );
}

type ToolItem = Extract<ChatItem, { kind: "tool" }>;

/** Consecutive tool steps become one entry, so the conversation reads as text with the steps folded between. */
function groupSteps(items: readonly ChatItem[]): Array<Exclude<ChatItem, ToolItem> | { kind: "steps"; tools: ToolItem[] }> {
  const out: Array<Exclude<ChatItem, ToolItem> | { kind: "steps"; tools: ToolItem[] }> = [];
  for (const item of items) {
    const last = out.at(-1);
    if (item.kind !== "tool") out.push(item);
    else if (last?.kind === "steps") last.tools.push(item);
    else out.push({ kind: "steps", tools: [item] });
  }
  return out;
}

/** One line for a run of steps: how many, of which tools, the one running now; opened when a step failed. */
function ToolGroup({ tools }: { tools: ToolItem[] }) {
  const counts = new Map<string, number>();
  for (const tool of tools) counts.set(tool.name, (counts.get(tool.name) ?? 0) + 1);
  const failed = tools.filter((tool) => tool.status === "failed").length;
  const running = tools.find((tool) => tool.status === "running");
  const steps = tools.length === 1 ? "1 step" : `${tools.length} steps`;
  const summary = running
    ? `${steps}, working: ${running.name}${running.path === undefined ? "" : ` ${running.path}`}`
    : `${steps}: ${[...counts].map(([name, count]) => `${name} ${count}`).join(", ")}${failed > 0 ? ` (${failed} failed)` : ""}`;
  return (
    <details className="tool-group" open={failed > 0}>
      <summary>{summary}</summary>
      {tools.map((tool) => (
        <ToolActivityCard key={`tool-${tool.toolId}`} tool={tool} />
      ))}
    </details>
  );
}

function ReplyItem({ item, onReplaceDefinition, signIn, running }: { item: ChatItem; onReplaceDefinition: (() => void) | undefined; signIn: SignInContext | undefined; running: boolean }) {
  switch (item.kind) {
    case "text":
      return (
        <div className="message message--assistant">
          <AssistantText text={item.text} running={running} />
        </div>
      );
    case "tool":
      return <ToolActivityCard tool={item} />;
    case "notice":
      if (TURN_ISOLATION_NOTICE_STARTS.some((start) => item.message.startsWith(start))) return null;
      return <NoticeBanner level={item.level} message={item.message} {...(item.action === undefined ? {} : { action: item.action })} {...(onReplaceDefinition === undefined ? {} : { onReplace: onReplaceDefinition })} />;
    case "error":
      return <ErrorCard code={item.code} message={item.message} {...(item.detail === undefined ? {} : { detail: item.detail })} {...(signIn === undefined ? {} : { signIn })} />;
  }
}

interface TurnProps {
  onUndo: ((turnId: string) => void) | undefined;
  onOpenFile: ((path: string) => void) | undefined;
  onReplaceDefinition: (() => void) | undefined;
  signIn: SignInContext | undefined;
  turn: ChatTurn;
  canUndo: boolean;
  undone: boolean;
}

/** What the user sent; a message to a PaperSmith agent names that agent instead of showing its command. */
function UserMessage({ prompt }: { prompt: string }) {
  const { agent, text } = splitAddressed(prompt);
  return (
    <div className="message message--user">
      {agent === null ? null : <span className="message__agent">{agent.label}</span>}
      {agent === null ? prompt : text === "" ? <em>Begin</em> : text}
    </div>
  );
}

function Turn({ turn, canUndo, undone, onUndo, onOpenFile, onReplaceDefinition, signIn }: TurnProps) {
  const waiting = turn.status === "running" && turn.items.length === 0;
  return (
    <section className="turn">
      {turn.prompt === null ? null : <UserMessage prompt={turn.prompt} />}
      {groupSteps(turn.items).map((entry, index) =>
        entry.kind === "steps" ? (
          <ToolGroup key={`steps-${entry.tools[0]!.toolId}`} tools={entry.tools} />
        ) : (
          <ReplyItem key={entry.kind === "text" ? `text-${entry.id}` : `${entry.kind}-${index}`} item={entry} onReplaceDefinition={onReplaceDefinition} signIn={signIn} running={turn.status === "running"} />
        ),
      )}
      {turn.status === "cancelled" ? <p className="turn__note">Stopped</p> : null}
      <TurnSummary turn={turn} canUndo={canUndo} undone={undone} onUndo={() => turn.turnId !== null && onUndo?.(turn.turnId)} onOpenFile={(path) => onOpenFile?.(path)} />
      {waiting ? (
        <p className="turn__working" role="status">
          Working
        </p>
      ) : null}
    </section>
  );
}

/** The conversation as a log region. It follows new output while the reader is at the end and leaves them alone otherwise. */
export function MessageList({ timeline, busy = false, undoableTurnId = null, undone = [], onUndo, onOpenFile, onReplaceDefinition, signIn }: MessageListProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (element !== null && following.current) element.scrollTop = element.scrollHeight;
  });

  return (
    <div
      ref={scroller}
      className="message-list"
      role="log"
      aria-label="Conversation"
      aria-live="polite"
      aria-relevant="additions"
      aria-busy={busy}
      tabIndex={0}
      onScroll={(event) => {
        const element = event.currentTarget;
        following.current = element.scrollHeight - element.scrollTop - element.clientHeight <= STICK_DISTANCE_PX;
      }}
    >
      {timeline.map((entry) =>
        entry.kind === "turn" ? (
          <Turn
            key={entry.turn.key}
            turn={entry.turn}
            canUndo={entry.turn.turnId !== null && entry.turn.turnId === undoableTurnId}
            undone={entry.turn.turnId !== null && undone.includes(entry.turn.turnId)}
            onUndo={onUndo}
            onOpenFile={onOpenFile}
            onReplaceDefinition={onReplaceDefinition}
            signIn={signIn}
          />
        ) : (
          <NoticeBanner key={entry.key} level={entry.level} message={entry.message} />
        ),
      )}
    </div>
  );
}
