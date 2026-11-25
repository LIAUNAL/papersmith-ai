import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { TURN_ERROR_CODES } from "@caztor/core";
import { ErrorCard } from "./ErrorCard.tsx";

describe("ErrorCard", () => {
  it("shows a plain title, the message and a suggested action", () => {
    render(<ErrorCard code="auth" message="Not logged in." />);
    expect(screen.getByRole("heading", { name: "The provider needs you to sign in" })).toBeInTheDocument();
    expect(screen.getByText("Not logged in.")).toBeInTheDocument();
    expect(screen.getByText(/sign in/i, { selector: "p.error-card__action" })).toBeInTheDocument();
  });

  it("keeps the technical detail collapsed until asked", async () => {
    render(<ErrorCard code="provider_error" message="The provider failed." detail={"exit 1\nstderr: boom"} />);
    expect(screen.queryByText(/stderr: boom/)).toBeNull();
    const toggle = screen.getByRole("button", { name: "Show details" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(screen.getByText(/stderr: boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide details" })).toHaveAttribute("aria-expanded", "true");
  });

  it("has no details button when there are no details", () => {
    render(<ErrorCard code="timeout" message="Too slow." />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it.each([...TURN_ERROR_CODES, "connection_lost" as const])("has a title and an action for %s", (code) => {
    const { container, unmount } = render(<ErrorCard code={code} message="m" />);
    expect(container.querySelector(".error-card__title")?.textContent).toMatch(/\S/);
    expect(container.querySelector(".error-card__action")?.textContent).toMatch(/\S/);
    unmount();
  });

  it("is an alert so assistive technology announces it", () => {
    render(<ErrorCard code="rate_limited" message="Slow down." />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
