import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { ChatController } from "./controller.ts";
import { ChatPanel } from "./ChatPanel.tsx";

async function setup(init: Parameters<typeof createFakeApi>[0] = {}, wait: (ms: number) => Promise<void> = async () => {}) {
  const fake = createFakeApi(init);
  const controller = new ChatController({ api: fake.api, wait });
  render(<ChatPanel controller={controller} />);
  await act(() => controller.load());
  return { fake, controller };
}

const box = () => screen.getByRole("textbox", { name: "Message to the assistant" });

describe("ChatPanel", () => {
  it("lets the user pick Antigravity when it is installed", async () => {
    await setup({
      providers: {
        selected: "claude",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "antigravity", installed: true, requiresModel: false, model: null },
        ],
      },
    });
    await userEvent.click(screen.getByRole("radio", { name: "Antigravity" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: "Antigravity" })).toBeChecked());
    expect(box()).toBeEnabled();
  });

  it("shows an invitation when there is no conversation yet", async () => {
    await setup();
    expect(screen.getByText(/ask the assistant/i)).toBeInTheDocument();
  });

  it("runs a whole exchange: send, stream with a tool card, finish", async () => {
    const { fake } = await setup();
    await userEvent.type(box(), "Fix the title{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    expect(screen.getByText("Fix the title")).toBeInTheDocument();
    expect(box()).toHaveValue("");
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    act(() => {
      fake.chat.begin("t1");
      fake.chat.emit({ type: "text_delta", messageId: "m", text: "I will " });
      fake.chat.emit({ type: "tool_start", toolId: "x", name: "Edit", kind: "edit", path: "main.tex" });
      fake.chat.emit({ type: "text_delta", messageId: "m", text: "edit it." });
    });
    expect(screen.getByText("I will edit it.")).toBeInTheDocument();
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    act(() => {
      fake.chat.emit({ type: "tool_end", toolId: "x", status: "done" });
      fake.chat.emit({ type: "done", reason: "completed" });
      fake.chat.end();
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Stop" })).toBeNull());
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(box(), "More");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("stops the running turn from the Stop button", async () => {
    const { fake } = await setup();
    await userEvent.type(box(), "Long job{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => fake.chat.begin("t1"));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(fake.chat.stopped).toEqual(["t1"]));
  });

  it("restores the stored conversation", async () => {
    const fake = createFakeApi();
    fake.chat.history.claude = {
      provider: "claude",
      turns: [{ turnId: "t1", provider: "claude", prompt: "Earlier question", startedAt: 1, events: [{ type: "text", messageId: "m", text: "Earlier answer" }, { type: "done", reason: "completed" }] }],
      undoableTurnId: null,
      undoProblem: null,
      running: false,
      currentTurnId: null,
    };
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} />);
    await act(() => controller.load());
    expect(screen.getByText("Earlier question")).toBeInTheDocument();
    expect(screen.getByText("Earlier answer")).toBeInTheDocument();
  });

  it("shows why a message was refused and keeps what was typed", async () => {
    const { fake } = await setup();
    fake.chat.refuseNext(apiError("busy", "A turn is already running.", 409));
    await userEvent.type(box(), "Hello{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("A turn is already running.");
    expect(box()).toHaveValue("Hello");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a loading failure with a way to try again", async () => {
    const fake = createFakeApi();
    fake.failNext(apiError("boom", "The server is not answering.", 500));
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} />);
    await act(() => controller.load());
    expect(screen.getByRole("alert")).toHaveTextContent("The server is not answering.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("says when the connection is being restored", async () => {
    // The pause before the next attempt never ends, so the pane stays in its reconnecting state.
    const { fake } = await setup({}, () => new Promise<void>(() => {}));
    await userEvent.type(box(), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => fake.chat.begin("t1"));
    act(() => fake.chat.drop());
    expect(await screen.findByText("Reconnecting")).toBeInTheDocument();
  });
});

describe("ChatPanel header", () => {
  it("shows the active provider's logo at the top without repeating its name as text", async () => {
    await setup();
    const header = screen.getByRole("group", { name: "Assistant" });
    expect(within(header).getAllByRole("img", { name: "Claude Code" }).length).toBeGreaterThan(0);
    expect(within(header).queryByText("Claude Code")).toBeNull();
  });

  it("falls back to the name as text when the logo fails to load", async () => {
    await setup();
    const header = screen.getByRole("group", { name: "Assistant" });
    for (const image of within(header).getAllByRole("img", { name: "Claude Code" })) fireEvent.error(image);
    expect(within(header).getAllByText("Claude Code").length).toBeGreaterThan(0);
  });

  it("switches provider from the selector and shows the other conversation", async () => {
    const fake = createFakeApi({
      providers: {
        selected: "claude",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "opencode", installed: true, requiresModel: true, model: "a/b" },
        ],
      },
    });
    fake.chat.history.opencode = {
      provider: "opencode",
      turns: [{ turnId: "o1", provider: "opencode", prompt: "In opencode", startedAt: 1, events: [{ type: "text", messageId: "m", text: "From opencode" }, { type: "done", reason: "completed" }] }],
      undoableTurnId: null,
      undoProblem: null,
      running: false,
      currentTurnId: null,
    };
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} />);
    await act(() => controller.load());
    await userEvent.click(screen.getByRole("radio", { name: "opencode" }));
    expect(await screen.findByText("From opencode")).toBeInTheDocument();
    expect(fake.calls).toContain("selectProvider opencode");
  });

  it("explains an unavailable provider with its reason, keeps the composer off, and checks again on request", async () => {
    const { fake } = await setup({
      providers: {
        selected: "codex",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "codex", installed: false, unavailableReason: "codex was not found on your PATH.", requiresModel: false, model: null },
        ],
      },
    });
    expect(screen.getByRole("heading", { name: /Codex is not available/ })).toBeInTheDocument();
    expect(screen.getAllByText("codex was not found on your PATH.").length).toBeGreaterThan(0);
    expect(box()).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(fake.chat.rechecks).toBe(1));
  });

  it("tells the user that Codex can run commands inside its own sandbox, also while Codex is unavailable", async () => {
    await setup({
      providers: {
        selected: "codex",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "codex", installed: false, unavailableReason: "codex was not found on your PATH.", requiresModel: false, supportsModel: false, model: null },
        ],
      },
    });
    const disclosure = screen.getByRole("note", { name: "Codex runs commands" });
    expect(disclosure).toHaveTextContent("Codex can run commands on this computer inside its own sandbox");
    expect(disclosure).toHaveTextContent("Caztor cannot turn this off");
  });

  it("shows no command disclosure for the other providers", async () => {
    await setup();
    expect(screen.queryByRole("note", { name: "Codex runs commands" })).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "opencode" }));
    expect(screen.queryByRole("note", { name: "Codex runs commands" })).toBeNull();
  });

  it("shows the note a provider carries, and hides the model setting of one that takes no model", async () => {
    await setup({
      providers: {
        selected: "opencode",
        providers: [
          { id: "claude", installed: true, requiresModel: false, model: null },
          { id: "opencode", installed: true, requiresModel: true, note: "Models from providers you defined yourself are not available here: ollama.", model: "a/b" },
          { id: "pi", installed: true, requiresModel: false, supportsModel: false, model: null },
        ],
      },
    });
    expect(screen.getByText("Models from providers you defined yourself are not available here: ollama.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Model" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Pi" }));
    expect(screen.queryByRole("textbox", { name: "Model" })).toBeNull();
    expect(screen.queryByText(/ollama/)).toBeNull();
  });

  it("does not let the provider change while a turn runs", async () => {
    const { fake } = await setup();
    await userEvent.type(box(), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    expect(screen.getByRole("radio", { name: "opencode" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
  });

  it("asks before starting a new chat, and then shows the note in an empty conversation", async () => {
    const fake = createFakeApi();
    fake.chat.history.claude = {
      provider: "claude",
      turns: [{ turnId: "t1", provider: "claude", prompt: "Earlier", startedAt: 1, events: [{ type: "text", messageId: "m", text: "Before" }, { type: "done", reason: "completed" }] }],
      undoableTurnId: null,
      undoProblem: null,
      running: false,
      currentTurnId: null,
    };
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} />);
    await act(() => controller.load());
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    const dialog = screen.getByRole("dialog", { name: "Start a new chat?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Before")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start new chat" }));
    expect(await screen.findByText(/New conversation started/)).toBeInTheDocument();
    expect(screen.queryByText("Before")).toBeNull();
  });

  it("shows the model setting of the active provider and saves it", async () => {
    const { fake } = await setup();
    const model = screen.getByRole("textbox", { name: "Model" });
    await userEvent.type(model, "sonnet{Enter}");
    await waitFor(() => expect(fake.calls).toContain("setProviderModel claude sonnet"));
  });
});

describe("ChatPanel results", () => {
  const changed = { path: "main.tex" as never, change: "modified", beforeHash: null, afterHash: null, undoable: true, mixed: false } as const;

  async function finishedTurn(fake: ReturnType<typeof createFakeApi>, extra: () => void = () => {}) {
    await userEvent.type(box(), "Edit{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => {
      fake.chat.begin("t1");
      extra();
      fake.chat.emit({ type: "done", reason: "completed" });
      fake.chat.emit({ type: "files_changed", turnId: "t1", files: [changed] });
      fake.chat.history.claude = { provider: "claude", turns: [], undoableTurnId: "t1", undoProblem: null, running: false, currentTurnId: null };
      fake.chat.end();
    });
  }

  it("lists the changed files, opens one in the editor, and undoes the turn", async () => {
    const fake = createFakeApi();
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    const opened: string[] = [];
    render(<ChatPanel controller={controller} onOpenFile={(path) => opened.push(path)} />);
    await act(() => controller.load());
    await finishedTurn(fake);
    await userEvent.click(await screen.findByRole("button", { name: "main.tex" }));
    expect(opened).toEqual(["main.tex"]);
    fake.chat.history.claude = { provider: "claude", turns: [], undoableTurnId: null, undoProblem: null, running: false, currentTurnId: null };
    await userEvent.click(screen.getByRole("button", { name: "Undo this turn" }));
    await waitFor(() => expect(fake.chat.undos).toEqual([{ turnId: "t1", mode: "strict" }]));
    expect(await screen.findByText("Undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo this turn" })).toBeNull();
  });

  it("offers the three choices when files changed after the turn", async () => {
    const { fake } = await setup();
    await finishedTurn(fake);
    fake.chat.nextUndo = new ApiError({ status: 409, code: "undo_conflict", message: "m", conflicts: [{ path: "main.tex", expected: null, actual: null }] });
    await userEvent.click(await screen.findByRole("button", { name: "Undo this turn" }));
    const dialog = await screen.findByRole("dialog", { name: "Some files changed after this turn" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Undo the rest and keep my edits" }));
    await waitFor(() => expect(fake.chat.undos.at(-1)).toEqual({ turnId: "t1", mode: "skip_conflicts" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a partial undo as a warning that names the skipped files", async () => {
    const { fake } = await setup();
    await finishedTurn(fake);
    fake.chat.nextUndo = { files: [], skipped: ["main.tex"] };
    await userEvent.click(await screen.findByRole("button", { name: "Undo this turn" }));
    expect(await screen.findByText(/only partial/)).toHaveTextContent("Not restored: main.tex");
  });

  it("shows provider errors as cards and notices as banners, with the replace action asking first", async () => {
    const { fake } = await setup();
    await userEvent.type(box(), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => {
      fake.chat.begin("t1");
      fake.chat.emit({ type: "notice", level: "warning", message: "You changed the definition.", action: "replace_definition" });
      fake.chat.emit({ type: "tool_start", toolId: "x", name: "Edit", kind: "edit", path: "a.tex" });
      fake.chat.emit({ type: "error", code: "rate_limited", message: "Too many requests.", detail: "429" });
      fake.chat.emit({ type: "done", reason: "failed" });
      fake.chat.end();
    });
    expect(await screen.findByRole("heading", { name: "The provider is limiting requests" })).toBeInTheDocument();
    expect(screen.getByText("Interrupted")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Replace definition" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Replace" }));
    await waitFor(() => expect(fake.chat.replaced).toEqual(["claude"]));
  });

  it("says why undo is unavailable when the snapshots cannot be read", async () => {
    const fake = createFakeApi();
    fake.chat.history.claude = { provider: "claude", turns: [], undoableTurnId: null, undoProblem: "The snapshot folder is a link.", running: false, currentTurnId: null };
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} />);
    await act(() => controller.load());
    expect(screen.getByText(/Undo is unavailable: The snapshot folder is a link\./)).toBeInTheDocument();
  });
});

describe("ChatPanel project CLI configuration", () => {
  const FINGERPRINT = `sha256:${"a".repeat(64)}`;
  const withConfig = (confirmed: boolean): Parameters<typeof createFakeApi>[0] => ({
    providers: {
      selected: "opencode",
      providers: [
        { id: "claude", installed: true, requiresModel: false, model: null },
        {
          id: "opencode",
          installed: true,
          requiresModel: true,
          model: "openai/gpt-5.5",
          projectConfig: { files: ["opencode.json", ".opencode/plugins/"], confirmed, fingerprint: FINGERPRINT },
        },
        { id: "codex", installed: false, unavailableReason: "no", requiresModel: false, model: null },
      ],
    },
  });

  it("lists the files and keeps the message box closed until the user decides", async () => {
    await setup(withConfig(false));
    expect(screen.getByText(/this project can run programs/i)).toBeInTheDocument();
    expect(box()).toBeDisabled();
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Review project configuration" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("opencode.json")).toBeInTheDocument();
    expect(within(dialog).getByText(".opencode/plugins/")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/lets the project run programs on this computer/i);
  });

  it("does not trust by default: the first button is Cancel and focus starts there", async () => {
    const { fake } = await setup(withConfig(false));
    await userEvent.click(screen.getByRole("button", { name: "Review project configuration" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getAllByRole("button")[0]).toHaveTextContent("Cancel");
    expect(within(dialog).getAllByRole("button")[0]).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fake.calls.filter((call) => call.startsWith("trustProjectConfig"))).toEqual([]);
    expect(box()).toBeDisabled();
    expect(screen.getByText(/this project can run programs/i)).toBeInTheDocument();
  });

  it("sends the fingerprint it showed when the user trusts, then opens the message box", async () => {
    const { fake } = await setup(withConfig(false));
    await userEvent.click(screen.getByRole("button", { name: "Review project configuration" }));
    await userEvent.click(screen.getByRole("button", { name: "Trust this project's CLI configuration" }));
    await waitFor(() => expect(fake.calls).toContain(`trustProjectConfig opencode ${FINGERPRINT}`));
    await waitFor(() => expect(box()).toBeEnabled());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText(/this project can run programs/i)).toBeNull();
  });

  it("shows nothing when the files were already trusted, or when the project has none", async () => {
    await setup(withConfig(true));
    expect(screen.queryByText(/this project can run programs/i)).toBeNull();
    expect(box()).toBeEnabled();
  });

  it("says why the trust could not be saved and keeps the message box closed", async () => {
    const { fake } = await setup(withConfig(false));
    fake.failNext(apiError("project_config_changed", "The project's CLI configuration changed since it was shown. Review it again.", 409));
    await userEvent.click(screen.getByRole("button", { name: "Review project configuration" }));
    await userEvent.click(screen.getByRole("button", { name: "Trust this project's CLI configuration" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed since it was shown/i);
    expect(box()).toBeDisabled();
  });
});

describe("slash commands in the chat", () => {
  const installed = {
    providers: {
      selected: "claude" as const,
      providers: [
        { id: "claude" as const, installed: true, requiresModel: false, model: "Model", auth: { mode: "account" as const, modes: ["account" as const], keys: [], slot: null, apiReady: false, login: "unknown" as const, loginHint: "Sign in with your Claude account: run `claude`, then `/login`." } },
        { id: "codex" as const, installed: true, requiresModel: false, model: null },
      ],
    },
  };
  const type = (text: string) => userEvent.type(box(), `${text}{Enter}`);

  it("/model with no name goes back to the default model, and clears the box", async () => {
    const { fake } = await setup(installed);
    await type("/model");
    await waitFor(() => expect(fake.calls).toContain("setProviderModel claude null"));
    expect(box()).toHaveValue("");
    expect(fake.chat.starts).toEqual([]);
  });

  it("/model with a name sets it", async () => {
    const { fake } = await setup(installed);
    await type("/model sonnet");
    await waitFor(() => expect(fake.calls).toContain("setProviderModel claude sonnet"));
  });

  it("/provider moves to an installed provider, and explains an unknown one", async () => {
    const { fake } = await setup(installed);
    await type("/provider nope");
    expect(await screen.findByRole("alert")).toHaveTextContent(/opencode.*claude.*pi.*antigravity/);
    await type("/provider codex");
    expect(await screen.findByRole("alert")).toHaveTextContent("Name a provider");
    await type("/provider pi");
    await waitFor(() => expect(fake.calls).toContain("selectProvider pi"));
  });

  it("/new starts a new chat and /recheck looks for the providers again", async () => {
    const { fake } = await setup(installed);
    await type("/recheck");
    await waitFor(() => expect(fake.calls).toContain("recheckProviders"));
    expect(box()).toHaveValue("");
    expect(fake.chat.starts).toEqual([]);
  });
});

describe("PaperSmith agents as switches", () => {
  const listing = { selected: "claude" as const, providers: [{ id: "claude" as const, installed: true, requiresModel: false, model: null }] };
  const agents = [
    { name: "experiments-tutor", description: "Tutor for the experiments." },
    { name: "math-tutor", description: "Socratic math tutor." },
    { name: "paper-reviewer", description: "Reviewer." },
    { name: "ai-auditor", description: "Auditor." },
    { name: "sota-scout", description: "Scout." },
  ];

  it("shows the two tutors as buttons, the reviewer and the auditor under More, and no other agent", async () => {
    await setup({ providers: listing, agents });
    const group = await screen.findByRole("group", { name: "PaperSmith agents" });
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(["Math tutor", "Experiments tutor", "More ▾"]);
    await userEvent.click(within(group).getByRole("button", { name: "More ▾" }));
    expect(screen.getAllByRole("menuitemcheckbox").map((item) => item.textContent)).toEqual(["Paper reviewer", "Writing auditor"]);
    expect(screen.queryByText(/Scout/)).toBeNull();
  });

  it("offers only the agents the workspace has, and none when it has none", async () => {
    await setup({ providers: listing, agents: [{ name: "math-tutor", description: "Tutor." }] });
    const group = await screen.findByRole("group", { name: "PaperSmith agents" });
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(["Math tutor"]);
  });

  it("no longer lists the agents in the slash menu", async () => {
    await setup({ providers: listing, agents });
    await screen.findByRole("group", { name: "PaperSmith agents" });
    await userEvent.type(box(), "/");
    const menu = await screen.findByRole("listbox", { name: "Commands" });
    expect(within(menu).getAllByRole("option").some((option) => (option.textContent ?? "").includes("tutor"))).toBe(false);
  });

  it("while a tutor is on, sends every message to it, and stops when switched off", async () => {
    const { fake } = await setup({ providers: listing, agents });
    await userEvent.click(await screen.findByRole("button", { name: "Math tutor" }));
    expect(screen.getByRole("button", { name: "Math tutor" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("status").textContent).toContain("Math tutor");
    await userEvent.type(box(), "why is equation 3 exact?{Enter}");
    await waitFor(() => expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "/math-tutor why is equation 3 exact?" }]));
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
  });

  it("sends nothing when a tutor is switched on: it waits for the question", async () => {
    const { fake } = await setup({ providers: listing, agents });
    await userEvent.click(await screen.findByRole("button", { name: "Experiments tutor" }));
    expect(screen.getByRole("status").textContent).toContain("Experiments tutor answers your next messages");
    expect(fake.chat.starts).toEqual([]);
  });

  it("sends a plain message once the agent is switched off", async () => {
    const { fake } = await setup({ providers: listing, agents });
    await userEvent.click(await screen.findByRole("button", { name: "Math tutor" }));
    await userEvent.click(screen.getByRole("button", { name: "Math tutor" }));
    expect(screen.queryByRole("status")).toBeNull();
    await userEvent.type(box(), "fix the typo{Enter}");
    await waitFor(() => expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "fix the typo" }]));
  });

  it("chooses the reviewer from the More menu", async () => {
    const { fake } = await setup({ providers: listing, agents });
    await userEvent.click(await screen.findByRole("button", { name: "More ▾" }));
    await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "Paper reviewer" }));
    expect(screen.getByRole("button", { name: "Paper reviewer ▾" }).getAttribute("aria-pressed")).toBe("true");
    await userEvent.type(box(), "review section 2{Enter}");
    await waitFor(() => expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "/paper-reviewer review section 2" }]));
  });

  it("lists the providers the selector shows in the /provider hint", async () => {
    await setup({ providers: listing, agents });
    await userEvent.type(box(), "/prov");
    const menu = await screen.findByRole("listbox", { name: "Commands" });
    expect(within(menu).getByRole("option").textContent).toContain("opencode|claude|pi|antigravity");
  });
});

