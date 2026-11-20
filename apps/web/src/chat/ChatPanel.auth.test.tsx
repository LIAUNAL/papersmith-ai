import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ProviderAuth, ProviderId, ProviderInfo } from "../api/types.ts";
import { apiError, createFakeApi } from "../testing/fake-api.ts";
import { ChatPanel } from "./ChatPanel.tsx";
import { ChatController } from "./controller.ts";

const HINTS: Record<string, string> = {
  antigravity: "Sign in with Antigravity: run `agy` and follow the sign-in prompts.",
  claude: "Sign in with your Claude account: run `claude`, then `/login`.",
  opencode: "Sign in with opencode: run `opencode providers login`.",
  codex: "Sign in with Codex: run `codex login`.",
  pi: "Sign in with Pi: run `pi`, then `/login`.",
};
const KEY = "sk-abcdef1234567890";

function auth(id: ProviderId, patch: Partial<ProviderAuth> = {}): ProviderAuth {
  return { mode: "account", modes: ["account", "api"], keys: [{ slot: id, set: false }], slot: id, apiReady: false, login: "unknown", loginHint: HINTS[id]!, ...patch };
}
const provider = (id: ProviderId, patch: Partial<ProviderAuth> = {}, extra: Partial<ProviderInfo> = {}): ProviderInfo => ({
  id,
  installed: true,
  requiresModel: id === "opencode",
  model: id === "opencode" ? "openai/gpt-5.5" : null,
  auth: auth(id, id === "opencode" ? { slot: "opencode:openai", keys: [{ slot: "opencode:openai", set: false }], ...patch } : patch),
  ...extra,
});

async function setup(providers: ProviderInfo[], selected: ProviderId = providers[0]!.id) {
  const fake = createFakeApi({ providers: { selected, providers } });
  const controller = new ChatController({ api: fake.api, wait: async () => {} });
  render(<ChatPanel controller={controller} />);
  await act(() => controller.load());
  return { fake, controller };
}
const signIn = () => screen.getByRole("group", { name: "Sign-in method" });
const radio = (name: string) => within(signIn()).getByRole("radio", { name });

describe("the sign-in mode toggle", () => {
  it("shows account as active and marks API key as not configured when no key is stored", async () => {
    await setup([provider("claude")]);
    expect(radio("Account")).toBeChecked();
    expect(radio("API key")).not.toBeChecked();
    expect(within(signIn()).getByText("Not configured")).toBeInTheDocument();
  });

  it("prompts for a key, and changes nothing on the server, when the user selects API key without one", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.click(radio("API key"));
    expect(screen.getByLabelText("API key", { selector: "input" })).toBeInTheDocument();
    expect(screen.getByText(/add an api key/i)).toBeInTheDocument();
    expect(fake.calls.some((call) => call.startsWith("setAuthMode"))).toBe(false);
    expect(radio("Account")).toBeChecked();
  });

  it("switches to API mode when a key is stored, and back to account", async () => {
    const { fake } = await setup([provider("claude", { apiReady: true, keys: [{ slot: "claude", set: true, last4: "1234" }] })]);
    await userEvent.click(radio("API key"));
    await waitFor(() => expect(radio("API key")).toBeChecked());
    expect(fake.calls).toContain("setAuthMode claude api");
    expect(within(signIn()).queryByText("Not configured")).toBeNull();
    await userEvent.click(radio("Account"));
    await waitFor(() => expect(radio("Account")).toBeChecked());
    expect(fake.calls).toContain("setAuthMode claude account");
  });

  it("shows the server's reason and stays on account when the switch is refused", async () => {
    const { fake } = await setup([provider("claude", { apiReady: true, keys: [{ slot: "claude", set: true, last4: "1234" }] })]);
    fake.failNext(apiError("api_key_missing", "No API key is stored for claude. Add one first, then switch.", 409));
    await userEvent.click(radio("API key"));
    expect(await screen.findByRole("alert")).toHaveTextContent("No API key is stored for claude. Add one first, then switch.");
    expect(radio("Account")).toBeChecked();
  });

  it("offers only account mode for a provider that has no API mode", async () => {
    await setup([provider("claude", { modes: ["account"] })]);
    expect(within(signIn()).getAllByRole("radio")).toHaveLength(1);
    expect(radio("Account")).toBeChecked();
    expect(within(signIn()).queryByRole("radio", { name: "API key" })).toBeNull();
    expect(screen.queryByLabelText("API key", { selector: "input" })).toBeNull();
  });

  it("is disabled while a turn runs", async () => {
    const { fake } = await setup([provider("claude", { apiReady: true, keys: [{ slot: "claude", set: true, last4: "1234" }] })]);
    await userEvent.type(screen.getByRole("textbox", { name: "Message to the assistant" }), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    expect(radio("API key")).toBeDisabled();
    expect(radio("Account")).toBeDisabled();
  });
});

