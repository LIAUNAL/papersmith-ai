import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProviderUnavailable } from "./ProviderUnavailable.tsx";

describe("ProviderUnavailable", () => {
  it("says the provider is not installed with the server's reason and an install hint", () => {
    render(<ProviderUnavailable provider="codex" reason="codex was not found on your PATH." checking={false} onRecheck={() => {}} />);
    expect(screen.getByRole("heading", { name: /Codex is not available/ })).toBeInTheDocument();
    expect(screen.getByText("codex was not found on your PATH.")).toBeInTheDocument();
    expect(screen.getByText(/install/i, { selector: "p" })).toBeInTheDocument();
  });

  it("re-checks on request and shows that it is checking", async () => {
    const onRecheck = vi.fn();
    const { rerender } = render(<ProviderUnavailable provider="claude" reason="r" checking={false} onRecheck={onRecheck} />);
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(onRecheck).toHaveBeenCalledTimes(1);
    rerender(<ProviderUnavailable provider="claude" reason="r" checking onRecheck={onRecheck} />);
    expect(screen.getByRole("button", { name: "Checking" })).toBeDisabled();
  });
});
