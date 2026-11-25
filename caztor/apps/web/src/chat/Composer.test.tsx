import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer.tsx";

function setup(props: Partial<Parameters<typeof Composer>[0]> = {}) {
  const onSend = vi.fn();
  const onStop = vi.fn();
  const onDraftChange = vi.fn();
  render(<Composer draft="" running={false} onDraftChange={onDraftChange} onSend={onSend} onStop={onStop} {...props} />);
  return { onSend, onStop, onDraftChange, box: screen.getByRole("textbox", { name: "Message to the assistant" }) };
}

describe("Composer", () => {
  it("sends with Enter and with the Send button, and Shift+Enter only adds a new line", async () => {
    const { onSend, box } = setup({ draft: "Fix the title" });
    await userEvent.type(box, "{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("Fix the title");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledTimes(2);
  });

  it("reports what is typed so the draft can be kept", async () => {
    const { onDraftChange, box } = setup();
    await userEvent.type(box, "ab");
    expect(onDraftChange).toHaveBeenLastCalledWith("b");
    expect(onDraftChange).toHaveBeenCalledTimes(2);
  });

  it("does not send an empty message", async () => {
    const { onSend, box } = setup({ draft: "   " });
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("while a turn runs: Send is disabled, Enter sends nothing, and Stop works", async () => {
    const { onSend, onStop, box } = setup({ draft: "next message", running: true });
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("offers no Stop button when nothing runs", () => {
    setup();
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });

  it("can be disabled with a reason that is shown and described", () => {
    const { box } = setup({ draft: "x", disabledReason: "codex is not installed." });
    expect(box).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByText("codex is not installed.")).toBeInTheDocument();
    expect(box).toHaveAccessibleDescription("codex is not installed.");
  });

  it("returns focus to the message box after Stop", async () => {
    const { box } = setup({ running: true });
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(box).toHaveFocus();
  });
});

describe("the slash command bar", () => {
  const commands = [
    { name: "new", hint: "Start a new chat" },
    { name: "model", hint: "Set the model", argument: "name" },
    { name: "login", hint: "How to sign in" },
  ];
  function bar(draft: string) {
    const onCommand = vi.fn();
    const onSend = vi.fn();
    const onDraftChange = vi.fn();
    const view = render(<Composer draft={draft} onDraftChange={onDraftChange} onSend={onSend} onStop={() => {}} running={false} commands={commands} onCommand={onCommand} />);
    return { onCommand, onSend, onDraftChange, view };
  }
  const box = () => screen.getByRole("textbox", { name: "Message to the assistant" });
  const options = () => screen.getAllByRole("option").map((option) => option.textContent);

  it("opens on a slash and lists every command with what it does", () => {
    bar("/");
    expect(options()).toEqual(["/newStart a new chat", "/modelnameSet the model", "/loginHow to sign in"]);
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("stays closed for an ordinary message or a slash later in the text", () => {
    bar("fix a/b");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("narrows as you type, and has no menu when nothing matches", () => {
    const { view } = bar("/lo");
    expect(options()).toEqual(["/loginHow to sign in"]);
    view.unmount();
    bar("/usr/share");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("runs the selected command on Enter, without sending a message", async () => {
    const { onCommand, onSend } = bar("/");
    box().focus();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(onCommand).toHaveBeenCalledWith("model", "");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("wraps with the arrows", async () => {
    const { onCommand } = bar("/");
    box().focus();
    await userEvent.keyboard("{ArrowUp}{Enter}");
    expect(onCommand).toHaveBeenCalledWith("login", "");
  });

  it("passes what follows the name as the argument", async () => {
    const { onCommand } = bar("/model opus 4");
    box().focus();
    await userEvent.keyboard("{Enter}");
    expect(onCommand).toHaveBeenCalledWith("model", "opus 4");
  });

  it("completes with Tab", async () => {
    const { onDraftChange, onCommand } = bar("/mo");
    box().focus();
    await userEvent.keyboard("{Tab}");
    expect(onDraftChange).toHaveBeenCalledWith("/model ");
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("closes with Escape, and Enter then sends the text as a message", async () => {
    const { onSend, onCommand } = bar("/new");
    box().focus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("/new");
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("sends text that names no command as a message", async () => {
    const { onSend, onCommand } = bar("/usr/share has the fonts");
    box().focus();
    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("/usr/share has the fonts");
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("runs a command on click", async () => {
    const { onCommand } = bar("/");
    await userEvent.click(screen.getAllByRole("option")[2]!);
    expect(onCommand).toHaveBeenCalledWith("login", "");
  });
});
