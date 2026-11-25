import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Icon } from "../components/Icon.tsx";
import "./Composer.css";

interface ComposerProps {
  draft: string;
  onDraftChange: (text: string) => void;
  onSend: (text: string) => void;
  onStop: () => void;
  /** A turn is running: Send is off and Stop is offered. */
  running: boolean;
  /** Why messages cannot be sent at all (no provider, provider missing); shown under the box. */
  disabledReason?: string | null;
  /** What typing a slash offers. They run in Caztor: a turn turns the CLI's own slash commands off. */
  commands?: readonly SlashCommand[];
  onCommand?: (name: string, argument: string) => void;
}

export interface SlashCommand {
  name: string;
  hint: string;
  /** What the command takes after its name. */
  argument?: string;
}

const MAX_ROWS = 8;

/** The message box: Enter sends, Shift+Enter makes a new line, and while a turn runs Stop takes the lead. */
export function Composer({ draft, onDraftChange, onSend, onStop, running, disabledReason = null, commands = [], onCommand }: ComposerProps) {
  const reasonId = useId();
  const menuId = useId();
  const box = useRef<HTMLTextAreaElement>(null);
  const blocked = disabledReason !== null;
  const canSend = !running && !blocked && draft.trim() !== "";

  // A first word that names no command is an ordinary message, such as a path.
  const typed = /^\/(\S*)(?: ([^\n]*))?$/.exec(draft);
  const word = typed?.[1] ?? "";
  const hasArgument = typed?.[2] !== undefined;
  const matches = typed === null ? [] : commands.filter((command) => (hasArgument ? command.name === word : command.name.startsWith(word)));
  const [dismissed, setDismissed] = useState(false);
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    setSelected(0);
    if (typed === null) setDismissed(false);
  }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps
  const menuOpen = matches.length > 0 && !dismissed && !blocked;
  const current = matches[Math.min(selected, matches.length - 1)];

  function runCommand(name: string): void {
    onCommand?.(name, typed?.[2]?.trim() ?? "");
    box.current?.focus();
  }

  function onMenuKey(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const step = event.key === "ArrowDown" ? 1 : -1;
      setSelected((selected + step + matches.length) % matches.length);
    } else if (event.key === "Escape") {
      setDismissed(true);
    } else if (event.key === "Tab" && current !== undefined) {
      onDraftChange(`/${current.name} `);
    } else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && current !== undefined) {
      runCommand(current.name);
    } else {
      return false;
    }
    event.preventDefault();
    return true;
  }

  /**
   * Sends the text, unless it names a command exactly: then the command runs, whether Enter or Send asked. Escape
   * closes the menu and keeps the text a message, as before.
   */
  function submit(): void {
    if (typed !== null && !blocked && !dismissed && commands.some((command) => command.name === word)) runCommand(word);
    else if (canSend) onSend(draft);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (menuOpen && onMenuKey(event)) return;
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  }

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {menuOpen ? (
        <ul id={menuId} role="listbox" aria-label="Commands" className="composer__commands">
          {matches.map((command) => (
            <li
              key={command.name}
              role="option"
              aria-selected={command === current}
              className="composer__command"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => runCommand(command.name)}
            >
              <span className="composer__command-name">/{command.name}</span>
              {command.argument === undefined ? null : <span className="composer__command-argument">{command.argument}</span>}
              <span className="composer__command-hint">{command.hint}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <textarea
        ref={box}
        className="composer__box"
        aria-label="Message to the assistant"
        aria-describedby={blocked ? reasonId : undefined}
        aria-controls={menuOpen ? menuId : undefined}
        placeholder="Ask for a change to your document"
        rows={Math.min(MAX_ROWS, Math.max(2, draft.split("\n").length))}
        value={draft}
        disabled={blocked}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      {blocked ? (
        <p id={reasonId} className="composer__reason">
          {disabledReason}
        </p>
      ) : null}
      <div className="composer__actions">
        <span className="composer__hint">Enter to send, Shift+Enter for a new line</span>
        {running ? (
          <button
            type="button"
            className="button button--danger composer__button"
            onClick={() => {
              onStop();
              box.current?.focus();
            }}
          >
            <Icon name="stop" />
            Stop
          </button>
        ) : null}
        <button type="submit" className="button button--primary composer__button" disabled={!canSend}>
          <Icon name="send" />
          Send
        </button>
      </div>
    </form>
  );
}