describe("the masked key form", () => {
  const withKey = () => provider("claude", { apiReady: true, mode: "api", keys: [{ slot: "claude", set: true, last4: "1234" }] });

  it("shows that a key is set and its last four characters, with an empty masked field", async () => {
    await setup([withKey()]);
    const field = screen.getByLabelText("API key", { selector: "input" });
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveValue("");
    expect(screen.getByText(/key set/i)).toHaveTextContent("1234");
  });

  it("shows that no key is set when there is none", async () => {
    await setup([provider("claude")]);
    await userEvent.click(radio("API key"));
    expect(screen.getByText(/no key set/i)).toBeInTheDocument();
  });

  it("saves the key, empties the field, and then shows set with the last four", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.click(radio("API key"));
    const field = screen.getByLabelText("API key", { selector: "input" });
    await userEvent.type(field, KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save key" }));
    await waitFor(() => expect(screen.getByText(/key set/i)).toHaveTextContent("7890"));
    expect(fake.chat.savedKeys).toEqual([{ slot: "claude", key: KEY }]);
    expect(screen.getByLabelText("API key", { selector: "input" })).toHaveValue("");
    expect(document.body.textContent).not.toContain(KEY);
    expect(fake.calls.join("\n")).not.toContain(KEY);
  });

  it("empties the field and shows a message without the key when the save fails", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.click(radio("API key"));
    fake.failNext(apiError("credential_store_unusable", `The key file rejected ${KEY} and cannot be used.`, 409));
    await userEvent.type(screen.getByLabelText("API key", { selector: "input" }), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save key" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("cannot be used");
    expect(document.body.textContent).not.toContain(KEY);
    expect(screen.getByLabelText("API key", { selector: "input" })).toHaveValue("");
    expect(screen.getByText(/no key set/i)).toBeInTheDocument();
  });

  it("does not submit an empty field", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.click(radio("API key"));
    expect(screen.getByRole("button", { name: "Save key" })).toBeDisabled();
    expect(fake.chat.savedKeys).toEqual([]);
  });

  it("replaces a key that is set, and deletes it", async () => {
    const { fake } = await setup([withKey()]);
    await userEvent.type(screen.getByLabelText("API key", { selector: "input" }), "sk-new-key-0000zzzz");
    await userEvent.click(screen.getByRole("button", { name: "Replace key" }));
    await waitFor(() => expect(screen.getByText(/key set/i)).toHaveTextContent("zzzz"));
    await userEvent.click(screen.getByRole("button", { name: "Delete key" }));
    await waitFor(() => expect(screen.getByText(/no key set/i)).toBeInTheDocument());
    expect(fake.calls).toContain("deleteCredential claude");
    expect(screen.queryByRole("button", { name: "Delete key" })).toBeNull();
  });

  it("asks for a provider/model name instead of showing a field when opencode has no usable vendor", async () => {
    await setup([provider("opencode", { slot: null, slotProblem: "Choose an opencode model written as provider/model, so Caztor knows which key to use.", keys: [] }, { model: null })]);
    await userEvent.click(radio("API key"));
    expect(screen.getByText(/provider\/model, so Caztor knows which key/)).toBeInTheDocument();
    expect(screen.queryByLabelText("API key", { selector: "input" })).toBeNull();
  });

  it("names the vendor whose key an opencode model uses", async () => {
    const { fake } = await setup([provider("opencode")]);
    await userEvent.click(radio("API key"));
    expect(screen.getByText(/key for openai/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("API key", { selector: "input" }), KEY);
    await userEvent.click(screen.getByRole("button", { name: "Save key" }));
    await waitFor(() => expect(fake.chat.savedKeys).toEqual([{ slot: "opencode:openai", key: KEY }]));
  });

  it("shows why the store cannot be used and turns the field off", async () => {
    await setup([provider("claude", { keys: [], storeProblem: "The Caztor key file can be reached by other users. Run chmod 600 on it." })]);
    await userEvent.click(radio("API key"));
    expect(screen.getByRole("alert")).toHaveTextContent("chmod 600");
    expect(screen.getByLabelText("API key", { selector: "input" })).toBeDisabled();
  });
});

