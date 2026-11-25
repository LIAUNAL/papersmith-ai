import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { apiError } from "../testing/fake-api.ts";
import { DisclosureNotice } from "./DisclosureNotice.tsx";

describe("DisclosureNotice", () => {
  it("states the limits in plain words", () => {
    render(<DisclosureNotice onAcknowledge={async () => {}} />);
    const dialog = screen.getByRole("dialog", { name: "Before you start" });
    expect(dialog).toHaveTextContent("LaTeX engine");
    expect(dialog).toHaveTextContent("AI agent");
    expect(dialog).toHaveTextContent("as your user");
    expect(dialog).toHaveTextContent("sent to the model provider");
    expect(dialog).toHaveTextContent("Open only projects you trust");
  });

  it("moves keyboard focus to the acknowledge button", () => {
    render(<DisclosureNotice onAcknowledge={async () => {}} />);
    expect(screen.getByRole("button", { name: "I understand" })).toHaveFocus();
  });

  it("acknowledges once and disables the button while it saves", async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    const onAcknowledge = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    render(<DisclosureNotice onAcknowledge={onAcknowledge} />);

    await user.click(screen.getByRole("button", { name: "I understand" }));
    expect(screen.getByRole("button", { name: "Saving" })).toBeDisabled();
    await user.keyboard("{Enter}");
    finish();
    expect(await screen.findByRole("button", { name: "I understand" })).toBeEnabled();
    expect(onAcknowledge).toHaveBeenCalledTimes(1);
  });

  it("is not dismissed by Escape", async () => {
    const user = userEvent.setup();
    const onAcknowledge = vi.fn(async () => {});
    render(<DisclosureNotice onAcknowledge={onAcknowledge} />);
    await user.keyboard("{Escape}");
    expect(onAcknowledge).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the readable error and lets the user try again when saving fails", async () => {
    const user = userEvent.setup();
    const onAcknowledge = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(apiError("network", "Cannot reach the Caztor server. Check that it is still running.", 0))
      .mockResolvedValueOnce(undefined);
    render(<DisclosureNotice onAcknowledge={onAcknowledge} />);

    await user.click(screen.getByRole("button", { name: "I understand" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the Caztor server. Check that it is still running.");
    await user.click(screen.getByRole("button", { name: "I understand" }));
    expect(onAcknowledge).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
