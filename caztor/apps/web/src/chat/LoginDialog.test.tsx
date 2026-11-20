import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ProviderAuth, ProviderId, ProviderInfo } from "../api/types.ts";
import { createFakeApi } from "../testing/fake-api.ts";
import { ChatPanel } from "./ChatPanel.tsx";
import { ChatController } from "./controller.ts";

const auth = (patch: Partial<ProviderAuth> = {}): ProviderAuth => ({
  mode: "account",
  modes: ["account", "api"],
  keys: [],
  slot: "claude",
  apiReady: false,
  login: "unknown",
  loginHint: "Sign in with your Claude account: run `claude`, then `/login`.",
  ...patch,
});
const provider = (id: ProviderId, patch: Partial<ProviderAuth> = {}): ProviderInfo => ({ id, installed: true, requiresModel: false, model: null, auth: auth(patch) });
const CLAUDE_TEXT = "Opening browser to sign in…\nIf the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=A3v5\nPaste code here if prompted >";

async function setup(providers: ProviderInfo[] = [provider("claude")]) {
  const fake = createFakeApi({ providers: { selected: providers[0]!.id, providers } });
  const controller = new ChatController({ api: fake.api, wait: async () => {}, loginPollMs: 20 });
  render(<ChatPanel controller={controller} />);
  await act(() => controller.load());
  return { fake, controller };
}

describe("signing in from the browser", () => {
  it("offers Sign in in account mode, and keeps the terminal hint as a fallback", async () => {
    await setup();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByTestId("login-hint")).toHaveTextContent("run claude, then /login");
  });

  it("opens a dialog that starts the sign-in and shows the CLI's text with its link clickable in a new tab", async () => {
    const { fake } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(fake.calls).toContain("startLogin claude default"));
    fake.login.view = { provider: "claude", method: "subscription", state: "running", text: CLAUDE_TEXT, terminal: false };
    const dialog = await screen.findByRole("dialog", { name: /Sign in to Claude/ });
    const link = await within(dialog).findByRole("link", { name: /claude\.com\/cai\/oauth/ });
    expect(link).toHaveAttribute("href", "https://claude.com/cai/oauth/authorize?code=true&state=A3v5");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("sends the pasted code and empties the box", async () => {
    const { fake } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const box = await screen.findByPlaceholderText("Paste the code here");
    await userEvent.type(box, "pasted-code-abc{Enter}");
    await waitFor(() => expect(fake.calls).toContain("sendLogin claude line:pasted-code-abc"));
    expect(box).toHaveValue("");
  });

  it("shows a device code ready to copy", async () => {
    const { fake } = await setup([provider("codex")]);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    fake.login.view = { provider: "codex", method: "device", state: "running", text: "Enter this one-time code\n   XZIF-17WOH", code: "XZIF-17WOH", terminal: false };
    expect(await screen.findByRole("button", { name: "Copy code XZIF-17WOH" })).toBeInTheDocument();
  });

  it("offers the menu keys when the CLI runs in a terminal", async () => {
    const { fake } = await setup([provider("antigravity")]);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    fake.login.view = { provider: "antigravity", method: "google", state: "running", text: " > 1. Google OAuth", terminal: true };
    await userEvent.click(await screen.findByRole("button", { name: "Down" }));
    await userEvent.click(screen.getByRole("button", { name: "Enter" }));
    await waitFor(() => expect(fake.calls).toEqual(expect.arrayContaining(["sendLogin antigravity key:down", "sendLogin antigravity key:enter"])));
  });

  it("cancels the sign-in on the server when the person closes the dialog", async () => {
    const { fake } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(fake.calls).toContain("cancelLogin claude");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says when it is done and reads the providers again", async () => {
    const { fake } = await setup();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const before = fake.calls.filter((call) => call === "listProviders").length;
    fake.login.view = { provider: "claude", method: "subscription", state: "signed_in", text: "Login successful.", terminal: false };
    expect(await screen.findByText("You are signed in.")).toBeInTheDocument();
    await waitFor(() => expect(fake.calls.filter((call) => call === "listProviders").length).toBeGreaterThan(before));
  });

  it("lets the person choose how to sign in when the CLI has several ways", async () => {
    const { fake } = await setup([provider("opencode")]);
    fake.login.methods = [{ id: "chatgpt", label: "ChatGPT Pro/Plus (device code)" }, { id: "menu", label: "Another provider (opencode's own menu)" }];
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.click(await screen.findByRole("button", { name: "Another provider (opencode's own menu)" }));
    expect(fake.calls).toContain("startLogin opencode menu");
  });
});