describe("login hints", () => {
  it.each([
    ["claude", ["claude", "/login"]],
    ["opencode", ["opencode providers login"]],
    ["codex", ["codex login"]],
  ] as Array<[ProviderId, string[]]>)("names the exact CLI step for %s in account mode", async (id, commands) => {
    await setup([provider(id)]);
    const hint = screen.getByTestId("login-hint");
    for (const command of commands) expect(within(hint).getByText(command, { selector: "code" })).toBeInTheDocument();
  });

  it("is not shown when the CLI is known to be signed in, nor in API mode", async () => {
    await setup([provider("claude", { login: "signed_in" })]);
    expect(screen.queryByTestId("login-hint")).toBeNull();
  });

  it("is replaced by the key form in API mode", async () => {
    await setup([provider("claude", { mode: "api", apiReady: true, keys: [{ slot: "claude", set: true, last4: "1234" }] })]);
    expect(screen.queryByTestId("login-hint")).toBeNull();
    expect(screen.getByLabelText("API key", { selector: "input" })).toBeInTheDocument();
  });

  it("appears again in the error card when a turn fails for authentication in account mode", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.type(screen.getByRole("textbox", { name: "Message to the assistant" }), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => {
      fake.chat.begin("t1");
      fake.chat.emit({ type: "error", code: "auth", message: "Invalid API key" });
      fake.chat.emit({ type: "done", reason: "failed" });
      fake.chat.end();
    });
    const cards = await screen.findAllByText(/The provider needs you to sign in/);
    const container = cards[0]!.closest(".error-card") as HTMLElement;
    expect(within(container).getByText("/login", { selector: "code" })).toBeInTheDocument();
  });

  it("points an authentication failure in API mode at the key, not at the CLI login", async () => {
    const { fake } = await setup([provider("claude", { mode: "api", apiReady: true, keys: [{ slot: "claude", set: true, last4: "1234" }] })]);
    await userEvent.type(screen.getByRole("textbox", { name: "Message to the assistant" }), "Go{Enter}");
    await waitFor(() => expect(fake.chat.starts).toHaveLength(1));
    act(() => {
      fake.chat.begin("t1");
      fake.chat.emit({ type: "error", code: "auth", message: "Invalid API key" });
      fake.chat.emit({ type: "done", reason: "failed" });
      fake.chat.end();
    });
    const cards = await screen.findAllByText(/The provider needs you to sign in/);
    const container = cards[0]!.closest(".error-card") as HTMLElement;
    expect(within(container).getByText(/check the api key/i)).toBeInTheDocument();
    expect(within(container).queryByText("/login", { selector: "code" })).toBeNull();
  });
});

describe("Antigravity in the header", () => {
  it("shows its official logo, account-only mode, and the agy sign-in hint", async () => {
    await setup([provider("antigravity", { modes: ["account"], keys: [], slot: null })]);
    const header = screen.getByRole("group", { name: "Assistant" });
    expect(within(header).getAllByRole("img", { name: "Antigravity" })).toHaveLength(2);
    expect(within(signIn()).getAllByRole("radio")).toHaveLength(1);
    expect(within(screen.getByTestId("login-hint")).getByText("agy", { selector: "code" })).toBeInTheDocument();
  });
});

