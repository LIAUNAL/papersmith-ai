import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Collaborator, CollaboratorKey } from "../api/types.ts";
import { createFakeApi } from "../testing/fake-api.ts";
import { CollaboratorsDialog } from "./CollaboratorsDialog.tsx";

const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;
const NOW = new Date(2026, 10, 3, 12, 0).getTime();
const key = (id: string, extra: Partial<CollaboratorKey> = {}): CollaboratorKey => ({ id, createdAt: 0, expiresAt: NOW + 6 * DAY + 5 * MINUTE, status: "active", failures: 0, sessions: 0, ...extra });
const ana: Collaborator = { id: "u-ana", name: "Ana", role: "collaborator", createdAt: 0, sessions: 2, invites: [key("k1", { sessions: 2 })] };

async function invite(name: string) {
  await screen.findByText("Nobody is invited yet.");
  await userEvent.type(screen.getByRole("textbox", { name: "Name" }), name);
}

describe("CollaboratorsDialog", () => {
  it("lists collaborators with how many browsers are signed in", async () => {
    const fake = createFakeApi({ collaborators: [ana] });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} now={() => NOW} />);
    const list = await screen.findByRole("list", { name: "Collaborators" });
    expect(within(list).getByText("Ana")).toBeInTheDocument();
    expect(within(list).getByText("Signed in on 2 browsers")).toBeInTheDocument();
  });

  it("says when nobody is invited yet", async () => {
    const fake = createFakeApi();
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} />);
    expect(await screen.findByText("Nobody is invited yet.")).toBeInTheDocument();
  });

  it("invites by name for the lifetime chosen, shows the link and the key once, each with a copy button, and the expiry", async () => {
    const fake = createFakeApi({ now: NOW });
    const copy = vi.fn(async () => {});
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} copy={copy} now={() => NOW} />);
    await invite("Bo");
    const lifetime = screen.getByRole("combobox", { name: "Key lasts" });
    expect(within(lifetime).getAllByRole("option").map((option) => option.textContent)).toEqual(["1 hour", "1 day", "7 days", "30 days", "Until a date and time"]);
    expect(lifetime).toHaveValue("10080");
    await userEvent.selectOptions(lifetime, "1 day");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    expect(fake.calls).toContain("inviteCollaborator Bo 1440");

    const link = await screen.findByRole("textbox", { name: "Invite link for Bo" });
    expect(link).toHaveValue("https://box.ts.net/invite/invite1");
    expect(link).toHaveAttribute("readonly");
    const accessKey = screen.getByRole("textbox", { name: "Access key for Bo" });
    expect(accessKey).toHaveValue("ABCDE-FGH23-JKMNP-QRST1");
    expect(accessKey).toHaveAttribute("readonly");
    expect(screen.getByText(/The key is shown only now/)).toBeInTheDocument();
    expect(screen.getByText(`Expires ${new Date(NOW + DAY).toLocaleString()} (in 1 day).`)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Copy link" }));
    expect(copy).toHaveBeenLastCalledWith("https://box.ts.net/invite/invite1");
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Copy key" }));
    expect(copy).toHaveBeenLastCalledWith("ABCDE-FGH23-JKMNP-QRST1");
    expect(await screen.findByText("Key copied.")).toBeInTheDocument();

    const keys = within(screen.getByRole("list", { name: "Collaborators" })).getByRole("list", { name: "Keys of Bo" });
    expect(within(keys).getByText("Key 1: expires in 1 day, not used yet")).toBeInTheDocument();
  });

  it("asks for 7 days unless told otherwise", async () => {
    const fake = createFakeApi({ now: NOW });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} now={() => NOW} />);
    await invite("Bo");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    await waitFor(() => expect(fake.calls).toContain("inviteCollaborator Bo 10080"));
  });

  it("takes a custom date and time, and refuses one outside 10 minutes to 365 days without asking the server", async () => {
    const fake = createFakeApi({ now: NOW });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} now={() => NOW} />);
    await invite("Bo");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Key lasts" }), "Until a date and time");
    const until = screen.getByLabelText("Key ends at");
    fireEvent.change(until, { target: { value: "2026-11-03T12:05" } });
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose how long the key lasts: from 10 minutes to 365 days.");
    expect(fake.calls.filter((call) => call.startsWith("inviteCollaborator"))).toEqual([]);
    fireEvent.change(until, { target: { value: "2026-11-05T12:00" } });
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    await waitFor(() => expect(fake.calls).toContain("inviteCollaborator Bo 2880"));
  });

  it("shows each key's expiry, and when it expired, locked or is an old invite", async () => {
    const people: Collaborator[] = [
      {
        ...ana,
        invites: [
          key("k1", { sessions: 2 }),
          key("k2", { expiresAt: NOW - MINUTE, status: "expired" }),
          key("k3", { status: "locked", failures: 10 }),
          key("k4", { status: "old" }),
          key("k5", { expiresAt: NOW + 3 * 60 * MINUTE + 20 * MINUTE, sessions: 1 }),
          key("k6", { expiresAt: NOW + 25 * MINUTE }),
          // Just under a day reads as a day: the nearest whole unit.
          key("k7", { expiresAt: NOW + DAY - 5 * MINUTE }),
        ],
      },
    ];
    render(<CollaboratorsDialog api={createFakeApi({ collaborators: people }).api} onClose={() => {}} now={() => NOW} />);
    const keys = await screen.findByRole("list", { name: "Keys of Ana" });
    expect(within(keys).getAllByRole("listitem").map((item) => item.querySelector(".collaborators__key-state")?.textContent)).toEqual([
      "Key 1: expires in 6 days, on 2 browsers",
      "Key 2: expired",
      "Key 3: locked after 10 wrong keys",
      "Key 4: old invite, create a new one",
      "Key 5: expires in 3 hours, on 1 browser",
      "Key 6: expires in 25 minutes, not used yet",
      "Key 7: expires in 1 day, not used yet",
    ]);
  });

  it("revokes one key and lists again", async () => {
    const fake = createFakeApi({ collaborators: [{ ...ana, invites: [key("k1"), key("k2")] }] });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} now={() => NOW} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke key 1 of Ana" }));
    await waitFor(() => expect(fake.calls).toContain("revokeCollaboratorKey k1"));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Keys of Ana" })).getAllByRole("listitem")).toHaveLength(1));
    expect(fake.calls).not.toContain("revokeCollaborator u-ana");
  });

  it("tells how to copy by hand when the browser refuses", async () => {
    const fake = createFakeApi();
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} copy={async () => Promise.reject(new Error("denied"))} />);
    await invite("Bo");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    await userEvent.click(await screen.findByRole("button", { name: "Copy key" }));
    expect(await screen.findByText("Select the key and copy it.")).toBeInTheDocument();
  });

  it("shows why an invite was refused", async () => {
    const fake = createFakeApi({ inviteError: "Start Caztor with --public-name so collaborators can reach it." });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} />);
    await invite("Bo");
    await userEvent.click(screen.getByRole("button", { name: "Invite" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("--public-name");
  });

  it("revokes a collaborator and lists again", async () => {
    const fake = createFakeApi({ collaborators: [ana] });
    render(<CollaboratorsDialog api={fake.api} onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke Ana" }));
    await waitFor(() => expect(fake.calls).toContain("revokeCollaborator u-ana"));
    expect(await screen.findByText("Nobody is invited yet.")).toBeInTheDocument();
  });

  it("closes", async () => {
    const onClose = vi.fn();
    render(<CollaboratorsDialog api={createFakeApi().api} onClose={onClose} />);
    await userEvent.click(await screen.findByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