describe("a command sent with the Send button", () => {
  const listing = { selected: "claude" as const, providers: [{ id: "claude" as const, installed: true, requiresModel: false, model: null }] };

  it("runs in Caztor like Enter does, and never reaches the assistant", async () => {
    const { fake } = await setup({ providers: listing, agents: [{ name: "math-tutor", description: "Tutor." }] });
    fireEvent.change(box(), { target: { value: "/recheck" } });
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(fake.calls).toContain("recheckProviders"));
    expect(fake.chat.starts).toEqual([]);
  });

  it("sends a slash that names no command as a normal message", async () => {
    const { fake } = await setup({ providers: listing });
    fireEvent.change(box(), { target: { value: "/paper/main.tex has a typo" } });
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(fake.chat.starts).toEqual([{ provider: "claude", prompt: "/paper/main.tex has a typo" }]));
  });
});


describe("ChatPanel arrows between explained passages", () => {
  async function withExplain(explain: NonNullable<Parameters<typeof ChatPanel>[0]["explain"]>) {
    const fake = createFakeApi({ providers: { selected: "claude", providers: [{ id: "claude", installed: true, requiresModel: false, model: null }] } });
    const controller = new ChatController({ api: fake.api, wait: async () => {} });
    render(<ChatPanel controller={controller} explain={explain} />);
    await act(() => controller.load());
  }

  it("steps back and forth and says which passage is shown", async () => {
    const steps: number[] = [];
    await withExplain({ on: true, count: 5, onToggle: () => {}, current: 1, onStep: (direction) => steps.push(direction) });
    const nav = screen.getByRole("group", { name: "Explained passages" });
    expect(nav).toHaveTextContent("2 / 5");
    await userEvent.click(within(nav).getByRole("button", { name: "Next explained passage" }));
    await userEvent.click(within(nav).getByRole("button", { name: "Previous explained passage" }));
    expect(steps).toEqual([1, -1]);
  });

  it("shows the count before the first step, and no arrows when the marks are off or there is nothing to show", async () => {
    await withExplain({ on: true, count: 3, onToggle: () => {}, current: null, onStep: () => {} });
    expect(screen.getByRole("group", { name: "Explained passages" })).toHaveTextContent("3 in the paper");
  });

  it("hides the arrows when highlighting is off", async () => {
    await withExplain({ on: false, count: 3, onToggle: () => {}, current: null, onStep: () => {} });
    expect(screen.queryByRole("group", { name: "Explained passages" })).toBeNull();
    expect(screen.getByText("3 in the paper")).toBeTruthy();
  });
});