describe("the partial isolation notice", () => {
  const notice = () => screen.queryByRole("note", { name: "Antigravity isolation" });

  it("stays visible while Antigravity is active, says what it means, and cannot be dismissed", async () => {
    await setup([provider("antigravity", { modes: ["account"], keys: [], slot: null })]);
    expect(notice()).toHaveTextContent("~/.gemini");
    expect(notice()).toHaveTextContent(/may already have started/i);
    expect(within(notice()!).queryByRole("button")).toBeNull();
  });

  it("is absent for the other providers", async () => {
    await setup([provider("claude")]);
    expect(notice()).toBeNull();
  });
});

describe("Pi in the header", () => {
  const piAuth = { modes: ["account", "api"] as ProviderAuth["modes"], keys: [{ slot: "pi:anthropic", set: false }], slot: null };

  it("shows its name, both sign-in modes and the pi sign-in hint", async () => {
    await setup([provider("claude"), provider("pi", piAuth)], "pi");
    const header = screen.getByRole("group", { name: "Assistant" });
    expect(within(header).getByText("Pi", { selector: ".provider-logo--large" })).toBeInTheDocument();
    expect(within(header).getByRole("radio", { name: "Pi" })).toHaveAttribute("aria-checked", "true");
    expect(within(signIn()).getAllByRole("radio")).toHaveLength(2);
    expect(within(screen.getByTestId("login-hint")).getByText("pi", { selector: "code" })).toBeInTheDocument();
  });

  it("keeps the Pi isolation notice visible while Pi is active, with no way to dismiss it", async () => {
    await setup([provider("claude"), provider("pi", piAuth)], "pi");
    const notice = screen.getByRole("note", { name: "Pi isolation" });
    expect(notice).toHaveTextContent("~/.pi/agent");
    expect(within(notice).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("note", { name: "Antigravity isolation" })).toBeNull();
  });

  it("is chosen from its radio, where Codex used to be", async () => {
    const { fake } = await setup([provider("claude"), provider("pi", piAuth)], "claude");
    expect(screen.queryByRole("note", { name: "Pi isolation" })).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "Pi" }));
    await waitFor(() => expect(fake.calls).toContain("selectProvider pi"));
  });
});

describe("the compact sign-in panel", () => {
  const details = () => signInDetails();
  const signInDetails = () => document.querySelector("details.auth-panel") as HTMLDetailsElement;

  it("folds away once the provider is signed in, saying how it signs in, and opens on request", async () => {
    await setup([provider("claude", { login: "signed_in" })]);
    expect(details().open).toBe(false);
    expect(within(details()).getByText("Sign-in: Account")).toBeInTheDocument();
    await userEvent.click(within(details()).getByText("Sign-in: Account"));
    expect(details().open).toBe(true);
  });

  it("stays open after the user changes the mode, so they can change it back", async () => {
    await setup([provider("claude", { login: "signed_out", apiReady: true, keys: [{ slot: "claude", set: true, last4: "7890" }] })]);
    await userEvent.click(radio("API key"));
    await waitFor(() => expect(radio("API key")).toBeChecked());
    expect(details().open).toBe(true);
  });

  it("stays open when the key store has a problem to show", async () => {
    await setup([provider("claude", { mode: "api", apiReady: true, storeProblem: "The store is unreadable.", keys: [{ slot: "claude", set: true, last4: "7890" }] })]);
    expect(details().open).toBe(true);
  });

  it("stays open while the provider still needs signing in", async () => {
    await setup([provider("claude", { login: "signed_out" })]);
    expect(details().open).toBe(true);
    expect(screen.getByTestId("login-hint")).toBeInTheDocument();
  });

  it("folds away in API mode only when a key is stored", async () => {
    await setup([provider("claude", { mode: "api", apiReady: true, keys: [{ slot: "claude", set: true, last4: "7890" }] })]);
    expect(details().open).toBe(false);
    expect(within(details()).getByText("Sign-in: API key")).toBeInTheDocument();
  });
});

describe("/login", () => {
  it("shows how to sign in to the active provider, and nothing reaches the assistant", async () => {
    const { fake } = await setup([provider("claude")]);
    await userEvent.type(screen.getByRole("textbox", { name: "Message to the assistant" }), "/login{Enter}");
    await waitFor(() => expect(screen.getAllByRole("status").some((note) => /run claude, then \/login/.test(note.textContent ?? ""))).toBe(true));
    expect(fake.chat.starts).toEqual([]);
  });
});
